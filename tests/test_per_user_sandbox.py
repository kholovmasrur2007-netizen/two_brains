"""Tests for per-user sandbox isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.brains import build_per_user_executor
from app.sandbox import SandboxError, user_workspace


def test_user_workspace_returns_subdir(tmp_path: Path) -> None:
    p = user_workspace(tmp_path, "alice")
    assert p == tmp_path / "alice"


def test_user_workspace_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(SandboxError):
        user_workspace(tmp_path, "../escape")


def test_user_workspace_rejects_absolute(tmp_path: Path) -> None:
    with pytest.raises(SandboxError):
        user_workspace(tmp_path, "/etc/passwd")


@pytest.mark.parametrize("bad", ["", "a/b", "evil;rm", "..", "user with space"])
def test_user_workspace_rejects_unsafe_names(tmp_path: Path, bad: str) -> None:
    with pytest.raises(SandboxError):
        user_workspace(tmp_path, bad)


@pytest.mark.parametrize("ok", ["alice", "bob_42", "user.name", "User-Name", "abc"])
def test_user_workspace_accepts_safe_names(tmp_path: Path, ok: str) -> None:
    p = user_workspace(tmp_path, ok)
    assert p.name == ok


def test_two_users_get_isolated_workspaces(tmp_path: Path, monkeypatch) -> None:
    """Two users running local-agent must end up in different directories."""
    monkeypatch.setattr("app.config.settings.agent_workspace", str(tmp_path))

    alice = build_per_user_executor("local-agent", "alice")
    bob   = build_per_user_executor("local-agent", "bob")

    assert alice.sandbox.root == (tmp_path / "alice").resolve()
    assert bob.sandbox.root   == (tmp_path / "bob").resolve()
    assert alice.sandbox.root != bob.sandbox.root


def test_non_filesystem_provider_ignores_username(monkeypatch) -> None:
    """Mock executor doesn't touch disk — should be the same as build_executor."""
    e1 = build_per_user_executor("mock", "alice")
    e2 = build_per_user_executor("mock", None)
    # Both should be of the same type — not the agent executor variant.
    assert type(e1) is type(e2)


def test_no_username_falls_back_to_default(monkeypatch, tmp_path: Path) -> None:
    """When username is None the shared default workspace is used."""
    monkeypatch.setattr("app.config.settings.agent_workspace", str(tmp_path))

    executor = build_per_user_executor("local-agent", None)
    # Default sandbox is the configured agent_workspace itself, not a sub-dir.
    assert executor.sandbox.root == tmp_path.resolve()
