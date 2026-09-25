from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from models import Task
from shadow.budget import BudgetTracker
from shadow.executor import ExecutorManager
from shadow.guard_config import GuardConfig, guard_config_store
from shadow.agents_store import list_agents
from auth import CurrentContext, current_context

# Every route here needs a signed-in caller when DEXTER_REQUIRE_AUTH is on (kill, gate
# approve/reject and guard edits control real spend). With auth off, current_context
# resolves to the default owner, so single-user setups are unaffected.
router = APIRouter(prefix="/api/shadow", tags=["shadow"], dependencies=[Depends(current_context)])

TEST_GATE_ID = "test"


def _require_manager(ctx: CurrentContext) -> None:
    if ctx.role not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Only an owner or admin can change guardrails")


def _task_in_business(task: Task | None, ctx: CurrentContext) -> bool:
    """ExecutorManager is process-wide (docs/PHASE_3_4_PLAN.md §1), so live tasks are
    filtered to the caller's business here — the id stamped on at spawn time."""
    return task is not None and task.metadata.get("business_id") == ctx.business_id


async def _owned_task(task_id: str, ctx: CurrentContext) -> Task:
    task = await get_manager().get_status(task_id)
    if not _task_in_business(task, ctx):
        raise HTTPException(status_code=404, detail="Task not found")
    return task

_manager: ExecutorManager | None = None


def get_manager() -> ExecutorManager:
    global _manager
    if _manager is None:
        _manager = ExecutorManager()
    return _manager


class DelegateRequest(BaseModel):
    title: str
    description: str = ""
    budget_cap: float | None = None
    tier: int | None = None            # 1 fast · 2 standard · 3 frontier — overrides the classifier
    minutes_saved: int | None = None   # Commander's estimate of human time this saves (Home: hours reclaimed)
    revenue_value: float | None = None  # revenue this task enables, if any (Home: revenue enabled)


class RejectRequest(BaseModel):
    reason: str = ""


@router.post("/delegate")
async def delegate_task(req: DelegateRequest, request: Request, ctx: CurrentContext = Depends(current_context)):
    mgr = get_manager()
    config = await guard_config_store.get()
    task = Task(
        title=req.title,
        description=req.description,
        budget_cap=req.budget_cap or config.per_task_budget_default,
        metadata={
            "business_id": ctx.business_id, "owner_user_id": ctx.user_id, "tier": req.tier,
            "minutes_saved": req.minutes_saved, "revenue_value": req.revenue_value,
        },
    )
    await spawn_selected(request.app, task, ctx.business_id, ctx.user_id, req.tier)
    return task.model_dump(mode="json")


async def spawn_selected(app, task: Task, business_id: str | None, owner_user_id: str | None, tier: int | None = None) -> None:
    """Selector Core picks the cheapest capable model; the task's tool loop runs on it.
    Falls back to the Brain (Ollama/DeepSeek/stub) only when the Selector has no candidate."""
    from shadow.selector import SelectedBrain, select
    from shadow.work import make_llm_work_fn

    work_fn = None
    model_route = None
    gateway = getattr(app.state, "gateway", None)
    selection = await select(gateway, f"{task.title} {task.description}", business_id, tier) if gateway else None
    if selection is not None:
        work_fn = make_llm_work_fn(SelectedBrain(gateway, selection, business_id, agent_id=f"agent_{task.id}"))
        model_route = selection.route
        task.metadata["selection"] = selection.as_dict()
    else:
        brain = getattr(app.state, "brain", None)
        if brain is not None:
            active = await brain.describe()
            if active["ready"]:
                work_fn = make_llm_work_fn(brain)
                model_route = f"{active['provider']}:{active['model']}"
    task.metadata["model_route"] = model_route
    await get_manager().spawn(task, work_fn=work_fn, owner_user_id=owner_user_id, business_id=business_id, model_route=model_route)


class SelectorPreview(BaseModel):
    title: str
    description: str = ""
    tier: int | None = None


@router.post("/selector/preview")
async def selector_preview(req: SelectorPreview, request: Request, ctx: CurrentContext = Depends(current_context)):
    """Dry run of Selector Core — which model a task like this would get, and why every
    other candidate was or wasn't eligible. No model is called."""
    from shadow.selector import select

    gateway = getattr(request.app.state, "gateway", None)
    selection = await select(gateway, f"{req.title} {req.description}", ctx.business_id, req.tier) if gateway else None
    return selection.as_dict() if selection else {"route": None, "reason": "No model available — configure a provider or start Ollama"}


@router.get("/agents")
async def get_agents(ctx: CurrentContext = Depends(current_context)):
    """Real, persistent Agent identity (docs/PHASE_3_4_PLAN.md §2) — feeds the Swarm
    screen. Empty without a database (agents aren't persisted, same as everything else)."""
    return await list_agents(ctx.business_id)


@router.get("/tasks")
async def list_tasks(ctx: CurrentContext = Depends(current_context)):
    mgr = get_manager()
    return [t.model_dump(mode="json") for t in mgr.list_all() if _task_in_business(t, ctx)]


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, ctx: CurrentContext = Depends(current_context)):
    task = await _owned_task(task_id, ctx)
    return task.model_dump(mode="json")


@router.post("/tasks/{task_id}/kill")
async def kill_task(task_id: str, ctx: CurrentContext = Depends(current_context)):
    await _owned_task(task_id, ctx)
    mgr = get_manager()
    killed = await mgr.kill(task_id)
    if not killed:
        raise HTTPException(status_code=404, detail="Task not found or already terminal")
    task = await mgr.get_status(task_id)
    return task.model_dump(mode="json") if task else {"status": "killed"}


@router.get("/gates")
async def list_gates(ctx: CurrentContext = Depends(current_context)):
    mgr = get_manager()
    visible = [
        g for g in mgr.gate_manager.list_pending()
        if g.task_id == TEST_GATE_ID or _task_in_business(await mgr.get_status(g.task_id), ctx)
    ]
    return [
        {
            "task_id": g.task_id,
            "reason": g.reason,
            "task_title": g.task_title,
            "created_at": g.created_at.isoformat(),
            "status": g.status,
            "resolved_at": g.resolved_at.isoformat() if g.resolved_at else None,
        }
        for g in visible
    ]


@router.post("/gates/{task_id}/approve")
async def approve_gate(task_id: str, ctx: CurrentContext = Depends(current_context)):
    if task_id != TEST_GATE_ID:
        await _owned_task(task_id, ctx)
    mgr = get_manager()
    approved = await mgr.approve_gate(task_id)
    if not approved:
        raise HTTPException(status_code=404, detail="No pending gate for this task")
    return {"task_id": task_id, "status": "approved"}


@router.post("/gates/{task_id}/reject")
async def reject_gate(task_id: str, req: RejectRequest | None = None, ctx: CurrentContext = Depends(current_context)):
    if task_id != TEST_GATE_ID:
        await _owned_task(task_id, ctx)
    mgr = get_manager()
    reason = req.reason if req else ""
    rejected = await mgr.reject_gate(task_id, reason)
    if not rejected:
        raise HTTPException(status_code=404, detail="No pending gate for this task")
    return {"task_id": task_id, "status": "rejected"}


@router.post("/gates/test")
async def create_test_gate():
    mgr = get_manager()
    gate = await mgr.gate_manager.create_gate(
        task_id=TEST_GATE_ID,
        reason="Test notification — tap approve to dismiss",
        task_title="Test gate from Settings",
    )
    return {
        "task_id": gate.task_id,
        "reason": gate.reason,
        "task_title": gate.task_title,
        "created_at": gate.created_at.isoformat(),
        "status": gate.status,
        "resolved_at": None,
    }


@router.get("/budget")
async def get_budget():
    mgr = get_manager()
    config = await guard_config_store.get()
    active = await mgr.list_active()
    tracker = BudgetTracker(
        task_id="__global__",
        task_budget=0,
        daily_budget=config.daily_budget,
    )
    snapshot = tracker.get_snapshot(
        active_tasks=len(active),
        total_tasks_today=len(mgr.list_all()),
    )
    return snapshot.model_dump(mode="json")


# ---------------------------------------------------------------- guard config (P6)

class GuardPatch(BaseModel):
    daily_budget: float | None = None
    per_task_budget_default: float | None = None
    high_cost_multiplier: float | None = None
    long_running_minutes: int | None = None
    monthly_budget: float | None = None
    provider_monthly_caps: dict[str, float] | None = None
    agent_daily_cap: float | None = None          # send null explicitly to remove the cap
    burn_rate_alert_per_hour: float | None = None  # send null explicitly to turn alerts off


class RuleIn(BaseModel):
    name: str
    keyword: str = ""
    max_spend: float | None = None
    require_approval: bool = False


@router.get("/guards", response_model=GuardConfig)
async def get_guard_config():
    return await guard_config_store.get()


@router.patch("/guards", response_model=GuardConfig)
async def patch_guard_config(patch: GuardPatch, ctx: CurrentContext = Depends(current_context)):
    _require_manager(ctx)
    return await guard_config_store.update(patch.model_dump(exclude_unset=True))


@router.post("/guards/rules", response_model=GuardConfig, status_code=201)
async def add_guard_rule(rule: RuleIn, ctx: CurrentContext = Depends(current_context)):
    _require_manager(ctx)
    return await guard_config_store.add_rule(
        name=rule.name, keyword=rule.keyword, max_spend=rule.max_spend, require_approval=rule.require_approval,
    )


@router.delete("/guards/rules/{rule_id}", response_model=GuardConfig)
async def remove_guard_rule(rule_id: str, ctx: CurrentContext = Depends(current_context)):
    _require_manager(ctx)
    return await guard_config_store.remove_rule(rule_id)
