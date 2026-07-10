from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import settings
from models import Task
from shadow.budget import BudgetTracker, DailyBudgetLedger
from shadow.executor import ExecutorManager

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
async def delegate_task(req: DelegateRequest):
    mgr = get_manager()
    task = Task(
        title=req.title,
        description=req.description,
        budget_cap=req.budget_cap or settings.per_task_budget_default,
    )
    task_id = await mgr.spawn(task)
    return task.model_dump(mode="json")


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
    ledger = DailyBudgetLedger()
    active = await mgr.list_active()
    tracker = BudgetTracker(
        task_id="__global__",
        task_budget=0,
        daily_budget=settings.daily_cloud_budget,
    )
    snapshot = tracker.get_snapshot(
        active_tasks=len(active),
        total_tasks_today=len(mgr.list_all()),
    )
    return snapshot.model_dump(mode="json")
