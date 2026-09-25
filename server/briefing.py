"""Morning briefing generator (docs/BACKEND_TASKS.md P4).

`GET /api/briefing/today` pulls real numbers — today's tasks, pending gates, spend —
and asks the Brain to turn them into the "Good morning, Commander" copy the Home
screen shows. The model only writes the sentence; every number it's given is real,
so a Brain-less deployment (no Ollama, no DeepSeek key) still gets an accurate,
if plainer, fallback line instead of Ollama's canned mock.

Cached for CACHE_TTL_S so opening Home repeatedly doesn't re-spend a model call —
mirrors Brain's own health-check TTL pattern.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from projects import tasks_store
from shadow.router import get_manager
from auth import CurrentContext, current_context

log = logging.getLogger("dexter.briefing")

router = APIRouter(prefix="/api/briefing", tags=["briefing"])

CACHE_TTL_S = 300
_cache: dict = {}


def _fallback_headline(stats: dict) -> str:
    bits = [f"{stats['tasks_today']} tasks today"]
    if stats["tasks_done"]:
        bits.append(f"{stats['tasks_done']} already done")
    if stats["blocked"]:
        bits.append(f"{stats['blocked']} blocked")
    if stats["gates_pending"]:
        bits.append(f"{stats['gates_pending']} gate(s) waiting on you")
    return "Good morning, Commander. " + ", ".join(bits) + "."


async def _gather_stats(business_id: str) -> dict:
    today_tasks = await tasks_store.list(business_id, when_bucket="today")
    # Anthony's executor manager is one process-wide instance, not partitioned per
    # business — this backend runs on the Commander's own single machine (PRD §6), so
    # "multiple businesses" means one Commander's own ventures, not unrelated tenants
    # sharing a server. Gates/live tasks are shared across a Commander's businesses by
    # design; only persisted history (projects/tasks/agents) is business-scoped.
    mgr = get_manager()
    pending_gates = mgr.gate_manager.list_pending()
    return {
        "tasks_today": len(today_tasks),
        "tasks_done": sum(1 for t in today_tasks if t["status"] == "done"),
        "blocked": sum(1 for t in today_tasks if t["status"] == "blocked"),
        "gates_pending": len(pending_gates),
        "task_titles": [t["title"] for t in today_tasks if t["status"] != "done"][:8],
        "gate_reasons": [g.reason for g in pending_gates][:5],
    }


@router.get("/today")
async def briefing_today(request: Request, refresh: bool = False, ctx: CurrentContext = Depends(current_context)):
    now = time.monotonic()
    cache_key = ctx.business_id
    cached = _cache.get(cache_key)
    if cached and not refresh and now - cached.get("at", 0) < CACHE_TTL_S:
        return {**cached["payload"], "cached": True}

    stats = await _gather_stats(ctx.business_id)
    spend_tracker = getattr(request.app.state, "spend_tracker", None)
    spend_today = round(spend_tracker.total_today(), 2) if spend_tracker else 0.0

    brain = getattr(request.app.state, "brain", None)
    active = await brain.describe() if brain else {"ready": False}

    headline = _fallback_headline(stats)
    source = "fallback"
    if active["ready"]:
        try:
            prompt = (
                "You are Dexter. Write ONE short, warm, confident briefing sentence for the Commander's "
                "Home screen, in Dexter's voice. Use ONLY these real facts — never invent a project name, "
                "a number, or a task you weren't given:\n"
                f"- Tasks today: {stats['tasks_today']} (done: {stats['tasks_done']}, blocked: {stats['blocked']})\n"
                f"- Open task titles: {', '.join(stats['task_titles']) or 'none'}\n"
                f"- Pending approval gates: {stats['gates_pending']}"
                + (f" ({'; '.join(stats['gate_reasons'])})" if stats["gate_reasons"] else "") + "\n"
                f"- Spend today: ${spend_today:.2f}\n"
                "Reply with just the sentence, no preamble, no quotes."
            )
            response = await brain.chat([{"role": "user", "content": prompt}])
            text = (response.get("message", {}).get("content") or "").strip()
            if text:
                headline = text
                source = "brain"
        except Exception as e:
            log.warning("Briefing generation failed, using fallback: %s", e)

    payload = {
        "headline": headline,
        "source": source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {**stats, "spend_today": spend_today},
    }
    _cache[cache_key] = {"payload": payload, "at": now}
    return {**payload, "cached": False}
