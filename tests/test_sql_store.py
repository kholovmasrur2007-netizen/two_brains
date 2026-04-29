"""Tests for SQLMemoryStore — same contract as MemoryStore, backed by SQLite."""

from __future__ import annotations

import os
import pytest

from app.types import CritiqueOutput, FinalResult, PlanOutput, TaskInput


@pytest.fixture
def store(tmp_path):
    """A fresh SQLMemoryStore with isolated per-test SQLite database."""
    from app.db.store import SQLMemoryStore
    return SQLMemoryStore(url=f"sqlite:///{tmp_path}/test.db")


def _task(tid: str = "t-1") -> TaskInput:
    return TaskInput(id=tid, prompt="do X")


def _plan(tid: str = "t-1") -> PlanOutput:
    return PlanOutput(task_id=tid, objective="obj", steps=["step 1"])


def _critique(tid: str = "t-1") -> CritiqueOutput:
    return CritiqueOutput(
        task_id=tid, overall_score=90,
        final_judgement="accepted",
        strengths=["good"], weaknesses=[], missing_elements=[],
        contradictions=[], risk_flags=[], improvement_suggestions=[],
        revised_step_notes=[],
    )


def _result(tid: str = "t-1") -> FinalResult:
    return FinalResult(
        task_id=tid, original_task=_task(tid), plan=_plan(tid),
        critique=_critique(tid), final_recommendation="ready",
        ready_for_execution=True, iterations=1,
    )


def test_save_and_get_task(store) -> None:
    task = _task()
    store.save_task(task)
    loaded = store.get_task("t-1")
    assert loaded is not None
    assert loaded.id == "t-1"
    assert loaded.prompt == "do X"


def test_save_and_get_plan(store) -> None:
    store.save_plan(_plan())
    loaded = store.get_plan("t-1")
    assert loaded is not None
    assert loaded.steps == ["step 1"]


def test_save_and_get_critique(store) -> None:
    store.save_critique(_critique())
    loaded = store.get_critique("t-1")
    assert loaded is not None
    assert loaded.overall_score == 90


def test_save_and_get_result(store) -> None:
    store.save_result(_result())
    loaded = store.get_result("t-1")
    assert loaded is not None
    assert loaded.ready_for_execution is True


def test_get_returns_none_for_unknown(store) -> None:
    assert store.get_task("never") is None
    assert store.get_plan("never") is None
    assert store.get_critique("never") is None
    assert store.get_result("never") is None


def test_known_task_ids_grows(store) -> None:
    assert store.known_task_ids() == []
    store.save_task(_task("a"))
    store.save_task(_task("b"))
    ids = store.known_task_ids()
    assert set(ids) == {"a", "b"}


def test_save_overwrites_existing(store) -> None:
    store.save_task(TaskInput(id="t-1", prompt="original"))
    store.save_task(TaskInput(id="t-1", prompt="updated"))
    loaded = store.get_task("t-1")
    assert loaded.prompt == "updated"


def test_tasks_property_returns_dict(store) -> None:
    store.save_task(_task("x"))
    assert "x" in store.tasks
