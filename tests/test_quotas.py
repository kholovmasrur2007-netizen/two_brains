"""Tests for per-user daily quotas (DB-backed atomic counter)."""

from __future__ import annotations

import pytest

from app.security.quotas import DailyQuotaExceeded, check_and_record_quota, usage_today


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Bring up a fresh SQLite DB and turn USE_DB on for the duration."""
    db_url = f"sqlite:///{tmp_path}/q.db"
    monkeypatch.setattr("app.config.settings.use_db", True)
    monkeypatch.setattr("app.config.settings.database_url", db_url)
    monkeypatch.setattr("app.db.engine._engine", None)
    from app.db.engine import init_db
    init_db()


def test_first_call_succeeds(db) -> None:
    check_and_record_quota("alice")
    assert usage_today("alice") == 1


def test_increments_per_call(db) -> None:
    for _ in range(5):
        check_and_record_quota("bob")
    assert usage_today("bob") == 5


def test_exceeds_after_quota_reached(db, monkeypatch) -> None:
    monkeypatch.setattr("app.security.quotas.DAILY_TASK_QUOTA", 3)
    check_and_record_quota("eve")
    check_and_record_quota("eve")
    check_and_record_quota("eve")
    with pytest.raises(DailyQuotaExceeded):
        check_and_record_quota("eve")


def test_anonymous_user_unlimited(db) -> None:
    """No username → no quota enforcement (handled at auth layer)."""
    for _ in range(1000):
        check_and_record_quota(None)


def test_db_off_disables_quotas(monkeypatch) -> None:
    """Without a database we have nowhere to store the counter — allow all."""
    monkeypatch.setattr("app.config.settings.use_db", False)
    for _ in range(500):
        check_and_record_quota("frank")


def test_disable_flag_short_circuits(db, monkeypatch) -> None:
    """``QUOTA_DISABLED=true`` (read at import time as ``_DISABLED``) bypasses checks."""
    monkeypatch.setattr("app.security.quotas._DISABLED", True)
    monkeypatch.setattr("app.security.quotas.DAILY_TASK_QUOTA", 1)
    for _ in range(50):
        check_and_record_quota("greg")  # would otherwise raise after 1
