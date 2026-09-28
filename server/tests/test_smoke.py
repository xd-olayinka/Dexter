"""Smoke tests for the Phase 2 backend additions (P2-P6). Run with no Postgres,
no Ollama and no DeepSeek key running — the whole point is that every new module
must degrade gracefully rather than 500 when those services aren't there, matching
the rest of this backend's stated philosophy. A real Postgres/Ollama box would
exercise the "happy path" (persistence actually persisting, recall actually
recalling) that these tests can't reach in this environment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    assert client.get("/").json()["status"] == "ok"


def test_status_reports_new_subsystems(client):
    body = client.get("/api/status").json()
    assert "brain" in body and "database" in body


def test_chat_send_degrades_to_stub_without_a_provider(client):
    res = client.post("/api/chat/send", json={"message": "hello", "protocol": "orch"})
    assert res.status_code == 200
    body = res.json()
    assert body["session_id"]
    assert "content" in body["message"]


def test_chat_history_round_trips_in_memory(client):
    sent = client.post("/api/chat/send", json={"message": "remember this", "protocol": "orch"}).json()
    sid = sent["session_id"]
    hist = client.get(f"/api/chat/history/{sid}").json()
    assert len(hist["messages"]) == 2
    assert hist["messages"][0]["content"] == "remember this"


def test_projects_list_is_empty_without_a_database(client):
    # get_pool() returns None without a real DSN reachable — list() must return [],
    # not raise, so the frontend can render "no projects yet" instead of erroring.
    assert client.get("/api/projects").json() == []
    assert client.get("/api/tasks").json() == []


def test_project_create_without_database_is_a_clean_503_not_a_500(client):
    res = client.post("/api/projects", json={"name": "Test Project"})
    assert res.status_code == 503
    assert "Database" in res.json()["detail"]


def test_briefing_falls_back_without_a_brain(client):
    body = client.get("/api/briefing/today").json()
    assert body["source"] == "fallback"
    assert "Commander" in body["headline"]
    assert body["stats"]["tasks_today"] == 0


def test_briefing_is_cached_on_second_call(client):
    # _cache is a module-level singleton — force a fresh fetch first so an earlier
    # test's call (same process) can't leave this one looking at an already-warm cache.
    first = client.get("/api/briefing/today?refresh=true").json()
    second = client.get("/api/briefing/today").json()
    assert first["cached"] is False
    assert second["cached"] is True
    assert second["headline"] == first["headline"]


def test_files_list_is_empty_without_a_database(client):
    assert client.get("/api/files").json() == []


def test_file_upload_extracts_text_but_503s_on_save_without_a_database(client):
    res = client.post(
        "/api/files/upload",
        files={"file": ("notes.txt", b"the sky is blue", "text/plain")},
    )
    assert res.status_code == 503  # extraction succeeded; only persistence is blocked


def test_file_upload_rejects_unsupported_type(client):
    res = client.post(
        "/api/files/upload",
        files={"file": ("archive.zip", b"PK\x03\x04", "application/zip")},
    )
    assert res.status_code == 415


def test_guards_config_has_sane_defaults_without_a_database(client):
    body = client.get("/api/shadow/guards").json()
    assert body["daily_budget"] > 0
    assert body["per_task_budget_default"] > 0
    assert body["custom_rules"] == []


def test_guards_config_patch_updates_the_running_chain(client):
    res = client.patch("/api/shadow/guards", json={"daily_budget": 12.5})
    assert res.status_code == 200
    assert res.json()["daily_budget"] == 12.5
    # takes effect for the next task spawned, without a restart
    budget = client.get("/api/shadow/budget").json()
    assert budget["daily_limit"] == 12.5


def test_guards_custom_rule_add_and_remove(client):
    created = client.post("/api/shadow/guards/rules", json={"name": "no huge tasks", "max_spend": 1.5}).json()
    assert any(r["name"] == "no huge tasks" for r in created["custom_rules"])
    rule_id = next(r["id"] for r in created["custom_rules"] if r["name"] == "no huge tasks")
    after = client.delete(f"/api/shadow/guards/rules/{rule_id}").json()
    assert all(r["id"] != rule_id for r in after["custom_rules"])


def test_voice_ws_ready_then_ping_pong(client):
    with client.websocket_connect("/ws/voice?protocol=orch") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert "capabilities" in ready
        ws.send_text('{"type": "ping"}')
        assert ws.receive_json() == {"type": "pong"}


def test_voice_ws_commit_with_no_audio_is_a_no_op(client):
    # push-to-talk release before any audio was sent must not crash the connection
    with client.websocket_connect("/ws/voice?protocol=orch") as ws:
        ws.receive_json()  # ready
        ws.send_text('{"type": "commit"}')
        ws.send_text('{"type": "ping"}')
        assert ws.receive_json() == {"type": "pong"}


def test_voice_ws_commit_finalizes_without_waiting_for_vad_silence(client):
    # the whole point of the commit message: one audio chunk + an immediate commit
    # must produce a transcription, since a real VAD would never see silence once the
    # client stops sending chunks (dummy VAD would already do this; commit must too)
    with client.websocket_connect("/ws/voice?protocol=orch") as ws:
        ws.receive_json()  # ready
        ws.send_bytes(b"\x00\x00" * 1600)  # 100ms of silence @16kHz mono PCM16
        ws.send_text('{"type": "commit"}')
        msg = ws.receive_json()
        assert msg["type"] in ("processing", "transcription")
        if msg["type"] == "processing":
            msg = ws.receive_json()
        assert msg["type"] == "transcription"


def test_escalation_route_dry_run_has_no_side_effects(client):
    res = client.post("/api/escalation/route", json={"message": "hi"})
    assert res.status_code == 200
    assert "provider" in res.json()


# ---------------------------------------------------------------- Phase 4 (docs/PHASE_3_4_PLAN.md)

def test_me_resolves_the_default_context_when_auth_is_off(client):
    body = client.get("/api/auth/me").json()
    assert body == {
        "require_auth": False,
        "user": {"id": "user_default", "email": "commander@local", "name": "Commander"},
        "business_id": "biz_default", "business_name": "My Business", "role": "owner",
    }


def test_register_login_require_a_database(client):
    assert client.post("/api/auth/register", json={"email": "a@b.com", "password": "x"}).status_code == 503
    assert client.post("/api/auth/login", json={"email": "a@b.com", "password": "x"}).status_code == 503


def test_logout_without_a_bearer_token_is_a_no_op_not_an_error(client):
    assert client.post("/api/auth/logout").status_code == 204


def test_members_list_is_empty_without_a_database(client):
    assert client.get("/api/auth/members").json() == []


def test_agents_list_is_empty_without_a_database(client):
    assert client.get("/api/shadow/agents").json() == []


def test_metrics_summary_is_honest_zeros_without_a_database(client):
    body = client.get("/api/metrics/summary").json()
    assert body["time_to_completion"] == {"median_seconds": None, "p90_seconds": None, "sample_size": 0, "on_track": None}
    assert body["intervention_rate"] == {"without_intervention_pct": None, "sample_size": 0, "on_track": None}
    assert body["cost_trend"] == []
    assert body["targets"] == {"time_to_completion_minutes": 10, "without_intervention_pct": 70}


def test_status_prometheus_block_is_internally_consistent(client):
    # Whether Prometheus is configured depends on server/.env in whatever environment
    # runs this test — assert the shape's consistency rather than one hardcoded state.
    from config import settings
    body = client.get("/api/status").json()
    configured = bool(settings.prometheus_mcp_url and settings.prometheus_mcp_token)
    assert body["prometheus"]["configured"] is configured
    if not configured:
        assert body["prometheus"] == {"configured": False, "connected": False, "url": None}
    else:
        assert body["prometheus"]["url"] == settings.prometheus_mcp_url


def test_delegate_still_works_with_the_default_context(client):
    # spawn goes through record_spawn (agents_store), which must degrade to a no-op
    # without a database rather than breaking the actual delegation
    res = client.post("/api/shadow/delegate", json={"title": "test task"})
    assert res.status_code == 200
    assert res.json()["title"] == "test task"


def test_invite_requires_a_database(client):
    res = client.post("/api/auth/invite", json={"email": "new@b.com", "role": "member"})
    assert res.status_code == 503


def test_invite_rejects_a_bad_role(client):
    # role validation runs before the DB check, so this 400s even with no database
    res = client.post("/api/auth/invite", json={"email": "new@b.com", "role": "superuser"})
    assert res.status_code == 400


def test_delegate_still_returns_a_task_when_a_brain_is_configured_or_not(client):
    # exercises the model_route-capture branch in shadow/router.py either way —
    # ready=False here (no Ollama/DeepSeek in this environment) so model_route stays None
    res = client.post("/api/shadow/delegate", json={"title": "route capture check"})
    assert res.status_code == 200


def test_businesses_lists_the_single_default_business_when_auth_is_off(client):
    body = client.get("/api/auth/businesses").json()
    assert body == [{"id": "biz_default", "name": "My Business", "role": "owner", "current": True}]


def test_switch_business_is_a_400_when_auth_is_off(client):
    res = client.post("/api/auth/switch-business", json={"business_id": "biz_default"})
    assert res.status_code == 400


def test_dependency_map_shape_without_a_database(client):
    body = client.get("/api/dependencies/map").json()
    assert body["business"] == {"id": "biz_default", "name": "My Business"}
    assert body["members"] == []
    assert body["agents"] == []
    # the tool registry itself needs no DB — real registered tool names always show up
    tool_names = {t["name"] for t in body["tools"]}
    assert "web_search" in tool_names
    assert "browse_url" in tool_names
    for t in body["tools"]:
        assert t["kind"] in ("builtin", "integration")
        assert t["used_by_agents"] == 0  # no agents in this fixture, so no tool could have been used


@pytest.mark.asyncio
async def test_tool_call_logging_degrades_without_a_database():
    from tools.registry import ToolRegistry, Tool
    from models import ToolCall

    registry = ToolRegistry()
    registry.register(Tool(name="echo", description="", parameters={}, handler=lambda: _echo()))
    result = await registry.execute(ToolCall(name="echo", arguments={}), task_id="task_doesnt_exist")
    assert result.success is True
    assert result.content == "ok"


async def _echo() -> str:
    return "ok"


def test_compute_efficiency_rewards_cheap_clean_completions():
    from shadow.agents_store import compute_efficiency
    from models import TaskStatus

    cheap_done = compute_efficiency(0.01, TaskStatus.DONE)
    expensive_done = compute_efficiency(1.0, TaskStatus.DONE)
    assert cheap_done > expensive_done  # cheaper is better for the same outcome

    killed = compute_efficiency(0.01, TaskStatus.KILLED)
    assert killed == 0.0  # a killed task scores zero regardless of spend

    gated = compute_efficiency(0.01, TaskStatus.GATED)
    assert 0 < gated < cheap_done  # mid-flight, worth less than a clean finish so far

    # spend floor: a free task doesn't divide by zero or return infinity
    from shadow.agents_store import SPEND_FLOOR
    assert compute_efficiency(0.0, TaskStatus.DONE) == round(1.0 / SPEND_FLOOR, 4)


# ---------------------------------------------------------------- auth coverage on Anthony's control plane

from auth import CurrentContext, current_context  # noqa: E402
from config import settings as _settings  # noqa: E402


def _ctx(business_id: str, role: str = "owner") -> CurrentContext:
    return CurrentContext(user_id=f"u_{business_id}", email=f"{business_id}@x.com", name="", business_id=business_id, business_name=business_id, role=role)


@pytest.fixture()
def as_business():
    """Swap the caller's context mid-test — stands in for two signed-in users."""
    def use(business_id: str, role: str = "owner"):
        app.dependency_overrides[current_context] = lambda: _ctx(business_id, role)
    yield use
    app.dependency_overrides.pop(current_context, None)


@pytest.mark.parametrize("method,path", [
    ("get", "/api/shadow/tasks"),
    ("post", "/api/shadow/tasks/task_x/kill"),
    ("get", "/api/shadow/gates"),
    ("post", "/api/shadow/gates/task_x/approve"),
    ("post", "/api/shadow/gates/task_x/reject"),
    ("post", "/api/shadow/gates/test"),
    ("get", "/api/shadow/budget"),
    ("patch", "/api/shadow/guards"),
    ("get", "/api/escalation/spend"),
    ("post", "/api/escalation/route"),
])
def test_control_plane_requires_a_session_when_auth_is_on(client, monkeypatch, method, path):
    monkeypatch.setattr(_settings, "require_auth", True)
    assert getattr(client, method)(path).status_code == 401


def test_tasks_are_scoped_to_the_callers_business(client, as_business):
    as_business("biz_a")
    task_id = client.post("/api/shadow/delegate", json={"title": "A's task"}).json()["id"]
    assert any(t["id"] == task_id for t in client.get("/api/shadow/tasks").json())

    as_business("biz_b")
    assert all(t["id"] != task_id for t in client.get("/api/shadow/tasks").json())
    assert client.get(f"/api/shadow/tasks/{task_id}").status_code == 404
    assert client.post(f"/api/shadow/tasks/{task_id}/kill").status_code == 404
    assert client.post(f"/api/shadow/gates/{task_id}/approve").status_code == 404


def test_guard_edits_need_owner_or_admin(client, as_business):
    as_business("biz_a", role="member")
    assert client.get("/api/shadow/guards").status_code == 200
    assert client.patch("/api/shadow/guards", json={"daily_budget": 1}).status_code == 403
    assert client.post("/api/shadow/guards/rules", json={"name": "r"}).status_code == 403
    assert client.delete("/api/shadow/guards/rules/whatever").status_code == 403


# ---------------------------------------------------------------- invite claim needs the code

class _FakeCursor:
    def __init__(self, row):
        self._row = row

    async def fetchone(self):
        return self._row


class _FakeConn:
    """Scripted stand-in for the few queries `register` runs against a pending invite."""
    def __init__(self, code_hash):
        self.code_hash = code_hash
        self.password_set = False

    async def execute(self, sql, params=()):
        if sql.startswith("SELECT id, password_hash FROM users"):
            return _FakeCursor(("user_inv", ""))
        if sql.startswith("SELECT invite_code_hash"):
            return _FakeCursor((self.code_hash,))
        if sql.startswith("UPDATE users SET password_hash"):
            self.password_set = True
        if "FROM business_members" in sql:
            return _FakeCursor(("biz_host", "Host Co", "member"))
        return _FakeCursor(None)


class _FakePool:
    def __init__(self, conn):
        self.conn = conn

    def connection(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *exc):
                return False
        return _Ctx()


@pytest.mark.parametrize("code,expected", [("", 403), ("wrong", 403), ("right-code", 201)])
def test_claiming_a_pending_invite_requires_its_code(client, monkeypatch, code, expected):
    import auth
    conn = _FakeConn(auth._hash_token("right-code"))

    async def fake_pool():
        return _FakePool(conn)
    monkeypatch.setattr(auth, "get_pool", fake_pool)

    res = client.post("/api/auth/register", json={"email": "inv@x.com", "password": "pw", "invite_code": code})
    assert res.status_code == expected
    assert conn.password_set is (expected == 201)
    if expected == 201:
        assert res.json()["business_id"] == "biz_host"
