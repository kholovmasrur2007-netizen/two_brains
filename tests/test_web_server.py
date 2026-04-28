"""Tests for the FastAPI web server (REST + WebSocket).

Every test uses an isolated in-memory MemoryStore so runs do not see
each other's history. The mock providers keep everything offline.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.memory.store import MemoryStore
from app.web.server import create_app


@pytest.fixture
def client() -> TestClient:
    """A TestClient over a freshly-built app with an isolated MemoryStore."""
    app = create_app(memory=MemoryStore())
    return TestClient(app)


# ── REST: providers ───────────────────────────────────────────────────


def test_providers_endpoint_lists_every_brain_kind(client: TestClient) -> None:
    res = client.get("/api/providers")
    assert res.status_code == 200
    payload = res.json()
    assert "deterministic" in payload["planner"]
    assert "deterministic" in payload["critic"]
    assert "deterministic" in payload["executor"]
    assert "mock" in payload["planner"]


# ── REST: synchronous run ─────────────────────────────────────────────


def test_run_endpoint_returns_final_result(client: TestClient) -> None:
    res = client.post("/api/run", json={
        "prompt": "Build a small REST API.",
        "planner_provider": "mock",
        "critic_provider": "mock",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["plan"]["task_id"] == body["task_id"]
    assert body["critique"]["task_id"] == body["task_id"]
    assert body["ready_for_execution"] is True  # mock provider always passes
    assert body["execution"] is None  # execute=False


def test_run_endpoint_runs_executor_when_requested(client: TestClient) -> None:
    res = client.post("/api/run", json={
        "prompt": "Build something.",
        "planner_provider": "mock",
        "critic_provider": "mock",
        "executor_provider": "mock",
        "execute": True,
    })
    assert res.status_code == 200
    body = res.json()
    assert body["execution"] is not None
    assert body["execution"]["overall_status"] == "completed"


def test_run_endpoint_rejects_invalid_provider(client: TestClient) -> None:
    res = client.post("/api/run", json={
        "prompt": "X",
        "planner_provider": "does-not-exist",
    })
    assert res.status_code == 400
    assert "available" in res.json()["detail"]


def test_run_endpoint_rejects_empty_prompt(client: TestClient) -> None:
    res = client.post("/api/run", json={"prompt": ""})
    assert res.status_code == 422  # pydantic min_length validation


# ── REST: history + tasks ─────────────────────────────────────────────


def test_history_starts_empty_and_grows_after_a_run(client: TestClient) -> None:
    assert client.get("/api/history").json() == []

    client.post("/api/run", json={
        "prompt": "Build a feature.",
        "planner_provider": "mock",
        "critic_provider": "mock",
    })

    history = client.get("/api/history").json()
    assert len(history) == 1
    assert history[0]["score"] is not None
    assert history[0]["ready_for_execution"] is True
    assert history[0]["executed"] is False


def test_get_task_returns_full_result(client: TestClient) -> None:
    run = client.post("/api/run", json={
        "prompt": "Build a feature.",
        "planner_provider": "mock",
        "critic_provider": "mock",
    }).json()
    task_id = run["task_id"]

    res = client.get(f"/api/tasks/{task_id}")
    assert res.status_code == 200
    assert res.json()["task_id"] == task_id


def test_get_task_returns_404_for_unknown_id(client: TestClient) -> None:
    res = client.get("/api/tasks/never-existed")
    assert res.status_code == 404


# ── WebSocket: live streaming ─────────────────────────────────────────


def test_websocket_streams_phase_events_in_order(client: TestClient) -> None:
    expected_first = {
        "task_received", "planner_started", "plan_ready",
        "critic_started", "critique_ready", "done",
    }
    with client.websocket_connect("/ws/run") as ws:
        ws.send_json({
            "prompt": "Build a thing.",
            "planner_provider": "mock",
            "critic_provider": "mock",
        })
        seen: list[str] = []
        while True:
            event = ws.receive_json()
            seen.append(event["type"])
            if event["type"] == "done":
                break

    # Every expected event must appear at least once and in a sane order.
    assert expected_first.issubset(set(seen))
    assert seen[0] == "task_received"
    assert seen[-1] == "done"
    assert seen.index("plan_ready") < seen.index("critique_ready")


def test_websocket_includes_executor_events_when_requested(client: TestClient) -> None:
    with client.websocket_connect("/ws/run") as ws:
        ws.send_json({
            "prompt": "Build a thing.",
            "planner_provider": "mock",
            "critic_provider": "mock",
            "executor_provider": "mock",
            "execute": True,
        })
        events: list[dict] = []
        while True:
            ev = ws.receive_json()
            events.append(ev)
            if ev["type"] == "done":
                break

    types = [e["type"] for e in events]
    assert "executor_started" in types
    assert "execution_ready" in types
    # The done event includes the full result with execution attached.
    final = events[-1]
    assert final["result"]["execution"] is not None


def test_websocket_emits_error_for_invalid_provider(client: TestClient) -> None:
    with client.websocket_connect("/ws/run") as ws:
        ws.send_json({
            "prompt": "X",
            "planner_provider": "nope",
        })
        ev = ws.receive_json()
        assert ev["type"] == "error"
        assert "available" in ev["message"]


# ── static UI ─────────────────────────────────────────────────────────


def test_index_html_is_served(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "two_brains" in res.text
    assert "<html" in res.text.lower()
