"""Dependency map (PRD §4's `Dependency` object: "edge linking business ↔ team ↔
agent ↔ tool; powers the dependency map"; deferred out of the first Phase 3/4 pass —
see docs/PHASE_3_4_PLAN.md §5 — because it needed a design decision, not just code).

The design: business → members (who owns what) → agents (real rows, §2) → tools each
agent has *actually called* (real rows from `agent_tool_calls`, added alongside this).
Every edge here is something that happened, not a guess — an agent that never called a
tool has an empty `tools_used`, not a fabricated "might use" list. This keeps faith with
NFR-4 (Explainable: every action logged with its reason) and NFR-6 (Honesty: no
placeholder data) — the two NFRs a graph of "what's connected to what" would be easiest
to cheat on with a nicer-looking fake.

Deliberately a structured JSON tree, not a force-directed graph render: for a handful
of members and a bounded recent-agent window, a labeled hierarchy is more legible than
node-and-edge physics, and it's honest about what this data actually is — nesting, not
a dense many-to-many mesh (an agent belongs to exactly one owner; a tool call belongs to
exactly one agent). The frontend renders it as nested cards.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import CurrentContext, current_context
from db.connection import get_pool
from status import get_prometheus_client
from tools.registry import registry

router = APIRouter(prefix="/api/dependencies", tags=["dependencies"])

RECENT_AGENTS_LIMIT = 30


@router.get("/map")
async def dependency_map(ctx: CurrentContext = Depends(current_context)) -> dict:
    pool = await get_pool()
    members: list[dict] = []
    agents: list[dict] = []
    tool_calls_by_task: dict[str, list[str]] = {}

    if pool is not None:
        async with pool.connection() as conn:
            cur = await conn.execute(
                """SELECT u.id, u.name, u.email, bm.role FROM business_members bm JOIN users u ON u.id = bm.user_id
                   WHERE bm.business_id = %s ORDER BY bm.joined_at ASC""",
                (ctx.business_id,),
            )
            members = [{"id": r[0], "name": r[1] or r[2], "role": r[3]} for r in await cur.fetchall()]

            cur = await conn.execute(
                """SELECT id, name, status, owner_user_id, task_id FROM agents
                   WHERE business_id = %s ORDER BY created_at DESC LIMIT %s""",
                (ctx.business_id, RECENT_AGENTS_LIMIT),
            )
            agent_rows = await cur.fetchall()
            agents = [{"id": r[0], "name": r[1], "status": r[2], "owner_user_id": r[3], "task_id": r[4]} for r in agent_rows]

            task_ids = [a["task_id"] for a in agents]
            if task_ids:
                cur = await conn.execute(
                    "SELECT DISTINCT task_id, tool_name FROM agent_tool_calls WHERE task_id = ANY(%s)",
                    (task_ids,),
                )
                for task_id, tool_name in await cur.fetchall():
                    tool_calls_by_task.setdefault(task_id, []).append(tool_name)

    for a in agents:
        a["tools_used"] = sorted(tool_calls_by_task.get(a["task_id"], []))

    members_by_id = {m["id"]: m for m in members}
    for a in agents:
        owner = members_by_id.get(a["owner_user_id"])
        a["owner_name"] = owner["name"] if owner else None

    prometheus = get_prometheus_client()
    all_tool_names = registry.list_tools()
    tools = [
        {
            "name": name,
            "kind": "integration" if name.startswith("prometheus_") else "builtin",
            "connected": (prometheus is not None) if name.startswith("prometheus_") else None,
            "used_by_agents": sum(1 for a in agents if name in a["tools_used"]),
        }
        for name in all_tool_names
    ]

    return {
        "business": {"id": ctx.business_id, "name": ctx.business_name},
        "members": members,
        "agents": agents,
        "tools": tools,
    }
