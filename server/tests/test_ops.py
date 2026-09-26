"""Full-pass surfaces (server/ops.py): run log, Hold, templates, standing preferences,
Prometheus workload, per-business budget, mission priority, hybrid Archive retrieval."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

import archive
import ops
from main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
    ops._hold.clear()


# ---------------------------------------------------------------- standing preferences (pure)

@pytest.mark.parametrize("text,expected", [
    ("Remember that invoices go out on Fridays.", "invoices go out on Fridays"),
    ("please remember I take calls after 2pm", "I take calls after 2pm"),
    ("From now on, cc Anthony on vendor emails", "cc Anthony on vendor emails"),
    ("Always ask before spending more than $50", "Always ask before spending more than $50"),
    ("never schedule meetings on Monday", "never schedule meetings on Monday"),
    ("I prefer short bullet summaries", "I prefer short bullet summaries"),
    ("My accountant is Dana Reyes", "My accountant is Dana Reyes"),
])
def test_standing_facts_are_detected(text, expected):
    assert ops.extract_standing_fact(text) == expected


@pytest.mark.parametrize("text", [
    "Do you remember what we said yesterday?",
    "What should I prioritize today?",
    "Draft the Q3 report",
    "",
    "remember\nthis is two lines",
])
def test_questions_and_ordinary_requests_are_not_preferences(text):
    assert ops.extract_standing_fact(text) is None


def test_forget_is_detected():
    assert ops.extract_forget("Forget that I prefer short summaries.") == "I prefer short summaries"
    assert ops.extract_forget("What did you forget?") is None


def test_standing_note_lists_preferences_and_is_none_when_empty():
    assert ops.standing_note([]) is None
    note = ops.standing_note([{"value": "Always cc Anthony"}])
    assert note["role"] == "system" and "- Always cc Anthony" in note["content"]


def test_fact_keys_are_scoped_per_business():
    a = ops._fact_key("biz_a", "Always cc Anthony")
    b = ops._fact_key("biz_b", "Always cc Anthony")
    assert a != b and a.startswith("biz_a::") and b.startswith("biz_b::")
    assert ops._fact_key("biz_a", "ALWAYS cc anthony") == a  # same statement, any case


def test_chat_reports_remembering_even_without_a_database(client):
    body = client.post("/api/chat/send", json={"message": "Remember that I like dark mode", "protocol": "orch"}).json()
    # no Postgres here: nothing is saved, so nothing is claimed
    assert body["remembered"] is None
    assert "content" in body["message"]


def test_facts_list_is_empty_without_a_database(client):
    assert client.get("/api/ops/facts").json() == []


# ---------------------------------------------------------------- hold

def _wait_for(client, task_id, status, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        t = next((t for t in client.get("/api/shadow/tasks").json() if t["id"] == task_id), None)
        if t and t["status"] == status:
            return t
        time.sleep(0.05)
    raise AssertionError(f"{task_id} never reached {status}")


def test_hold_parks_new_tasks_at_a_gate_and_approval_releases_them(client):
    assert client.post("/api/ops/hold", json={"on": True}).json() == {"on": True}
    assert client.get("/api/ops/hold").json() == {"on": True}
    task = client.post("/api/shadow/delegate", json={"title": "held work"}).json()
    _wait_for(client, task["id"], "gated")
    gates = client.get("/api/shadow/gates").json()
    assert any(g["task_id"] == task["id"] and "hold" in g["reason"].lower() for g in gates)
    client.post("/api/ops/hold", json={"on": False})
    assert client.post(f"/api/shadow/gates/{task['id']}/approve").status_code == 200
    _wait_for(client, task["id"], "done")


def test_run_log_shows_spawns_and_gates(client):
    client.post("/api/ops/hold", json={"on": True})
    task = client.post("/api/shadow/delegate", json={"title": "logged work"}).json()
    _wait_for(client, task["id"], "gated")
    events = client.get("/api/ops/runlog").json()
    kinds = {e["kind"] for e in events if e["task_id"] == task["id"]}
    assert {"spawn", "gated"} <= kinds
    client.post(f"/api/shadow/gates/{task['id']}/reject", json={"reason": "test"})


# ---------------------------------------------------------------- priority, budget, templates, workload

def test_tasks_sort_by_mission_priority(client):
    low = client.post("/api/shadow/delegate", json={"title": "p-low", "priority": "low"}).json()
    crit = client.post("/api/shadow/delegate", json={"title": "p-crit", "priority": "critical"}).json()
    ids = [t["id"] for t in client.get("/api/shadow/tasks").json()]
    assert ids.index(crit["id"]) < ids.index(low["id"])
    assert crit["metadata"]["priority"] == "critical"


def test_budget_is_scoped_to_the_business(client):
    body = client.get("/api/shadow/budget").json()
    assert set(body) >= {"daily_limit", "daily_spent", "daily_remaining", "active_tasks", "total_tasks_today"}
    assert body["daily_remaining"] <= body["daily_limit"]


def test_templates_need_a_database_to_save_but_list_empty_without_one(client):
    assert client.get("/api/ops/templates").json() == []
    assert client.post("/api/ops/templates", json={"name": "Weekly report"}).status_code == 503


def test_prometheus_workload_reports_disconnected_without_a_bridge(client, monkeypatch):
    import tools.prometheus_tools as pt
    monkeypatch.setattr(pt, "get_client", lambda: None)
    assert client.get("/api/ops/prometheus/workload").json() == {"connected": False, "teams": []}


# ---------------------------------------------------------------- hybrid archive retrieval

def test_blend_lets_semantic_hits_outrank_weak_lexical_ones():
    a = {"text": "lexical top"}
    b = {"text": "lexical second"}
    c = {"text": "semantic only"}
    ranked = [a, b, c]  # c is appended after the lexical list, as rank_hybrid does
    out = archive.blend(ranked, {id(a): 0.0, id(b): 0.1, id(c): 0.99}, k=3)
    assert out[0] is c or out.index(c) < out.index(b)


@pytest.mark.asyncio
async def test_rank_hybrid_falls_back_to_bm25_without_embeddings():
    pool = archive.passages("d1", "Doc", "Invoices are paid on Fridays.\n\nThe office cat is named Toast.")
    async def no_embed(_):
        return []
    out = await archive.rank_hybrid("when are invoices paid", pool, no_embed)
    assert out and "Invoices" in out[0]["text"]
    assert await archive.rank_hybrid("when are invoices paid", pool, None) == archive.rank_passages("when are invoices paid", pool)[:archive.TOP_K]


@pytest.mark.asyncio
async def test_rank_hybrid_surfaces_a_paraphrase_with_embeddings():
    pool = [
        {"doc_id": "d", "title": "t", "index": 0, "text": "Quarterly revenue grew twelve percent."},
        {"doc_id": "d", "title": "t", "index": 1, "text": "Our feline mascot is called Toast."},
    ]
    async def embed(text):
        t = text.lower()
        return [1.0, 0.0] if ("cat" in t or "feline" in t) else [0.0, 1.0]
    out = await archive.rank_hybrid("what is the cat called", pool, embed, k=1)
    assert out[0]["index"] == 1  # no word overlap with the question, found by similarity
