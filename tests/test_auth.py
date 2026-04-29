"""Tests for JWT authentication — login, register, protected endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.memory.store import MemoryStore
from app.web.server import create_app


@pytest.fixture
def client_noauth(monkeypatch) -> TestClient:
    """App with AUTH_ENABLED=false (default) — all endpoints open."""
    monkeypatch.setattr("app.security.rate_limit.limiter.enabled", False)
    app = create_app(memory=MemoryStore())
    return TestClient(app)


@pytest.fixture
def client_auth(tmp_path, monkeypatch) -> TestClient:
    """App with AUTH_ENABLED=true, isolated SQLite for users table."""
    import app.auth.core as auth_core
    from app.db.store import SQLMemoryStore

    # Patch module-level flag directly — works on non-frozen objects.
    monkeypatch.setattr(auth_core, "_AUTH_ENABLED", True)
    monkeypatch.setattr("app.security.rate_limit.limiter.enabled", False)

    db_url = f"sqlite:///{tmp_path}/auth_test.db"
    # Patch _get_user_row / _create_user_row / _user_count to use isolated DB.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.engine import Base, UserRow

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def _get(username):
        with Session() as s:
            return s.get(UserRow, username)

    def _create(username, pw_hash, is_admin=False):
        with Session() as s:
            if s.get(UserRow, username):
                raise ValueError(f"User {username!r} already exists")
            s.add(UserRow(username=username, password_hash=pw_hash,
                          is_admin="true" if is_admin else "false"))
            s.commit()

    def _count():
        with Session() as s:
            return s.query(UserRow).count()

    monkeypatch.setattr(auth_core, "_get_user_row", _get)
    monkeypatch.setattr(auth_core, "_create_user_row", _create)
    monkeypatch.setattr(auth_core, "_user_count", _count)

    app = create_app(memory=MemoryStore())
    return TestClient(app)


# ── auth disabled (default) ──────────────────────────────────────────


def test_auth_status_disabled(client_noauth: TestClient) -> None:
    r = client_noauth.get("/auth/status")
    assert r.status_code == 200
    assert r.json()["auth_enabled"] is False


def test_history_accessible_without_token(client_noauth: TestClient) -> None:
    r = client_noauth.get("/api/history")
    assert r.status_code == 200


def test_run_accessible_without_token(client_noauth: TestClient) -> None:
    r = client_noauth.post("/api/run", json={
        "prompt": "test task",
        "planner_provider": "mock",
        "critic_provider": "mock",
    })
    assert r.status_code == 200


# ── auth enabled ─────────────────────────────────────────────────────


def test_login_with_default_admin(client_auth: TestClient) -> None:
    r = client_auth.post(
        "/auth/login",
        data={"username": "admin", "password": "admin"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["username"] == "admin"


def test_protected_endpoint_requires_token(client_auth: TestClient) -> None:
    r = client_auth.get("/api/history")
    assert r.status_code == 401


def test_protected_endpoint_works_with_token(client_auth: TestClient) -> None:
    token = client_auth.post(
        "/auth/login",
        data={"username": "admin", "password": "admin"},
    ).json()["access_token"]
    r = client_auth.get(
        "/api/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


def test_invalid_token_rejected(client_auth: TestClient) -> None:
    r = client_auth.get(
        "/api/history",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401


def test_wrong_password_rejected(client_auth: TestClient) -> None:
    r = client_auth.post(
        "/auth/login",
        data={"username": "admin", "password": "wrong"},
    )
    assert r.status_code == 401


def test_me_endpoint_returns_current_user(client_auth: TestClient) -> None:
    token = client_auth.post(
        "/auth/login",
        data={"username": "admin", "password": "admin"},
    ).json()["access_token"]
    r = client_auth.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "admin"
    assert r.json()["is_admin"] is True


def test_register_new_user_as_admin(client_auth: TestClient) -> None:
    token = client_auth.post(
        "/auth/login",
        data={"username": "admin", "password": "admin"},
    ).json()["access_token"]
    r = client_auth.post(
        "/auth/register",
        json={"username": "alice", "password": "securepass"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201


def test_register_duplicate_user_409(client_auth: TestClient) -> None:
    token = client_auth.post(
        "/auth/login",
        data={"username": "admin", "password": "admin"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client_auth.post("/auth/register", json={"username": "bob", "password": "password1"}, headers=headers)
    r = client_auth.post("/auth/register", json={"username": "bob", "password": "password2"}, headers=headers)
    assert r.status_code == 409


def test_short_password_rejected(client_auth: TestClient) -> None:
    token = client_auth.post(
        "/auth/login",
        data={"username": "admin", "password": "admin"},
    ).json()["access_token"]
    r = client_auth.post(
        "/auth/register",
        json={"username": "x", "password": "short"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422
