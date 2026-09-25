"""Selector Core (PRD §1, §5.3): picks the cheapest capable model for each Anthony task.

  1. Required capability tier from the task text (escalation/classifier.py: fast → 1,
     local → 2, cloud → 3), or an explicit tier the Commander passes when delegating.
  2. Candidates = every configured model on every configured provider (catalog below), each
     with a tier, tool-calling support and a price from its provider.
  3. Filtered by: available now, tier ≥ required, tool support (Anthony's loop needs tools),
     provider monthly caps and the monthly/daily budget (ledger.py). Models with a poor record
     (≥ MIN_RUNS runs, success < MIN_SUCCESS) are dropped — "fittest survive" — unless nothing
     else qualifies.
  4. Ranked by expected cost per *successful* run (estimated cost ÷ observed success rate),
     then observed latency, then the lowest sufficient tier.

`select()` returns the pick plus every candidate considered with its reason, which the Swarm
screen shows. `SelectedBrain` then runs the task's tool loop on that model through the
gateway, recording each call's cost to the ledger and enforcing caps before every call.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field

from config import settings
from db.connection import get_pool
from escalation.classifier import TaskClassifier
from models import EscalationLevel

log = logging.getLogger("dexter.shadow.selector")

MIN_RUNS = 5
MIN_SUCCESS = 0.5
PRIOR_SUCCESS = 0.8          # untried models start here — optimistic, so new models get tried
EST_ROUNDS = 3               # typical tool-loop rounds per task
EST_OVERHEAD_TOKENS = 1500   # system prompt + tool schemas per round
EST_OUTPUT_TOKENS = 700      # per round

_LEVEL_TIER = {EscalationLevel.FAST: 1, EscalationLevel.LOCAL: 2, EscalationLevel.CLOUD: 3}


@dataclass
class Candidate:
    provider: str
    model: str
    tier: int
    tools: bool = True

    @property
    def route(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass
class Stats:
    runs: int = 0
    successes: int = 0
    avg_seconds: float | None = None

    @property
    def success_rate(self) -> float:
        return self.successes / self.runs if self.runs else PRIOR_SUCCESS


@dataclass
class Considered:
    route: str
    tier: int
    est_cost: float
    success_rate: float
    runs: int
    eligible: bool
    reason: str


@dataclass
class Selection:
    provider: str
    model: str
    tier: int
    required_tier: int
    est_cost: float
    reason: str
    considered: list[Considered] = field(default_factory=list)

    @property
    def route(self) -> str:
        return f"{self.provider}:{self.model}"

    def as_dict(self) -> dict:
        d = asdict(self)
        d["route"] = self.route
        return d


def catalog() -> list[Candidate]:
    """Every model the Selector may use. Claude tiers: Haiku 4.5 (1), Sonnet 5 (2), the configured
    Opus model (3); Fable 5.1 only when DEXTER_SELECTOR_ALLOW_FABLE is on (2x Opus price)."""
    c = [
        Candidate("ollama", settings.ollama_fast_model, 1, tools=False),
        Candidate("ollama", settings.ollama_model, 2),
        Candidate("groq", "llama-3.3-70b-versatile", 2),
        Candidate("deepseek", settings.deepseek_model, 2),
        Candidate("deepseek", settings.deepseek_reasoner_model, 3, tools=False),
        Candidate("anthropic", "claude-haiku-4-5", 1),
        Candidate("anthropic", "claude-sonnet-5", 2),
        Candidate("anthropic", settings.anthropic_model, 3),
        Candidate("openai", settings.openai_model, 3),
    ]
    if settings.selector_allow_fable:
        c.append(Candidate("anthropic", "claude-fable-5-1", 3))
    seen: set[str] = set()
    return [x for x in c if not (x.route in seen or seen.add(x.route))]


def required_tier(text: str, explicit: int | None = None) -> int:
    if explicit in (1, 2, 3):
        return explicit
    return _LEVEL_TIER[TaskClassifier().classify(text, None)]


def estimate_tokens(text: str) -> tuple[int, int]:
    per_round_in = EST_OVERHEAD_TOKENS + len(text) // 4
    return per_round_in * EST_ROUNDS, EST_OUTPUT_TOKENS * EST_ROUNDS


def rank(
    candidates: list[Candidate], need_tier: int, needs_tools: bool, available: set[str],
    prices: dict[str, float], stats: dict[str, Stats], budget: dict,
) -> tuple[Candidate | None, list[Considered]]:
    """Pure ranking — unit-tested. `prices` = estimated cost per route; `budget` = ledger.remaining()."""
    considered: list[tuple[Candidate, Considered, bool]] = []
    for cand in candidates:
        st = stats.get(cand.route, Stats())
        cost = prices.get(cand.route, 0.0)
        reason = ""
        if cand.provider not in available:
            reason = "provider not configured / unreachable"
        elif cand.tier < need_tier:
            reason = f"tier {cand.tier} < required {need_tier}"
        elif needs_tools and not cand.tools:
            reason = "no tool calling"
        elif cost > 0 and budget["providers"].get(cand.provider, float("inf")) <= 0:
            reason = f"{cand.provider} monthly cap reached"
        elif cost > 0 and (budget["month"] <= 0 or budget["today"] <= 0):
            reason = "budget exhausted — free models only"
        elif cost > min(budget["month"], budget["today"]):
            reason = f"estimated ${cost:.4f} exceeds remaining budget"
        weak = st.runs >= MIN_RUNS and st.success_rate < MIN_SUCCESS
        considered.append((cand, Considered(cand.route, cand.tier, round(cost, 6), round(st.success_rate, 3), st.runs, not reason, reason), weak))

    eligible = [(c, k, w) for c, k, w in considered if k.eligible]
    fit = [(c, k, w) for c, k, w in eligible if not w] or eligible  # fittest survive, unless nothing else is left
    for c, k, w in eligible:
        if w and (c, k, w) not in fit:
            k.eligible, k.reason = False, f"retired: {k.success_rate:.0%} success over {k.runs} runs"

    def key(item):
        cand, k, _ = item
        st = stats.get(cand.route, Stats())
        return (k.est_cost / max(k.success_rate, 0.25), st.avg_seconds if st.avg_seconds is not None else 60.0, cand.tier)

    fit.sort(key=key)
    return (fit[0][0] if fit else None), [k for _, k, _ in considered]


async def load_stats(business_id: str | None) -> dict[str, Stats]:
    """Per-route history from task_log (success = done; failure = killed/failed)."""
    out: dict[str, Stats] = {}
    pool = await get_pool()
    if pool is not None:
        try:
            async with pool.connection() as conn:
                cur = await conn.execute(
                    """SELECT model_route, COUNT(*), COUNT(*) FILTER (WHERE status = 'done'),
                              AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) FILTER (WHERE status = 'done')
                       FROM task_log
                       WHERE model_route IS NOT NULL AND status IN ('done', 'killed', 'failed')
                         AND business_id IS NOT DISTINCT FROM %s AND created_at > now() - interval '60 days'
                       GROUP BY model_route""",
                    (business_id,),
                )
                for route, runs, ok, secs in await cur.fetchall():
                    out[route] = Stats(int(runs), int(ok), float(secs) if secs is not None else None)
            return out
        except Exception as e:
            log.warning("Selector stats query failed, using in-memory history: %s", e)
    from shadow.router import get_manager

    for t in get_manager().list_all():
        route = t.metadata.get("model_route")
        if not route or t.metadata.get("business_id") != business_id or t.status.value not in ("done", "killed", "failed"):
            continue
        st = out.setdefault(route, Stats())
        st.runs += 1
        if t.status.value == "done":
            st.successes += 1
            if t.completed_at:
                secs = (t.completed_at - t.created_at).total_seconds()
                st.avg_seconds = secs if st.avg_seconds is None else (st.avg_seconds * (st.successes - 1) + secs) / st.successes
    return out


class ModelGateway:
    """One chat() over every provider, Ollama included, in Ollama's normalized shape."""

    def __init__(self, ollama, providers: dict) -> None:
        self.ollama = ollama
        self.providers = providers
        self._ollama_ok = False
        self._ollama_checked = 0.0

    async def available_providers(self) -> set[str]:
        out = {name for name, p in self.providers.items() if await p.available()}
        now = time.monotonic()
        if now - self._ollama_checked > 30:
            self._ollama_ok = await self.ollama.health()
            self._ollama_checked = now
        if self._ollama_ok:
            out.add("ollama")
        return out

    def price(self, provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
        if provider == "ollama":
            return 0.0
        return self.providers[provider].estimate_cost_for(model, tokens_in, tokens_out)

    async def chat(self, provider: str, model: str, messages: list[dict], tools: list[dict] | None = None) -> dict:
        if provider == "ollama":
            return await self.ollama.chat(messages, model=model, tools=tools)
        return await self.providers[provider].chat(messages, model=model, tools=tools)


async def select(gateway: ModelGateway, text: str, business_id: str | None, explicit_tier: int | None = None) -> Selection | None:
    from ledger import remaining

    need = required_tier(text, explicit_tier)
    cands = catalog()
    tin, tout = estimate_tokens(text)
    available = await gateway.available_providers()
    prices = {c.route: gateway.price(c.provider, c.model, tin, tout) for c in cands if c.provider in available}
    stats = await load_stats(business_id)
    budget = await remaining(business_id)
    pick, considered = rank(cands, need, True, available, prices, stats, budget)
    if pick is None:
        # Nothing at or above the needed tier: take the best lower-tier model rather than refusing,
        # and say so — the Commander can still kill it or raise the budget.
        for lower in range(need - 1, 0, -1):
            pick, considered = rank(cands, lower, True, available, prices, stats, budget)
            if pick:
                break
        if pick is None:
            return None
    st = stats.get(pick.route, Stats())
    est = prices.get(pick.route, 0.0)
    why = (
        f"tier {pick.tier} for a tier-{need} task · est ${est:.4f} · "
        f"{'untried' if not st.runs else f'{st.success_rate:.0%} success over {st.runs} runs'} · "
        f"cheapest capable of {sum(1 for k in considered if k.eligible)} eligible"
    )
    if pick.tier < need:
        why = f"no tier-{need} model within budget — downgraded; " + why
    return Selection(pick.provider, pick.model, pick.tier, need, est, why, considered)


class CapReached(RuntimeError):
    pass


class SelectedBrain:
    """What a task's tool loop calls: runs on the selected model, records spend to the ledger,
    and refuses the next call once a hard cap is hit (the executor then kills the task and logs why)."""

    def __init__(self, gateway: ModelGateway, selection: Selection, business_id: str | None, agent_id: str) -> None:
        self.gateway = gateway
        self.selection = selection
        self.business_id = business_id
        self.agent_id = agent_id

    async def _check_caps(self) -> None:
        from ledger import agent_spend_today, remaining
        from shadow.guard_config import guard_config_store

        if self.selection.provider == "ollama":
            return
        cfg = await guard_config_store.get()
        rem = await remaining(self.business_id)
        if rem["month"] <= 0:
            raise CapReached("Monthly budget reached")
        if rem["providers"].get(self.selection.provider, float("inf")) <= 0:
            raise CapReached(f"{self.selection.provider} monthly cap reached")
        if cfg.agent_daily_cap is not None and await agent_spend_today(self.agent_id) >= cfg.agent_daily_cap:
            raise CapReached(f"Agent daily cap reached (${cfg.agent_daily_cap:.2f})")

    async def chat(self, messages: list[dict], tools: list[dict] | None = None, task_id: str | None = None, **_) -> dict:
        from ledger import record

        await self._check_caps()
        sel = self.selection
        response = await self.gateway.chat(sel.provider, sel.model, messages, tools=tools)
        usage = response.get("usage") or {}
        tin = usage.get("input_tokens", usage.get("prompt_tokens", usage.get("prompt_eval_count", 0))) or 0
        tout = usage.get("output_tokens", usage.get("completion_tokens", usage.get("eval_count", 0))) or 0
        cost = self.gateway.price(sel.provider, sel.model, tin, tout)
        await record(self.business_id, sel.provider, sel.model, tin, tout, cost, task_id=task_id, agent_id=self.agent_id)
        response["cost_usd"] = cost
        return response
