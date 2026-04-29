"""Tests for the slowapi rate-limit integration."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.memory.store import MemoryStore
from app.web.server import create_app


@pytest.fixture
def client_limited(monkeypatch) -> TestClient:
    """Build an app with the /api/run limiter forced down to 2/minute."""
    # Patch the env-derived constant used at decorator time.
    monkeypatch.setattr("app.security.rate_limit.RATE_LIMIT_RUN", "2/minute")
    # Also patch the limiter we already imported in server.py.
    monkeypatch.setattr("app.web.server.RATE_LIMIT_RUN", "2/minute")
    monkeypatch.setattr("app.security.rate_limit.limiter.enabled", True)
    return TestClient(create_app(memory=MemoryStore()))


@pytest.fixture
def client_unlimited(monkeypatch) -> TestClient:
    monkeypatch.setattr("app.security.rate_limit.limiter.enabled", False)
    return TestClient(create_app(memory=MemoryStore()))


def test_disabled_limiter_allows_many_calls(client_unlimited: TestClient) -> None:
    for _ in range(10):
        r = client_unlimited.post("/api/run", json={
            "prompt": "x", "planner_provider": "mock", "critic_provider": "mock",
        })
        assert r.status_code == 200


def test_429_response_format(client_unlimited: TestClient) -> None:
    """Trigger a fake rate-limit error and verify the JSON body shape."""
    from slowapi.errors import RateLimitExceeded
    from app.security.rate_limit import rate_limit_handler
    import asyncio

    class FakeLimit:
        error_message = "test/minute"

    async def _go():
        from fastapi import Request
        scope = {"type": "http", "headers": [], "method": "GET", "path": "/x",
                 "query_string": b"", "client": ("127.0.0.1", 1)}
        async def receive():
            return {"type": "http.request"}
        req = Request(scope, receive)
        exc = RateLimitExceeded(FakeLimit())
        return await rate_limit_handler(req, exc)

    response = asyncio.run(_go())
    assert response.status_code == 429
    assert "Retry-After" in response.headers
