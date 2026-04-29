"""Tests for the operations endpoints: /health, /ready, /metrics."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.memory.store import MemoryStore
from app.web.server import create_app


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr("app.security.rate_limit.limiter.enabled", False)
    return TestClient(create_app(memory=MemoryStore()))


def test_health_returns_200(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "uptime_seconds" in body


def test_ready_returns_200_when_db_off(client: TestClient) -> None:
    """USE_DB=false → readiness only checks the process."""
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"]["process"] == "ok"


def test_metrics_returns_prometheus_format(client: TestClient) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200
    text = r.text
    # Prometheus format requires HELP/TYPE comments and metric lines.
    assert "# HELP two_brains_uptime_seconds" in text
    assert "# TYPE two_brains_uptime_seconds gauge" in text
    assert "two_brains_uptime_seconds" in text
    # A counter we know exists.
    assert "two_brains_requests_total" in text


def test_metrics_increments_after_a_run(client: TestClient) -> None:
    """The /api/run handler bumps two_brains_requests_total — verify."""
    before = _counter_value(client, "two_brains_requests_total")
    client.post("/api/run", json={
        "prompt": "x",
        "planner_provider": "mock",
        "critic_provider": "mock",
    })
    after = _counter_value(client, "two_brains_requests_total")
    assert after >= before + 1


def _counter_value(client: TestClient, name: str) -> int:
    text = client.get("/metrics").text
    for line in text.splitlines():
        if line.startswith(name + " "):
            return int(line.split()[1])
    return 0
