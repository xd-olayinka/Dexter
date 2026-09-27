"""Anthony: automatic Prometheus gate votes (gate_voter.py) and per-round task checkpoints."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import gate_voter


@pytest.mark.parametrize("text,expected", [
    ('{"verdict": "pass", "reason": "Tests attached."}', ("pass", "Tests attached.")),
    ('Sure!\n```json\n{"verdict":"FAIL","reason":"No PR link"}\n```', ("fail", "No PR link")),
    ('{"verdict": "maybe", "reason": "?"}', None),
    ("I think it passes.", None),
    ("", None),
])
def test_parse_verdict(text, expected):
    assert gate_voter.parse_verdict(text) == expected


class FakeClient:
    def __init__(self, checks):
        self.checks = checks
        self.reports = []

    async def my_gate_checks(self):
        return {"checks": self.checks}

    async def get_issue(self, issue_id):
        return {"markdown": f"# {issue_id}\n\nAcceptance criteria met; PR #12 merged."}

    async def report_gate_check(self, proposal_id, gate_id, verdict, detail=None):
        self.reports.append((proposal_id, gate_id, verdict, detail))
        return {"outcome": "recorded"}


class FakeBrain:
    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    async def describe(self):
        return {"ready": True, "provider": "fake", "model": "fake"}

    async def chat(self, messages, **kw):
        self.prompts.append(messages[-1]["content"])
        return {"message": {"content": self.reply}}


def _check(pid="prop_1", gid="gate_1", vote=None):
    return {"proposalId": pid, "gateId": gid, "gateType": "agent_check", "instructions": "PR must be merged",
            "issueId": "iss_1", "identifier": "ENG-1", "title": "Ship it", "toState": "Done", "yourVote": vote}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    gate_voter._done.clear()
    gate_voter.recent.clear()
    import ledger

    async def plenty(_):
        return {"month": 10.0, "today": 1.0, "providers": {}}
    monkeypatch.setattr(ledger, "remaining", plenty)


def _app(brain):
    return SimpleNamespace(state=SimpleNamespace(brain=brain))


@pytest.mark.asyncio
async def test_votes_once_per_gate_with_reasoning(monkeypatch):
    import tools.prometheus_tools as pt
    client = FakeClient([_check(), _check(gid="gate_2", vote="pass")])  # gate_2 already voted
    monkeypatch.setattr(pt, "get_client", lambda: client)
    brain = FakeBrain('{"verdict": "pass", "reason": "PR #12 is merged."}')

    assert await gate_voter.vote_once(_app(brain)) == 1
    assert client.reports == [("prop_1", "gate_1", "pass", "Anthony: PR #12 is merged.")]
    assert "PR must be merged" in brain.prompts[0] and "PR #12 merged" in brain.prompts[0]
    assert gate_voter.recent[0]["detail"].startswith("voted pass")
    # a second sweep doesn't vote again
    assert await gate_voter.vote_once(_app(brain)) == 0


@pytest.mark.asyncio
async def test_unclear_judgement_casts_no_vote(monkeypatch):
    import tools.prometheus_tools as pt
    client = FakeClient([_check()])
    monkeypatch.setattr(pt, "get_client", lambda: client)
    assert await gate_voter.vote_once(_app(FakeBrain("Looks fine to me"))) == 0
    assert client.reports == []


@pytest.mark.asyncio
async def test_spent_budget_stops_voting(monkeypatch):
    import ledger
    import tools.prometheus_tools as pt
    client = FakeClient([_check()])
    monkeypatch.setattr(pt, "get_client", lambda: client)

    async def spent(_):
        return {"month": 0.0, "today": 0.0, "providers": {}}
    monkeypatch.setattr(ledger, "remaining", spent)
    assert await gate_voter.vote_once(_app(FakeBrain('{"verdict":"pass","reason":"ok"}'))) == 0
    assert client.reports == []


@pytest.mark.asyncio
async def test_no_bridge_or_no_brain_is_a_no_op(monkeypatch):
    import tools.prometheus_tools as pt
    monkeypatch.setattr(pt, "get_client", lambda: None)
    assert await gate_voter.vote_once(_app(FakeBrain("{}"))) == 0


# ---------------------------------------------------------------- checkpoints

@pytest.mark.asyncio
async def test_tool_loop_checkpoints_after_each_round():
    from models import ToolResult
    from tools.caller import run_with_tools

    replies = iter([
        {"message": {"role": "assistant", "content": "", "tool_calls": [{"id": "t1", "function": {"name": "get_time", "arguments": {}}}]}},
        {"message": {"role": "assistant", "content": "Done."}},
    ])

    class Brain:
        async def chat(self, messages, tools=None):
            return next(replies)

    class Registry:
        def get_schema(self):
            return []

        async def execute(self, call, task_id=None):
            return ToolResult(tool_call_id=call.id, content="12:00", success=True)

    saved = []

    async def on_step(msgs):
        saved.append(len(msgs))

    result, msgs = await run_with_tools(Brain(), [{"role": "user", "content": "time?"}], Registry(), on_step=on_step)
    assert result == "Done."
    assert saved == [3]  # user + assistant tool call + tool result


@pytest.mark.asyncio
async def test_resumed_work_fn_continues_from_the_checkpoint():
    from models import Task
    from shadow.budget import BudgetTracker
    from shadow.work import make_llm_work_fn

    seen = {}

    class Brain:
        async def chat(self, messages, tools=None, **kw):
            seen["messages"] = list(messages)
            return {"message": {"role": "assistant", "content": "Finished the remaining step."}}

    checkpoint = [{"role": "system", "content": "sys"}, {"role": "user", "content": "do two things"},
                  {"role": "assistant", "content": "did the first"}]
    task = Task(title="do two things", metadata={"checkpoint": checkpoint})
    out = await make_llm_work_fn(Brain())(task, BudgetTracker(task_id=task.id, task_budget=1.0, daily_budget=5.0))
    assert out == "Finished the remaining step."
    assert seen["messages"][:3] == checkpoint and "restarted" in seen["messages"][3]["content"]
    assert "checkpoint" not in task.metadata
