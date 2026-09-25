from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from models import Task
from shadow.budget import BudgetTracker
from shadow.executor import ExecutorManager
from shadow.guard_config import GuardConfig, guard_config_store
from shadow.agents_store import list_agents
from auth import CurrentContext, current_context

router = APIRouter(prefix="/api/shadow", tags=["shadow"])

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
    )
    work_fn = None
    model_route = None
    brain = getattr(request.app.state, "brain", None)
    if brain is not None:
        active = await brain.describe()
        if active["ready"]:
            from shadow.work import make_llm_work_fn
            work_fn = make_llm_work_fn(brain)
            model_route = f"{active['provider']}:{active['model']}"
    task_id = await mgr.spawn(task, work_fn=work_fn, owner_user_id=ctx.user_id, business_id=ctx.business_id, model_route=model_route)
    return task.model_dump(mode="json")


@router.get("/agents")
async def get_agents(ctx: CurrentContext = Depends(current_context)):
    """Real, persistent Agent identity (docs/PHASE_3_4_PLAN.md §2) — feeds the Swarm
    screen. Empty without a database (agents aren't persisted, same as everything else)."""
    return await list_agents(ctx.business_id)


@router.get("/tasks")
async def list_tasks():
    mgr = get_manager()
    return [t.model_dump(mode="json") for t in mgr.list_all()]


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    mgr = get_manager()
    task = await mgr.get_status(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task.model_dump(mode="json")


@router.post("/tasks/{task_id}/kill")
async def kill_task(task_id: str):
    mgr = get_manager()
    killed = await mgr.kill(task_id)
    if not killed:
        raise HTTPException(status_code=404, detail="Task not found or already terminal")
    task = await mgr.get_status(task_id)
    return task.model_dump(mode="json") if task else {"status": "killed"}


@router.get("/gates")
async def list_gates():
    mgr = get_manager()
    return [
        {
            "task_id": g.task_id,
            "reason": g.reason,
            "task_title": g.task_title,
            "created_at": g.created_at.isoformat(),
            "status": g.status,
            "resolved_at": g.resolved_at.isoformat() if g.resolved_at else None,
        }
        for g in mgr.gate_manager.list_pending()
    ]


@router.post("/gates/{task_id}/approve")
async def approve_gate(task_id: str):
    mgr = get_manager()
    approved = await mgr.approve_gate(task_id)
    if not approved:
        raise HTTPException(status_code=404, detail="No pending gate for this task")
    return {"task_id": task_id, "status": "approved"}


@router.post("/gates/{task_id}/reject")
async def reject_gate(task_id: str, req: RejectRequest | None = None):
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
        task_id="test",
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


class RuleIn(BaseModel):
    name: str
    keyword: str = ""
    max_spend: float | None = None
    require_approval: bool = False


@router.get("/guards", response_model=GuardConfig)
async def get_guard_config():
    return await guard_config_store.get()


@router.patch("/guards", response_model=GuardConfig)
async def patch_guard_config(patch: GuardPatch):
    return await guard_config_store.update(patch.model_dump(exclude_unset=True))


@router.post("/guards/rules", response_model=GuardConfig, status_code=201)
async def add_guard_rule(rule: RuleIn):
    return await guard_config_store.add_rule(
        name=rule.name, keyword=rule.keyword, max_spend=rule.max_spend, require_approval=rule.require_approval,
    )


@router.delete("/guards/rules/{rule_id}", response_model=GuardConfig)
async def remove_guard_rule(rule_id: str):
    return await guard_config_store.remove_rule(rule_id)
