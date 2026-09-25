"""Success metrics (PRD §8, docs/PHASE_3_4_PLAN.md §3) — before this, nothing counted
any of the four numbers the PRD defines as what "working" looks like. All four are
computed from `task_log` (now actually written to — see shadow/agents_store.py),
`gates`, and `conversations`, scoped to the caller's business.

Every number here comes from real rows; a business with no history yet gets honest
zeros/nulls, never a fabricated "looks good" placeholder.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from db.connection import get_pool
from auth import CurrentContext, current_context

log = logging.getLogger("dexter.metrics")

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

# PRD §8's own stated v1 targets — the numbers exist without these, but "is it working"
# needs something to compare against, not just a raw figure.
TARGET_TIME_TO_COMPLETION_MIN = 10
TARGET_WITHOUT_INTERVENTION_PCT = 70


def _empty_summary() -> dict:
    return {
        "time_to_completion": {"median_seconds": None, "p90_seconds": None, "sample_size": 0, "on_track": None},
        "intervention_rate": {"without_intervention_pct": None, "sample_size": 0, "on_track": None},
        "cost_trend": [],
        "activity": {"active_sessions_7d": 0, "approvals_7d": 0},
        "targets": {"time_to_completion_minutes": TARGET_TIME_TO_COMPLETION_MIN, "without_intervention_pct": TARGET_WITHOUT_INTERVENTION_PCT},
    }


@router.get("/summary")
async def metrics_summary(ctx: CurrentContext = Depends(current_context)) -> dict:
    pool = await get_pool()
    if pool is None:
        return _empty_summary()

    async with pool.connection() as conn:
        # 1 · time from command to completed mission — PRD's own target: median < 10 min
        cur = await conn.execute(
            """SELECT EXTRACT(EPOCH FROM (completed_at - created_at))
               FROM task_log WHERE business_id = %s AND status = 'done' AND completed_at IS NOT NULL
               ORDER BY completed_at DESC LIMIT 200""",
            (ctx.business_id,),
        )
        durations = sorted(r[0] for r in await cur.fetchall())

        # 2 · % of missions completed without human intervention (never passed through a gate)
        cur = await conn.execute(
            """SELECT COUNT(*) FILTER (WHERE NOT was_gated), COUNT(*)
               FROM task_log WHERE business_id = %s AND status IN ('done', 'killed')""",
            (ctx.business_id,),
        )
        clean, total_terminal = await cur.fetchone()

        # 3 · cost per completed mission, trending — weekly buckets, last 8 weeks
        cur = await conn.execute(
            """SELECT date_trunc('week', completed_at) AS wk, AVG(spend), COUNT(*)
               FROM task_log
               WHERE business_id = %s AND status = 'done' AND completed_at > now() - interval '8 weeks'
               GROUP BY wk ORDER BY wk ASC""",
            (ctx.business_id,),
        )
        cost_trend = [
            {"week_start": r[0].date().isoformat(), "avg_cost": round(float(r[1]), 4), "count": r[2]}
            for r in await cur.fetchall()
        ]

        # 4 · weekly active sessions / approvals per week
        since = datetime.now(timezone.utc) - timedelta(days=7)
        cur = await conn.execute(
            "SELECT COUNT(DISTINCT id) FROM conversations WHERE business_id = %s AND updated_at > %s",
            (ctx.business_id, since),
        )
        active_sessions = (await cur.fetchone())[0]

    # Gates are process-wide, not persisted per-business (see briefing.py's note on why) —
    # approved/rejected in the last 7 days, across whichever businesses this Commander runs.
    from shadow.router import get_manager
    mgr = get_manager()
    approvals_7d = len(mgr.gate_manager.list_resolved_since(since))

    def _pct(part: int, whole: int) -> float | None:
        return round(100 * part / whole, 1) if whole else None

    def _pick(sorted_vals: list[float], pct: float) -> float | None:
        if not sorted_vals:
            return None
        idx = min(len(sorted_vals) - 1, int(len(sorted_vals) * pct))
        return round(sorted_vals[idx], 1)

    median_s = _pick(durations, 0.5)
    without_intervention = _pct(clean or 0, total_terminal or 0)

    return {
        "time_to_completion": {
            "median_seconds": median_s,
            "p90_seconds": _pick(durations, 0.9),
            "sample_size": len(durations),
            "on_track": (median_s / 60 <= TARGET_TIME_TO_COMPLETION_MIN) if median_s is not None else None,
        },
        "intervention_rate": {
            "without_intervention_pct": without_intervention,
            "sample_size": total_terminal or 0,
            "on_track": (without_intervention >= TARGET_WITHOUT_INTERVENTION_PCT) if without_intervention is not None else None,
        },
        "cost_trend": cost_trend,
        "activity": {"active_sessions_7d": active_sessions, "approvals_7d": approvals_7d},
        "targets": {"time_to_completion_minutes": TARGET_TIME_TO_COMPLETION_MIN, "without_intervention_pct": TARGET_WITHOUT_INTERVENTION_PCT},
    }
