"""Selector Core, credit ledger, hard caps, Anthropic tool normalization, Home headline stats and
Archive retrieval. Like test_smoke.py these run with no Postgres, no Ollama and no API keys —
providers are faked at the gateway so nothing leaves the machine."""
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import ledger
from archive import build_ask_prompt, cited_numbers, parse_script, passages, rank_passages
from escalation.providers import AnthropicProvider
from main import app
from shadow.guard_config import guard_config_store
from shadow.selector import Candidate, CapReached, SelectedBrain, Selection, Stats, rank

INF = float("inf")
OPEN_BUDGET = {"month": INF, "today": INF, "providers": {}}


@pytest.fixture(autouse=True)
def _clean_ledger(monkeypatch):
    async def no_push(*a, **k):
        return None
    monkeypatch.setattr("shadow.gates.notify_push", no_push)  # never hit ntfy.sh from tests
    ledger._reset_for_tests()
    yield
    ledger._reset_for_tests()


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------- Selector ranking

CANDS = [
    Candidate("ollama", "small", 1, tools=False),
    Candidate("ollama", "big", 2),
    Candidate("deepseek", "deepseek-chat", 2),
    Candidate("anthropic", "claude-sonnet-5", 2),
    Candidate("anthropic", "claude-opus-5", 3),
]
PRICES = {"ollama:small": 0, "ollama:big": 0, "deepseek:deepseek-chat": 0.002, "anthropic:claude-sonnet-5": 0.03, "anthropic:claude-opus-5": 0.08}


def test_selector_picks_the_cheapest_capable_model():
    pick, considered = rank(CANDS, 2, True, {"ollama", "deepseek", "anthropic"}, PRICES, {}, OPEN_BUDGET)
    assert pick.route == "ollama:big"  # free and tier 2
    reasons = {k.route: k.reason for k in considered}
    assert reasons["ollama:small"].startswith("tier 1 < required 2")


def test_selector_needs_tier_three_for_hard_tasks_and_skips_unavailable():
    pick, _ = rank(CANDS, 3, True, {"deepseek", "anthropic"}, PRICES, {}, OPEN_BUDGET)
    assert pick.route == "anthropic:claude-opus-5"
    pick, _ = rank(CANDS, 2, True, {"deepseek", "anthropic"}, PRICES, {}, OPEN_BUDGET)
    assert pick.route == "deepseek:deepseek-chat"


def test_selector_retires_models_with_a_poor_record():
    stats = {"ollama:big": Stats(runs=10, successes=2)}
    pick, considered = rank(CANDS, 2, True, {"ollama", "deepseek", "anthropic"}, PRICES, stats, OPEN_BUDGET)
    assert pick.route == "deepseek:deepseek-chat"
    assert "retired" in next(k.reason for k in considered if k.route == "ollama:big")


def test_selector_prefers_cost_per_success_not_raw_cost():
    stats = {"deepseek:deepseek-chat": Stats(runs=20, successes=11)}  # 55% — still eligible
    pick, _ = rank(CANDS[2:4], 2, True, {"deepseek", "anthropic"}, {"deepseek:deepseek-chat": 0.02, "anthropic:claude-sonnet-5": 0.021}, stats, OPEN_BUDGET)
    assert pick.route == "anthropic:claude-sonnet-5"  # 0.021/0.8 < 0.02/0.55


def test_selector_respects_budget_and_provider_caps():
    capped = {"month": INF, "today": INF, "providers": {"deepseek": 0.0}}
    pick, considered = rank(CANDS[2:4], 2, True, {"deepseek", "anthropic"}, PRICES, {}, capped)
    assert pick.route == "anthropic:claude-sonnet-5"
    assert "cap reached" in next(k.reason for k in considered if k.route == "deepseek:deepseek-chat")
    broke = {"month": 0.0, "today": INF, "providers": {}}
    pick, _ = rank(CANDS, 2, True, {"ollama", "deepseek", "anthropic"}, PRICES, {}, broke)
    assert pick.route == "ollama:big"  # only free models once the month is spent
    pick, _ = rank(CANDS[2:], 2, True, {"deepseek", "anthropic"}, PRICES, {}, broke)
    assert pick is None


# ---------------------------------------------------------------- ledger + caps

def test_ledger_totals_and_remaining():
    async def go():
        await ledger.record("biz_a", "anthropic", "claude-sonnet-5", 1000, 100, 0.40)
        await ledger.record("biz_a", "deepseek", "deepseek-chat", 1000, 100, 0.10)
        await ledger.record("biz_b", "deepseek", "deepseek-chat", 1000, 100, 9.0)
        t = await ledger.totals("biz_a")
        await guard_config_store.update({"provider_monthly_caps": {"anthropic": 0.40}, "monthly_budget": 100.0})
        rem = await ledger.remaining("biz_a")
        await guard_config_store.update({"provider_monthly_caps": {}})
        return t, rem
    t, rem = asyncio.run(go())
    assert round(t.month, 2) == 0.50 and round(t.by_provider_month["anthropic"], 2) == 0.40
    assert rem["providers"]["anthropic"] == 0.0 and rem["month"] == pytest.approx(99.5)


def test_burn_rate_alert_fires_once_per_hour(monkeypatch):  # overrides the no-op push with a recorder
    sent = []

    async def fake_push(title, body, **_):
        sent.append(title)
    monkeypatch.setattr("shadow.gates.notify_push", fake_push)

    async def go():
        await guard_config_store.update({"burn_rate_alert_per_hour": 0.5})
        await ledger.record("biz_a", "anthropic", "claude-opus-5", 0, 0, 0.6)
        await ledger.record("biz_a", "anthropic", "claude-opus-5", 0, 0, 0.6)
        await guard_config_store.update({"burn_rate_alert_per_hour": 1.0})
    asyncio.run(go())
    assert sent == ["Burn rate alert"]
    assert ledger.recent_alerts("biz_a")[0]["kind"] == "burn_rate"


class _FakeGateway:
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def price(self, provider, model, tin, tout):
        return (tin + tout) / 1_000_000

    async def chat(self, provider, model, messages, tools=None):
        self.calls += 1
        return dict(self.reply)


def _selection(provider="anthropic", model="claude-sonnet-5"):
    return Selection(provider, model, 2, 2, 0.01, "test")


def test_selected_brain_records_spend_and_stops_at_the_agent_cap():
    gw = _FakeGateway({"message": {"role": "assistant", "content": "done"}, "usage": {"input_tokens": 400_000, "output_tokens": 100_000}})
    brain = SelectedBrain(gw, _selection(), "biz_a", agent_id="agent_t1")

    async def go():
        await guard_config_store.update({"agent_daily_cap": 0.4})
        try:
            r = await brain.chat([{"role": "user", "content": "x"}], task_id="t1")
            with pytest.raises(CapReached, match="Agent daily cap"):
                await brain.chat([{"role": "user", "content": "x"}], task_id="t1")
            return r, await ledger.totals("biz_a")
        finally:
            await guard_config_store.update({"agent_daily_cap": None})
    r, t = asyncio.run(go())
    assert r["cost_usd"] == pytest.approx(0.5) and t.today == pytest.approx(0.5)
    assert gw.calls == 1


def test_selected_brain_stops_when_the_provider_cap_is_hit():
    gw = _FakeGateway({"message": {"role": "assistant", "content": "ok"}, "usage": {}})
    brain = SelectedBrain(gw, _selection("deepseek", "deepseek-chat"), "biz_a", agent_id="agent_t2")

    async def go():
        await ledger.record("biz_a", "deepseek", "deepseek-chat", 0, 0, 2.0)
        await guard_config_store.update({"provider_monthly_caps": {"deepseek": 1.0}})
        try:
            with pytest.raises(CapReached, match="deepseek monthly cap"):
                await brain.chat([{"role": "user", "content": "x"}])
        finally:
            await guard_config_store.update({"provider_monthly_caps": {}})
    asyncio.run(go())
    assert gw.calls == 0


# ---------------------------------------------------------------- Anthropic tool-use normalization

def test_anthropic_response_normalizes_to_ollama_tool_calls_and_keeps_blocks():
    block = lambda **kw: SimpleNamespace(**kw, model_dump=lambda exclude_none=True, kw=kw: dict(kw))  # noqa: E731
    resp = SimpleNamespace(
        stop_reason="tool_use", usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        content=[
            block(type="thinking", thinking="", signature="sig"),
            block(type="text", text="Checking."),
            block(type="tool_use", id="tu_1", name="web_search", input={"q": "x"}),
        ],
    )
    out = AnthropicProvider.normalize_response(resp)
    msg = out["message"]
    assert msg["content"] == "Checking."
    assert msg["tool_calls"] == [{"id": "tu_1", "function": {"name": "web_search", "arguments": {"q": "x"}}}]
    assert [b["type"] for b in msg["_anthropic_content"]] == ["thinking", "text", "tool_use"]
    # the round trip sends the original blocks back, then the tool result as a tool_result block
    _, converted = AnthropicProvider.convert_messages([
        {"role": "user", "content": "go"}, msg, {"role": "tool", "tool_call_id": "tu_1", "content": "result"},
    ])
    assert converted[1]["content"][0]["type"] == "thinking"
    assert converted[2] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu_1", "content": "result"}]}


def test_anthropic_refusal_is_reported_not_read_as_content():
    resp = SimpleNamespace(stop_reason="refusal", usage=SimpleNamespace(input_tokens=1, output_tokens=0),
                           stop_details=SimpleNamespace(category="cyber"), content=[])
    assert AnthropicProvider.normalize_response(resp)["message"]["content"] == "[Claude declined this request (cyber)]"


# ---------------------------------------------------------------- API surfaces

def test_delegate_records_the_selection_when_a_model_is_available(client, monkeypatch):
    class Gw(_FakeGateway):
        async def available_providers(self):
            return {"deepseek"}
    gw = Gw({"message": {"role": "assistant", "content": "report"}, "usage": {"prompt_tokens": 100, "completion_tokens": 50}})
    monkeypatch.setattr(app.state, "gateway", gw, raising=False)
    body = client.post("/api/shadow/delegate", json={"title": "summarize the inbox", "minutes_saved": 30, "revenue_value": 120}).json()
    sel = body["metadata"]["selection"]
    assert sel["route"] == "deepseek:" + sel["model"] and sel["required_tier"] in (1, 2, 3)
    assert body["metadata"]["minutes_saved"] == 30
    preview = client.post("/api/shadow/selector/preview", json={"title": "hi"}).json()
    assert preview["provider"] == "deepseek" and preview["considered"]


def test_headline_stats_are_real_or_honestly_empty(client):
    body = client.get("/api/metrics/headline").json()
    assert set(body) == {"tasks_terminated", "hours_reclaimed", "revenue_enabled", "model_spend"}
    assert body["revenue_enabled"]["total"] is None or body["revenue_enabled"]["tagged_tasks"] > 0
    assert "assumption" in body["hours_reclaimed"]


def test_ledger_summary_endpoint(client):
    asyncio.run(ledger.record("biz_default", "deepseek", "deepseek-chat", 0, 0, 0.25))
    body = client.get("/api/ledger/summary").json()
    assert body["totals"]["today"] >= 0.25 and "monthly_budget" in body["limits"]


def test_guard_patch_accepts_ledger_limits(client):
    res = client.patch("/api/shadow/guards", json={"monthly_budget": 42, "provider_monthly_caps": {"anthropic": 10}})
    assert res.status_code == 200 and res.json()["monthly_budget"] == 42
    client.patch("/api/shadow/guards", json={"monthly_budget": 100, "provider_monthly_caps": {}})


def test_archive_needs_a_database(client):
    assert client.get("/api/archive/notebooks").json() == []
    assert client.post("/api/archive/notebooks", json={"title": "Q3"}).status_code == 503


# ---------------------------------------------------------------- Archive retrieval (pure)

def test_archive_passages_rank_and_citations():
    text = "Pricing\n\nOur churn rose to 7% in August after the price change.\n\n" + ("Filler about offices. " * 60) + "\n\nHiring plan: two engineers in Q4."
    pool = passages("d1", "Board memo", text, size=300)
    assert len(pool) >= 3 and all(len(p["text"]) <= 300 for p in pool)
    top = rank_passages("why did churn go up in August", pool, k=2)
    assert "churn" in top[0]["text"]
    prompt = build_ask_prompt("churn?", top)
    assert "[1] (Board memo)" in prompt
    assert cited_numbers("Churn rose [1], see also [1, 2] and [9].", 2) == [1, 2]


def test_archive_script_parsing():
    script = parse_script("DEXTER: Big picture first.\n**ANTHONY**: Risk: churn.\nnoise line\nDexter: Next steps.")
    assert [s["speaker"] for s in script] == ["DEXTER", "ANTHONY", "DEXTER"]
