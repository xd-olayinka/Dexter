"""Operational surfaces the PRD describes that had no backend yet:

- Run log (PRD §5.4 Shadow "chronological ops log with guard trips and terminations, every
  action explained") — `GET /api/ops/runlog`, from task history, tool calls and ledger alerts.
- Hold (PRD §5.6 quick action "hold") — `POST /api/ops/hold`: while on, every newly delegated
  task parks at an approval gate ("Commander hold") instead of running.
- Spawn templates (PRD §5.3 / §6 "spawner creates executor sub-agents from templates") — saved
  task presets (tier, budget, minutes saved, priority) you spawn from in one click.
- Standing preferences (the FactStore had no writer) — "remember that …", "from now on …",
  "always/never …", "I prefer …" in chat are saved per business and fed back into every chat.
- Prometheus workload (PRD §5.4 team load) — `GET /api/ops/prometheus/workload` via the MCP bridge.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import CurrentContext, current_context
from db.connection import get_pool

log = logging.getLogger("dexter.ops")

router = APIRouter(prefix="/api/ops", tags=["ops"])

# ---------------------------------------------------------------- hold (per business, in-process)

_hold: dict[str | None, bool] = {}


def is_on_hold(business_id: str | None) -> bool:
    return _hold.get(business_id, False)


class HoldIn(BaseModel):
    on: bool


@router.get("/hold")
async def get_hold(ctx: CurrentContext = Depends(current_context)):
    return {"on": is_on_hold(ctx.business_id)}


@router.post("/hold")
async def set_hold(body: HoldIn, ctx: CurrentContext = Depends(current_context)):
    _hold[ctx.business_id] = body.on
    return {"on": body.on}


# ---------------------------------------------------------------- standing preferences

_REMEMBER = [
    re.compile(r"^\s*(?:please\s+)?remember(?:\s+that)?\s+(?P<s>.{3,300}?)[.!]?\s*$", re.I),
    re.compile(r"^\s*(?:from now on|going forward)[,:]?\s+(?P<s>.{3,300}?)[.!]?\s*$", re.I),
    re.compile(r"^\s*(?P<s>(?:always|never)\s+.{3,300}?)[.!]?\s*$", re.I),
    re.compile(r"^\s*(?P<s>i\s+(?:prefer|like|want|don't want|do not want)\s+.{3,300}?)[.!]?\s*$", re.I),
    re.compile(r"^\s*(?P<s>my\s+[\w\s]{2,40}?\s+is\s+.{2,200}?)[.!]?\s*$", re.I),
]
_FORGET = re.compile(r"^\s*(?:please\s+)?forget(?:\s+that)?\s+(?P<s>.{3,300}?)[.!]?\s*$", re.I)


def extract_standing_fact(text: str) -> str | None:
    """A statement worth keeping as a standing preference, or None. Questions never count."""
    t = text.strip()
    if not t or t.endswith("?") or "\n" in t:
        return None
    for rx in _REMEMBER:
        m = rx.match(t)
        if m:
            return m.group("s").strip()
    return None


def extract_forget(text: str) -> str | None:
    m = _FORGET.match(text.strip())
    return m.group("s").strip() if m else None


def _fact_key(business_id: str | None, statement: str) -> str:
    digest = hashlib.sha1(statement.lower().encode("utf-8")).hexdigest()[:16]
    return f"{business_id or 'default'}::{digest}"


async def remember(fact_store, business_id: str | None, statement: str) -> bool:
    try:
        await fact_store.set_fact("standing", _fact_key(business_id, statement), statement, {"business_id": business_id})
        return True
    except Exception as e:
        log.info("Could not save standing fact (no database?): %s", e)
        return False


async def standing_facts(fact_store, business_id: str | None) -> list[dict]:
    try:
        rows = await fact_store.list_facts("standing")
    except Exception:
        return []
    prefix = f"{business_id or 'default'}::"
    return [r for r in rows if r["key"].startswith(prefix)]


async def forget(fact_store, business_id: str | None, phrase: str) -> int:
    """Deactivate standing facts containing the phrase (case-insensitive)."""
    n = 0
    for f in await standing_facts(fact_store, business_id):
        if phrase.lower() in f["value"].lower():
            await fact_store.delete_fact("standing", f["key"])
            n += 1
    return n


def standing_note(facts: list[dict]) -> dict | None:
    if not facts:
        return None
    lines = "\n".join(f"- {f['value']}" for f in facts[:30])
    return {"role": "system", "content": f"The Commander's standing preferences (follow these unless told otherwise):\n{lines}"}


@router.get("/facts")
async def list_standing(request: Request, ctx: CurrentContext = Depends(current_context)):
    return await standing_facts(request.app.state.fact_store, ctx.business_id)


@router.delete("/facts/{key}", status_code=204)
async def delete_standing(key: str, request: Request, ctx: CurrentContext = Depends(current_context)):
    if not key.startswith(f"{ctx.business_id or 'default'}::"):
        raise HTTPException(status_code=404, detail="Not found")
    await request.app.state.fact_store.delete_fact("standing", key)


# ---------------------------------------------------------------- run log

@router.get("/runlog")
async def runlog(limit: int = 40, ctx: CurrentContext = Depends(current_context)):
    """Every executor event, newest first, each with its reason/cost — from persisted history when
    Postgres is up, otherwise from this process's tasks."""
    import ledger
    from shadow.router import get_manager

    events: list[dict] = []
    pool = await get_pool()
    if pool is not None:
        try:
            async with pool.connection() as conn:
                cur = await conn.execute(
                    """SELECT id, title, status, spend, created_at, completed_at, error, model_route, was_gated
                       FROM task_log WHERE business_id IS NOT DISTINCT FROM %s ORDER BY created_at DESC LIMIT %s""",
                    (ctx.business_id, limit),
                )
                for r in await cur.fetchall():
                    tid, title, status, spend, created, done, error, route, gated = r
                    events.append({"at": created.isoformat(), "kind": "spawn", "task_id": tid, "title": title,
                                   "detail": f"spawned on {route}" if route else "spawned"})
                    if done:
                        kind = "done" if status == "done" else "killed" if status in ("killed", "failed") else status
                        events.append({"at": done.isoformat(), "kind": kind, "task_id": tid, "title": title,
                                       "detail": (error or ("completed" + (" after a gate" if gated else ""))) + f" · ${float(spend or 0):.4f}"})
                cur = await conn.execute(
                    """SELECT c.task_id, c.tool_name, c.success, c.created_at, t.title FROM agent_tool_calls c
                       JOIN task_log t ON t.id = c.task_id
                       WHERE t.business_id IS NOT DISTINCT FROM %s ORDER BY c.created_at DESC LIMIT %s""",
                    (ctx.business_id, limit),
                )
                for tid, tool, ok, at, title in await cur.fetchall():
                    events.append({"at": at.isoformat(), "kind": "tool" if ok else "tool_error", "task_id": tid, "title": title,
                                   "detail": f"{'called' if ok else 'failed calling'} {tool}"})
        except Exception as e:
            log.warning("run log query failed: %s", e)
            events = []
    if not events:
        for t in get_manager().list_all():
            if t.metadata.get("business_id") != ctx.business_id:
                continue
            events.append({"at": t.created_at.isoformat(), "kind": "spawn", "task_id": t.id, "title": t.title,
                           "detail": f"spawned on {t.metadata.get('model_route') or 'default brain'}"})
            if t.completed_at:
                events.append({"at": t.completed_at.isoformat(), "kind": t.status.value, "task_id": t.id, "title": t.title,
                               "detail": (t.error or "completed") + f" · ${t.spend:.4f}"})
    for g in get_manager().gate_manager.list_pending():
        events.append({"at": g.created_at.isoformat(), "kind": "gated", "task_id": g.task_id, "title": g.task_title, "detail": g.reason})
    import gate_voter
    for v in gate_voter.recent:
        if v["business_id"] in (ctx.business_id, None):
            events.append({"at": v["at"], "kind": "vote", "task_id": None, "title": v["title"], "detail": v["detail"]})
    for a in ledger.recent_alerts(ctx.business_id):
        events.append({"at": a["at"], "kind": "alert", "task_id": None, "title": a["title"], "detail": a["body"]})
    events.sort(key=lambda e: e["at"], reverse=True)
    return events[:limit]


# ---------------------------------------------------------------- spawn templates

class TemplateIn(BaseModel):
    name: str
    description: str = ""
    tier: int | None = None
    budget_cap: float | None = None
    minutes_saved: int | None = None
    priority: str | None = None


async def _pool_or_503():
    pool = await get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not configured — templates need PostgreSQL")
    return pool


def _tpl(r) -> dict:
    return {"id": r[0], "name": r[1], "description": r[2], "tier": r[3], "budget_cap": float(r[4]) if r[4] is not None else None,
            "minutes_saved": r[5], "priority": r[6]}


@router.get("/templates")
async def list_templates(ctx: CurrentContext = Depends(current_context)):
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT id, name, description, tier, budget_cap, minutes_saved, priority FROM spawn_templates
               WHERE business_id IS NOT DISTINCT FROM %s ORDER BY name""",
            (ctx.business_id,),
        )
        return [_tpl(r) for r in await cur.fetchall()]


@router.post("/templates", status_code=201)
async def create_template(body: TemplateIn, ctx: CurrentContext = Depends(current_context)):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name required")
    pool = await _pool_or_503()
    tid = f"tpl_{uuid.uuid4().hex[:8]}"
    async with pool.connection() as conn:
        await conn.execute(
            """INSERT INTO spawn_templates (id, business_id, name, description, tier, budget_cap, minutes_saved, priority)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (tid, ctx.business_id, body.name.strip(), body.description, body.tier, body.budget_cap, body.minutes_saved, body.priority),
        )
    return {"id": tid, **body.model_dump()}


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: str, ctx: CurrentContext = Depends(current_context)):
    pool = await _pool_or_503()
    async with pool.connection() as conn:
        await conn.execute("DELETE FROM spawn_templates WHERE id = %s AND business_id IS NOT DISTINCT FROM %s", (template_id, ctx.business_id))


class SpawnFromTemplate(BaseModel):
    title: str | None = None
    description: str | None = None


@router.post("/templates/{template_id}/spawn")
async def spawn_template(template_id: str, body: SpawnFromTemplate, request: Request, ctx: CurrentContext = Depends(current_context)):
    from models import Task
    from shadow.guard_config import guard_config_store
    from shadow.router import spawn_selected

    pool = await _pool_or_503()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """SELECT id, name, description, tier, budget_cap, minutes_saved, priority FROM spawn_templates
               WHERE id = %s AND business_id IS NOT DISTINCT FROM %s""",
            (template_id, ctx.business_id),
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    t = _tpl(row)
    config = await guard_config_store.get()
    task = Task(
        title=body.title or t["name"], description=body.description if body.description is not None else t["description"],
        budget_cap=t["budget_cap"] or config.per_task_budget_default,
        metadata={"business_id": ctx.business_id, "owner_user_id": ctx.user_id, "tier": t["tier"],
                  "minutes_saved": t["minutes_saved"], "priority": t["priority"], "template_id": t["id"]},
    )
    await spawn_selected(request.app, task, ctx.business_id, ctx.user_id, t["tier"])
    return task.model_dump(mode="json")


# ---------------------------------------------------------------- chat-proposed changes (chat_tools.py)

@router.post("/actions/{action_id}/confirm")
async def confirm_action(action_id: str, ctx: CurrentContext = Depends(current_context)):
    import chat_tools

    p = chat_tools.take(action_id, ctx.business_id)
    if p is None:
        raise HTTPException(status_code=404, detail="That proposal expired or was already handled — ask Dexter again")
    try:
        result = await chat_tools.perform(p)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Prometheus refused it: {e}")
    return {"ok": True, "summary": p["summary"], "result": result}


@router.delete("/actions/{action_id}", status_code=204)
async def dismiss_action(action_id: str, ctx: CurrentContext = Depends(current_context)):
    import chat_tools

    chat_tools.take(action_id, ctx.business_id)


# ---------------------------------------------------------------- Prometheus workload (team load)

@router.get("/prometheus/workload")
async def prometheus_workload(ctx: CurrentContext = Depends(current_context)):
    from tools.prometheus_tools import get_client

    client = get_client()
    if client is None:
        return {"connected": False, "teams": []}
    try:
        teams = await client.list_teams()
        rows = teams.get("teams", teams) if isinstance(teams, dict) else teams
        out = []
        for t in rows or []:
            tid = t.get("id")
            if not tid:
                continue
            wl = await client.get_workload(team_id=tid)
            out.append({"team": t.get("name") or t.get("key") or tid, "members": wl.get("members", wl) if isinstance(wl, dict) else wl})
        return {"connected": True, "teams": out}
    except Exception as e:
        log.warning("Prometheus workload failed: %s", e)
        return {"connected": True, "teams": [], "error": str(e)}
