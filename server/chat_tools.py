"""Tools for Dexter's chat (docs/PROMETHEUS_MCP_SPEC.md §2: Dexter reads, Anthony writes).

Chat gets the read-only tools — Prometheus reads, web search, the browser, the clock — and runs
them without asking. Anything that would change Prometheus goes through `propose_action`: the
model describes the change, the Commander sees it as a card with Confirm, and only
POST /api/ops/actions/{id}/confirm performs it. Nothing is written from chat on the model's say-so.
"""
from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from models import ToolCall
from tools import registry
from tools.caller import run_with_tools
from tools.registry import Tool, ToolRegistry

log = logging.getLogger("dexter.chat_tools")

READ_TOOLS = (
    "prometheus_list_issues", "prometheus_get_issue", "prometheus_my_queue", "prometheus_list_dependencies",
    "prometheus_list_projects", "prometheus_get_project", "prometheus_list_teams", "prometheus_get_workload",
    "prometheus_read_resource", "web_search", "browse_url", "current_datetime", "time_until",
)

# Changes the Commander can confirm from chat, and the arguments each needs.
ACTIONS: dict[str, tuple[str, ...]] = {
    "create_issue": ("team_id", "title"),
    "comment_issue": ("issue_id", "body"),
    "transition_issue": ("issue_id", "to_state_id"),
    "update_issue": ("issue_id",),
    "link_issues": ("source_id", "target_id", "type"),
    "pick_issue": ("issue_id",),
}

TOOL_GUIDE = (
    "\n\nYou can look things up with your tools: Prometheus (the team's projects, issues, workload, "
    "dependencies), web search, a browser and the clock. Use them instead of guessing whenever the "
    "Commander asks about their work or anything current. To CHANGE anything in Prometheus (create, "
    "comment, move, update, link, pick up an issue), call propose_action — the Commander confirms it; "
    "never say a change is done until they have. The chat shows plain text: answer in short "
    "sentences and simple dash lists, no tables or Markdown headings."
)

# id -> proposal. Per-process: a proposal is only good for the session that made it.
_pending: dict[str, dict] = {}


def validate_action(kind: str, args: dict) -> str | None:
    if kind not in ACTIONS:
        return f"Unknown action {kind!r}; allowed: {', '.join(ACTIONS)}"
    missing = [a for a in ACTIONS[kind] if not args.get(a)]
    if missing:
        return f"{kind} needs: {', '.join(missing)}"
    if kind == "update_issue" and len(args) < 2:
        return "update_issue needs at least one field to change"
    return None


def make_registry(business_id: str | None, proposals: list[dict]) -> ToolRegistry:
    """This turn's tools: the read-only subset of the global registry plus propose_action,
    whose proposals are collected into `proposals` for the caller to show."""
    reg = ToolRegistry()
    for name in READ_TOOLS:
        t = registry._tools.get(name)
        if t is not None:
            reg.register(t)

    async def propose_action(kind: str, summary: str, args: dict | str) -> str:
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                return "args must be a JSON object"
        err = validate_action(kind, args or {})
        if err:
            return f"Not proposed: {err}"
        pid = f"act_{uuid.uuid4().hex[:10]}"
        p = {"id": pid, "kind": kind, "summary": summary[:300], "args": args,
             "business_id": business_id, "created_at": datetime.now(timezone.utc).isoformat()}
        _pending[pid] = p
        proposals.append({k: p[k] for k in ("id", "kind", "summary", "args")})
        return "Proposed. The Commander now sees a Confirm button for it — tell them what it will do; it is NOT done yet."

    reg.register(Tool(
        name="propose_action",
        description="Propose a change in Prometheus for the Commander to confirm. kind: " + ", ".join(
            f"{k} ({'/'.join(v)})" for k, v in ACTIONS.items()
        ) + ". update_issue also takes the fields to change (description, progress_note, ...).",
        parameters={
            "kind": {"type": "string", "enum": list(ACTIONS)},
            "summary": {"type": "string", "description": "One line the Commander reads, e.g. 'Create \"Fix login\" in ENG'"},
            "args": {"type": "object", "description": "Arguments for the action, e.g. {\"issue_id\": \"...\", \"body\": \"...\"}"},
        },
        handler=propose_action,
    ))
    return reg


class _ChatBrain:
    """Bills chat tool rounds to the business like any chat call."""

    def __init__(self, brain, business_id):
        self._brain, self._business_id = brain, business_id

    async def chat(self, messages, tools=None, **kw):
        return await self._brain.chat(messages, tools=tools, business_id=self._business_id, source="chat")


async def run_turn(brain, messages: list[dict], business_id: str | None,
                   on_status: Callable[[str], Awaitable[None]] | None = None) -> tuple[str, list[dict]]:
    """One chat turn with tools. Returns (reply, proposals)."""
    proposals: list[dict] = []
    reg = make_registry(business_id, proposals)
    msgs = list(messages)
    if msgs and msgs[0].get("role") == "system":
        msgs[0] = {**msgs[0], "content": msgs[0]["content"] + TOOL_GUIDE}

    async def on_tool(name: str) -> None:
        if on_status is None:
            return
        label = ("Checking Prometheus" if name.startswith("prometheus_") else
                 "Searching the web" if name == "web_search" else
                 "Reading a page" if name == "browse_url" else
                 "Drafting a change for you to confirm" if name == "propose_action" else "Working")
        await on_status(f"{label}…")

    reply, _ = await run_with_tools(_ChatBrain(brain, business_id), msgs, reg, max_rounds=5, on_tool=on_tool)
    return reply or "I couldn't finish that — try asking again more specifically.", proposals


def take(action_id: str, business_id: str | None) -> dict | None:
    p = _pending.get(action_id)
    if p is None or p["business_id"] != business_id:
        return None
    return _pending.pop(action_id)


async def perform(p: dict) -> str:
    """Run a confirmed proposal against Prometheus."""
    from tools.prometheus_tools import get_client

    client = get_client()
    if client is None:
        raise RuntimeError("Prometheus isn't connected")
    a = dict(p["args"])
    kind = p["kind"]
    if kind == "create_issue":
        r = await client.create_issue(a.pop("team_id"), a.pop("title"), **a)
    elif kind == "comment_issue":
        r = await client.comment_issue(a["issue_id"], a["body"])
    elif kind == "transition_issue":
        r = await client.transition_issue(a["issue_id"], a["to_state_id"], comment=a.get("comment"))
    elif kind == "update_issue":
        r = await client.update_issue(a.pop("issue_id"), **a)
    elif kind == "link_issues":
        r = await client.link_issues(a["source_id"], a["target_id"], a["type"])
    elif kind == "pick_issue":
        r = await client.pick_issue(a["issue_id"])
    else:
        raise ValueError(kind)
    return json.dumps(r, default=str)[:2000]


__all__ = ["run_turn", "take", "perform", "validate_action", "make_registry", "ToolCall"]
