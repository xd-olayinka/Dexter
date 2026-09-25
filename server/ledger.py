"""Credit ledger (PRD §5.5): one persistent row per model call, per business.

Before this, spend lived in two in-memory trackers that reset on restart, so there could be no
monthly budget, no per-provider or per-agent cap, and no burn-rate alert. Now every call from
executors (shadow/gateway.py), chat and the briefing lands here; totals drive the Credits screen,
the Selector's provider eligibility, the guard chain's agent cap, and phone-push alerts.

Without Postgres it degrades like the rest of the backend: rows are kept in memory (bounded)
and totals are computed from those, so a single-session setup still sees real numbers.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from auth import CurrentContext, current_context
from db.connection import get_pool

log = logging.getLogger("dexter.ledger")

router = APIRouter(prefix="/api/ledger", tags=["ledger"])

_MEMORY_CAP = 5000
ALERT_COOLDOWN_S = 3600


@dataclass
class LedgerRow:
    ts: datetime
    business_id: str | None
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    task_id: str | None = None
    agent_id: str | None = None
    source: str = "executor"


@dataclass
class Totals:
    today: float = 0.0
    month: float = 0.0
    last_hour: float = 0.0
    last_12h: float = 0.0
    by_provider_today: dict[str, float] = field(default_factory=dict)
    by_provider_month: dict[str, float] = field(default_factory=dict)
    by_model_month: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        r = lambda v: round(v, 6)  # noqa: E731
        return {
            "today": r(self.today), "month": r(self.month), "last_hour": r(self.last_hour), "last_12h": r(self.last_12h),
            "by_provider_today": {k: r(v) for k, v in self.by_provider_today.items()},
            "by_provider_month": {k: r(v) for k, v in self.by_provider_month.items()},
            "by_model_month": {k: r(v) for k, v in self.by_model_month.items()},
        }


_memory: deque[LedgerRow] = deque(maxlen=_MEMORY_CAP)
_alerts: deque[dict] = deque(maxlen=100)
_last_alert_at: dict[str, float] = {}


def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _day_start(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def record(
    business_id: str | None, provider: str, model: str, input_tokens: int, output_tokens: int, cost_usd: float,
    task_id: str | None = None, agent_id: str | None = None, source: str = "executor",
) -> None:
    row = LedgerRow(datetime.now(timezone.utc), business_id, provider, model, int(input_tokens or 0),
                    int(output_tokens or 0), float(cost_usd or 0), task_id, agent_id, source)
    _memory.append(row)
    pool = await get_pool()
    if pool is not None:
        try:
            async with pool.connection() as conn:
                await conn.execute(
                    """INSERT INTO spend_ledger (ts, business_id, provider, model, input_tokens, output_tokens,
                              cost_usd, task_id, agent_id, source)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (row.ts, business_id, provider, model, row.input_tokens, row.output_tokens, row.cost_usd,
                     task_id, agent_id, source),
                )
        except Exception as e:
            log.warning("Could not persist ledger row (kept in memory): %s", e)
    if row.cost_usd > 0:
        await check_alerts(business_id)


def _totals_from_rows(rows: list[LedgerRow], now: datetime) -> Totals:
    t = Totals()
    day, month = _day_start(now), _month_start(now)
    hour_ago, h12 = now - timedelta(hours=1), now - timedelta(hours=12)
    for r in rows:
        if r.ts < month:
            continue
        t.month += r.cost_usd
        t.by_provider_month[r.provider] = t.by_provider_month.get(r.provider, 0.0) + r.cost_usd
        t.by_model_month[r.model] = t.by_model_month.get(r.model, 0.0) + r.cost_usd
        if r.ts >= day:
            t.today += r.cost_usd
            t.by_provider_today[r.provider] = t.by_provider_today.get(r.provider, 0.0) + r.cost_usd
        if r.ts >= hour_ago:
            t.last_hour += r.cost_usd
        if r.ts >= h12:
            t.last_12h += r.cost_usd
    return t


async def totals(business_id: str | None, now: datetime | None = None) -> Totals:
    now = now or datetime.now(timezone.utc)
    pool = await get_pool()
    if pool is not None:
        try:
            async with pool.connection() as conn:
                cur = await conn.execute(
                    """SELECT ts, provider, model, cost_usd FROM spend_ledger
                       WHERE business_id IS NOT DISTINCT FROM %s AND ts >= %s""",
                    (business_id, _month_start(now)),
                )
                rows = [LedgerRow(r[0], business_id, r[1], r[2], 0, 0, float(r[3])) for r in await cur.fetchall()]
            return _totals_from_rows(rows, now)
        except Exception as e:
            log.warning("Ledger query failed, using in-memory rows: %s", e)
    return _totals_from_rows([r for r in _memory if r.business_id == business_id], now)


async def agent_spend_today(agent_id: str) -> float:
    """Spend by one executor agent today (the per-agent cap). In-memory rows are authoritative
    for the running process — an agent only lives as long as its task."""
    day = _day_start(datetime.now(timezone.utc))
    return sum(r.cost_usd for r in _memory if r.agent_id == agent_id and r.ts >= day)


async def check_alerts(business_id: str | None) -> list[dict]:
    """Burn-rate and monthly-budget alerts, each at most once per hour, pushed to the phone."""
    from shadow.guard_config import guard_config_store

    cfg = await guard_config_store.get()
    t = await totals(business_id)
    fired: list[dict] = []

    def fire(key: str, title: str, body: str) -> None:
        now = time.monotonic()
        if now - _last_alert_at.get(f"{business_id}:{key}", -1e9) < ALERT_COOLDOWN_S:
            return
        _last_alert_at[f"{business_id}:{key}"] = now
        alert = {"at": datetime.now(timezone.utc).isoformat(), "business_id": business_id, "kind": key, "title": title, "body": body}
        _alerts.appendleft(alert)
        fired.append(alert)

    if cfg.burn_rate_alert_per_hour is not None and t.last_hour > cfg.burn_rate_alert_per_hour:
        fire("burn_rate", "Burn rate alert", f"${t.last_hour:.2f} spent in the last hour (alert above ${cfg.burn_rate_alert_per_hour:.2f}/h)")
    if cfg.monthly_budget > 0:
        pct = t.month / cfg.monthly_budget
        if pct >= 1:
            fire("monthly_100", "Monthly budget reached", f"${t.month:.2f} of ${cfg.monthly_budget:.2f} — cloud models are paused until next month or a raise")
        elif pct >= 0.8:
            fire("monthly_80", "80% of monthly budget", f"${t.month:.2f} of ${cfg.monthly_budget:.2f} used")
    for provider, cap in cfg.provider_monthly_caps.items():
        if cap > 0 and t.by_provider_month.get(provider, 0.0) >= cap:
            fire(f"provider_{provider}", f"{provider} cap reached", f"${t.by_provider_month[provider]:.2f} of ${cap:.2f} this month — the Selector skips {provider} now")

    if fired:
        from shadow.gates import notify_push
        for a in fired:
            await notify_push(a["title"], a["body"])
    return fired


async def remaining(business_id: str | None) -> dict:
    """What the Selector may still spend: monthly headroom and per-provider headroom."""
    from shadow.guard_config import guard_config_store

    cfg = await guard_config_store.get()
    t = await totals(business_id)
    return {
        "month": max(0.0, cfg.monthly_budget - t.month) if cfg.monthly_budget > 0 else float("inf"),
        "today": max(0.0, cfg.daily_budget - t.today),
        "providers": {p: max(0.0, cap - t.by_provider_month.get(p, 0.0)) for p, cap in cfg.provider_monthly_caps.items() if cap > 0},
    }


def recent_alerts(business_id: str | None, limit: int = 20) -> list[dict]:
    return [a for a in _alerts if a["business_id"] == business_id][:limit]


def _reset_for_tests() -> None:
    _memory.clear()
    _alerts.clear()
    _last_alert_at.clear()


@router.get("/summary")
async def ledger_summary(ctx: CurrentContext = Depends(current_context)) -> dict:
    from shadow.guard_config import guard_config_store

    cfg = await guard_config_store.get()
    t = await totals(ctx.business_id)
    projected = None
    now = datetime.now(timezone.utc)
    day_of_month = now.day - 1 + (now.hour / 24)
    if t.month > 0 and day_of_month > 0.25:
        next_month = (_month_start(now) + timedelta(days=32)).replace(day=1)
        days_in_month = (next_month - _month_start(now)).days
        projected = round(t.month / day_of_month * days_in_month, 4)
    return {
        "totals": t.as_dict(),
        "limits": {
            "daily_budget": cfg.daily_budget, "monthly_budget": cfg.monthly_budget,
            "provider_monthly_caps": cfg.provider_monthly_caps, "agent_daily_cap": cfg.agent_daily_cap,
            "burn_rate_alert_per_hour": cfg.burn_rate_alert_per_hour,
        },
        "projected_month": projected,
        "alerts": recent_alerts(ctx.business_id),
    }
