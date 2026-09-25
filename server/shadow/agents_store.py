"""Persistent Agent identity + real task history (docs/PHASE_3_4_PLAN.md §2).

Before this, an executor was a pure in-memory `Task`/`ExecutorProcess` pair with no
row anywhere — the PRD's §4 `Agent` object (efficiency score, spawn metadata, owner)
didn't exist, and `task_log` had a table nobody wrote to. Every `ExecutorManager.spawn`
now creates an `agents` row and both are updated on completion.

Efficiency score is computed, not fabricated: `outcome_weight / max(spend, floor)`,
where outcome_weight is 1.0 for a clean `done`, 0.3 for a gate that got approved, 0 for
anything killed. That's a real number from real spend and a real outcome — distinct
from the PRD's separate "score candidates before routing" idea, which is what
`escalation/router.py` already does at routing time; this is a post-hoc fitness score,
which is what Swarm's "fittest survive" language actually needs. Stored unnormalized;
callers normalize against the batch they're displaying (a display concern, not a
storage one — a score for a $50 task will always look tiny next to a $0.01 one, and
which of those is "the batch" changes with the query).
"""
from __future__ import annotations

import logging

from db.connection import get_pool
from models import Task, TaskStatus

log = logging.getLogger("dexter.shadow.agents_store")

SPEND_FLOOR = 0.001


def compute_efficiency(spend: float, status: TaskStatus) -> float:
    if status == TaskStatus.DONE:
        outcome_weight = 1.0
    elif status == TaskStatus.GATED:
        outcome_weight = 0.3  # mid-flight snapshot; finalized once the gate resolves
    elif status == TaskStatus.KILLED:
        outcome_weight = 0.0
    else:
        outcome_weight = 0.5  # queued/running — no outcome yet, neutral
    return round(outcome_weight / max(spend, SPEND_FLOOR), 4)


async def record_spawn(task: Task, owner_user_id: str | None, business_id: str | None, model_route: str | None = None) -> None:
    pool = await get_pool()
    if pool is None:
        return
    try:
        async with pool.connection() as conn:
            await conn.execute(
                """INSERT INTO agents (id, name, kind, status, model_route, budget_cap, spend, owner_user_id, business_id, task_id)
                   VALUES (%s, %s, 'executor', %s, %s, %s, 0, %s, %s, %s)""",
                (f"agent_{task.id}", task.title[:120], task.status.value, model_route, task.budget_cap, owner_user_id, business_id, task.id),
            )
            await conn.execute(
                """INSERT INTO task_log (id, title, description, status, protocol, executor_id, budget_cap, spend, created_at, business_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status""",
                (task.id, task.title, task.description, task.status.value, task.protocol.value,
                 task.executor_id, task.budget_cap, task.spend, task.created_at, business_id),
            )
    except Exception as e:
        log.warning("Could not persist agent spawn for task %s (continuing without it): %s", task.id, e)


async def record_completion(task: Task) -> None:
    """Called once a task reaches a terminal state (done/killed) or is gated —
    updates both `agents` and `task_log` with the final spend/status/score."""
    pool = await get_pool()
    if pool is None:
        return
    score = compute_efficiency(task.spend, task.status)
    gated_now = task.status == TaskStatus.GATED
    try:
        async with pool.connection() as conn:
            await conn.execute(
                """UPDATE agents SET status = %s, spend = %s, efficiency_score = %s, completed_at = %s
                   WHERE task_id = %s""",
                (task.status.value, task.spend, score, task.completed_at, task.id),
            )
            await conn.execute(
                """UPDATE task_log SET status = %s, spend = %s, completed_at = %s, result = %s, error = %s,
                          was_gated = was_gated OR %s
                   WHERE id = %s""",
                (task.status.value, task.spend, task.completed_at, task.result, task.error, gated_now, task.id),
            )
    except Exception as e:
        log.warning("Could not persist agent completion for task %s (continuing without it): %s", task.id, e)


async def list_agents(business_id: str, limit: int = 50) -> list[dict]:
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT id, name, kind, model_route, status, efficiency_score, budget_cap, spend,
                      task_id, created_at, completed_at
               FROM agents WHERE business_id = %s ORDER BY created_at DESC LIMIT %s""",
            (business_id, limit),
        )
        rows = await cur.fetchall()
    agents = [
        {
            "id": r[0], "name": r[1], "kind": r[2], "model_route": r[3], "status": r[4],
            "efficiency_score": r[5], "budget_cap": r[6], "spend": r[7], "task_id": r[8],
            "created_at": r[9], "completed_at": r[10],
        }
        for r in rows
    ]
    # Normalize efficiency to 0-1 against the max in THIS batch — see module docstring.
    scored = [a["efficiency_score"] for a in agents if a["efficiency_score"] is not None]
    peak = max(scored) if scored else 0
    for a in agents:
        a["efficiency_normalized"] = round(a["efficiency_score"] / peak, 3) if peak and a["efficiency_score"] is not None else None
    return agents
