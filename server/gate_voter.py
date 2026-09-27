"""Anthony votes on Prometheus's automated gates by itself.

Prometheus gates of type `agent_check`/`consensus` wait for votes from their assigned agents. Before
this, Anthony only voted when a task explicitly asked it to, so those gates sat. Now a background
loop asks Prometheus for checks addressed to this agent (`my_gate_checks`) every
DEXTER_GATE_VOTE_INTERVAL seconds, reads the issue, has the brain judge it against the gate's
instructions, and reports pass/fail with its reasoning (`report_gate_check`).

It never guesses: an unparseable judgement, a missing issue, or a spent monthly budget means no vote
(the gate falls back to its humans / fallback agent as Prometheus already handles).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import deque
from datetime import datetime, timezone

from config import settings

log = logging.getLogger("dexter.gate_voter")

# (proposalId, gateId) already handled by this process — a vote is final, a skip is retried
# only after the proposal changes (Prometheus drops it from my_gate_checks once settled).
_done: set[tuple[str, str]] = set()
recent: deque[dict] = deque(maxlen=50)  # shown in the run log

VOTE_PROMPT = """You are ANTHONY, an automated reviewer voting on a Prometheus approval gate.

Gate type: {gate_type}
Gate instructions (what must be true to pass):
{instructions}

The issue wants to move to state "{to_state}". Here is the issue:

{issue}

Judge ONLY against the gate instructions. If the issue gives no evidence the requirement is met,
vote fail and say what is missing. Reply with a single JSON object and nothing else:
{{"verdict": "pass" or "fail", "reason": "<one or two sentences>"}}"""


def parse_verdict(text: str) -> tuple[str, str] | None:
    """Pull {"verdict","reason"} out of a model reply; None if it isn't a clear pass/fail."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in ("pass", "fail"):
        return None
    return verdict, str(data.get("reason", "")).strip()[:500]


async def _billing_business() -> str | None:
    """Gate votes are Anthony's own work for the workspace owner: bill the first business."""
    from db.connection import get_pool

    pool = await get_pool()
    if pool is None:
        return None
    try:
        async with pool.connection() as conn:
            cur = await conn.execute("SELECT id FROM businesses ORDER BY created_at ASC LIMIT 1")
            row = await cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None


async def vote_once(app) -> int:
    """One sweep. Returns how many votes were cast."""
    import ledger
    from tools.prometheus_tools import get_client

    client = get_client()
    brain = getattr(app.state, "brain", None)
    if client is None or brain is None or not (await brain.describe())["ready"]:
        return 0
    try:
        checks = (await client.my_gate_checks()).get("checks", [])
    except Exception as e:
        log.info("my_gate_checks failed: %s", e)
        return 0

    business_id = await _billing_business()
    cast = 0
    for c in checks:
        key = (c.get("proposalId", ""), c.get("gateId", ""))
        if c.get("yourVote") or key in _done:
            continue
        left = await ledger.remaining(business_id)
        if left["month"] <= 0 or left["today"] <= 0:
            log.info("Budget spent — not voting on %s", key)
            return cast
        try:
            issue = await client.get_issue(c["issueId"])
        except Exception as e:
            log.info("Could not read issue %s: %s", c.get("issueId"), e)
            continue
        body = issue.get("markdown") or json.dumps(issue, default=str)[:6000]
        prompt = VOTE_PROMPT.format(
            gate_type=c.get("gateType", ""), instructions=c.get("instructions") or "(none given — judge general readiness)",
            to_state=c.get("toState", ""), issue=body[:8000],
        )
        try:
            reply = await brain.chat([{"role": "user", "content": prompt}], business_id=business_id, source="gate_vote")
        except Exception as e:
            log.info("Brain failed on gate %s: %s", key, e)
            continue
        parsed = parse_verdict((reply.get("message") or {}).get("content", ""))
        if not parsed:
            log.info("No clear verdict for gate %s — leaving it for humans", key)
            continue
        verdict, reason = parsed
        try:
            await client.report_gate_check(key[0], key[1], verdict, f"Anthony: {reason}")
        except Exception as e:
            log.info("report_gate_check failed for %s: %s", key, e)
            continue
        _done.add(key)
        cast += 1
        recent.appendleft({
            "at": datetime.now(timezone.utc).isoformat(), "business_id": business_id,
            "title": f"{c.get('identifier') or c.get('issueId')} · {c.get('title') or ''}".strip(" ·"),
            "detail": f"voted {verdict} on {c.get('gateType')} gate → {c.get('toState')}: {reason}",
        })
        log.info("Voted %s on %s", verdict, key)
    return cast


async def run_forever(app) -> None:
    interval = settings.gate_vote_interval
    if interval <= 0:
        return
    await asyncio.sleep(10)  # let startup settle
    while True:
        try:
            await vote_once(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("gate voter sweep failed")
        await asyncio.sleep(interval)
