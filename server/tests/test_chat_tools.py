"""Chat tools (chat_tools.py): reads run freely, Prometheus changes only via confirmed proposals."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import chat_tools
from main import app


def test_chat_registry_has_reads_and_propose_but_no_writes_or_files():
    reg = chat_tools.make_registry("biz", [])
    names = set(reg.list_tools())
    assert "propose_action" in names and "web_search" in names
    for forbidden in ("read_file", "write_file", "list_directory", "prometheus_create_issue",
                      "prometheus_comment_issue", "prometheus_transition_issue", "prometheus_report_gate_check"):
        assert forbidden not in names


@pytest.mark.parametrize("kind,args,ok", [
    ("create_issue", {"team_id": "t1", "title": "Fix login"}, True),
    ("create_issue", {"title": "no team"}, False),
    ("comment_issue", {"issue_id": "i1", "body": "hi"}, True),
    ("update_issue", {"issue_id": "i1"}, False),
    ("update_issue", {"issue_id": "i1", "progress_note": "half done"}, True),
    ("delete_everything", {}, False),
])
def test_validate_action(kind, args, ok):
    assert (chat_tools.validate_action(kind, args) is None) is ok


class ScriptedBrain:
    """Replies with the scripted messages in order (tool calls first, then text)."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen = []

    async def chat(self, messages, tools=None, **kw):
        self.seen.append((list(messages), [t["function"]["name"] for t in tools or []]))
        return {"message": self.replies.pop(0)}


@pytest.mark.asyncio
async def test_turn_collects_a_proposal_and_reports_status():
    brain = ScriptedBrain(
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "propose_action", "arguments": {
            "kind": "comment_issue", "summary": "Comment on ENG-1", "args": {"issue_id": "i1", "body": "Looks good"}}}}]},
        {"role": "assistant", "content": "I've drafted that comment — confirm it below."},
    )
    statuses = []

    async def on_status(s):
        statuses.append(s)

    reply, proposals = await chat_tools.run_turn(brain, [{"role": "system", "content": "sys"}, {"role": "user", "content": "comment"}], "biz", on_status)
    assert reply.startswith("I've drafted")
    assert [p["kind"] for p in proposals] == ["comment_issue"]
    assert statuses == ["Drafting a change for you to confirm…"]
    assert "propose_action" in brain.seen[0][1] and "Use them instead of guessing" in brain.seen[0][0][0]["content"]
    # proposals belong to the business that made them
    pid = proposals[0]["id"]
    assert chat_tools.take(pid, "other-biz") is None
    assert chat_tools.take(pid, "biz")["kind"] == "comment_issue"
    assert chat_tools.take(pid, "biz") is None  # single use


@pytest.mark.asyncio
async def test_perform_calls_prometheus(monkeypatch):
    import tools.prometheus_tools as pt

    calls = []

    class Client:
        async def comment_issue(self, issue_id, body):
            calls.append((issue_id, body))
            return {"commentId": "c9"}

    monkeypatch.setattr(pt, "get_client", lambda: Client())
    out = await chat_tools.perform({"kind": "comment_issue", "args": {"issue_id": "i1", "body": "ok"}})
    assert calls == [("i1", "ok")] and "c9" in out


def test_confirming_an_unknown_action_is_a_404():
    with TestClient(app) as c:
        assert c.post("/api/ops/actions/act_nope/confirm").status_code == 404
