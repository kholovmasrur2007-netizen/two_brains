"""Tests for the audit log writer + admin reader endpoint."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.memory.store import MemoryStore
from app.web.server import create_app


@pytest.fixture
def client_audit(tmp_path, monkeypatch) -> TestClient:
    """App with USE_DB=true so audit writes actually land in a SQLite file."""
    db_url = f"sqlite:///{tmp_path}/audit.db"
    monkeypatch.setattr("app.config.settings.use_db", True)
    monkeypatch.setattr("app.config.settings.database_url", db_url)
    monkeypatch.setattr("app.db.engine._engine", None)
    monkeypatch.setattr("app.security.rate_limit.limiter.enabled", False)
    return TestClient(create_app(memory=MemoryStore()))


def test_audit_writer_no_op_without_db(monkeypatch) -> None:
    """Without USE_DB the writer must silently return — no exception."""
    monkeypatch.setattr("app.config.settings.use_db", False)
    from app.security.audit import AuditLogger
    AuditLogger.log(action="test", username="u")  # must not raise


def test_audit_writer_stores_entry(client_audit) -> None:
    from app.security.audit import AuditLogger
    AuditLogger.log(action="run", username="alice", target="task-1", status="ok")

    # Read back via the admin endpoint (auth is off → anonymous = admin).
    r = client_audit.get("/api/audit")
    assert r.status_code == 200
    rows = r.json()
    actions = [row["action"] for row in rows]
    assert "run" in actions


def test_audit_filter_by_username(client_audit) -> None:
    from app.security.audit import AuditLogger
    AuditLogger.log(action="run", username="alice")
    AuditLogger.log(action="run", username="bob")

    r = client_audit.get("/api/audit?username=alice")
    rows = r.json()
    assert all(row["username"] == "alice" for row in rows)


def test_audit_filter_by_action(client_audit) -> None:
    from app.security.audit import AuditLogger
    AuditLogger.log(action="login",  username="alice")
    AuditLogger.log(action="run",    username="alice")
    AuditLogger.log(action="login",  username="bob")

    r = client_audit.get("/api/audit?action=login")
    rows = r.json()
    assert all(row["action"] == "login" for row in rows)
    assert len(rows) == 2


def test_run_endpoint_writes_audit_entry(client_audit) -> None:
    """A successful /api/run call must leave a trace in the audit log."""
    client_audit.post("/api/run", json={
        "prompt": "test",
        "planner_provider": "mock",
        "critic_provider": "mock",
    })
    rows = client_audit.get("/api/audit?action=run").json()
    assert len(rows) >= 1
    assert rows[0]["action"] == "run"
    assert rows[0]["status"] == "ok"


def test_audit_returns_503_when_db_off(monkeypatch) -> None:
    """If USE_DB=false the audit endpoint returns 503 — no silent empty list."""
    monkeypatch.setattr("app.security.rate_limit.limiter.enabled", False)
    client = TestClient(create_app(memory=MemoryStore()))
    r = client.get("/api/audit")
    assert r.status_code == 503
