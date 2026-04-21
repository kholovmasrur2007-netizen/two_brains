"""Tests for the memory layer."""

from __future__ import annotations

import json
from pathlib import Path

from app.memory.store import MemoryStore
from app.types import CritiqueOutput, FinalResult, PlanOutput, TaskInput


# ── fixtures ───────────────────────────────────────────────────────────


def _task() -> TaskInput:
    return TaskInput(id="t-1", prompt="Build an app.", constraints=["no backend"])


def _plan() -> PlanOutput:
    return PlanOutput(
        task_id="t-1",
        objective="Build an app.",
        assumptions=["Environment is ready."],
        constraints=["no backend"],
        risks=["Browser compatibility."],
        steps=["Step one.", "Step two.", "Step three."],
        success_criteria=["All tests pass.", "No console errors."],
        planner_notes="Build an app.",
    )


def _critique() -> CritiqueOutput:
    return CritiqueOutput(
        task_id="t-1",
        overall_score=90,
        strengths=["Clear objective."],
        weaknesses=[],
        missing_elements=[],
        contradictions=[],
        risk_flags=[],
        improvement_suggestions=[],
        revised_step_notes=[],
        final_judgement="accepted",
    )


def _result(task: TaskInput, plan: PlanOutput, critique: CritiqueOutput) -> FinalResult:
    return FinalResult(
        task_id=task.id,
        original_task=task,
        plan=plan,
        critique=critique,
        final_recommendation="Plan is ready to execute.",
        ready_for_execution=True,
    )


# ── in-memory behaviour ────────────────────────────────────────────────


def test_save_and_get_round_trip() -> None:
    store = MemoryStore()
    task, plan, critique = _task(), _plan(), _critique()
    result = _result(task, plan, critique)

    store.save_task(task)
    store.save_plan(plan)
    store.save_critique(critique)
    store.save_result(result)

    assert store.get_task("t-1") == task
    assert store.get_plan("t-1") == plan
    assert store.get_critique("t-1") == critique
    assert store.get_result("t-1") == result


def test_get_missing_id_returns_none() -> None:
    store = MemoryStore()
    assert store.get_task("missing") is None
    assert store.get_plan("missing") is None
    assert store.get_critique("missing") is None
    assert store.get_result("missing") is None


def test_save_overwrites_previous_entry() -> None:
    """Saving a second plan for the same task_id replaces the first."""
    store = MemoryStore()
    store.save_plan(PlanOutput(task_id="t-1", objective="v1", steps=["a"]))
    store.save_plan(PlanOutput(task_id="t-1", objective="v2", steps=["b"]))

    retrieved = store.get_plan("t-1")
    assert retrieved is not None
    assert retrieved.objective == "v2"


def test_known_task_ids_lists_saved_tasks() -> None:
    store = MemoryStore()
    store.save_task(TaskInput(id="a", prompt="a"))
    store.save_task(TaskInput(id="b", prompt="b"))
    assert set(store.known_task_ids()) == {"a", "b"}


# ── JSON persistence ───────────────────────────────────────────────────


def test_persistence_round_trip(tmp_path: Path) -> None:
    """Save with a path, then reopen — every artefact must survive."""
    path = tmp_path / "memory.json"
    task, plan, critique = _task(), _plan(), _critique()
    result = _result(task, plan, critique)

    writer = MemoryStore(path=path)
    writer.save_task(task)
    writer.save_plan(plan)
    writer.save_critique(critique)
    writer.save_result(result)

    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data.keys()) == {"tasks", "plans", "critiques", "results"}
    assert "t-1" in data["tasks"]

    reader = MemoryStore(path=path)
    assert reader.get_task("t-1") == task
    assert reader.get_plan("t-1") == plan
    assert reader.get_critique("t-1") == critique
    assert reader.get_result("t-1") == result


def test_corrupt_file_does_not_crash(tmp_path: Path) -> None:
    """If the JSON file is unreadable, the store starts empty instead of raising."""
    path = tmp_path / "broken.json"
    path.write_text("{this is not valid json", encoding="utf-8")

    store = MemoryStore(path=path)  # must not raise

    assert store.get_task("any") is None
    assert store.tasks == {}


def test_schema_mismatch_does_not_crash(tmp_path: Path) -> None:
    """A well-formed JSON file with the wrong shape resets the store to empty."""
    path = tmp_path / "wrong.json"
    path.write_text(
        json.dumps({"tasks": {"t-1": {"id": "t-1"}}}),  # missing required 'prompt'
        encoding="utf-8",
    )

    store = MemoryStore(path=path)

    assert store.get_task("t-1") is None
    assert store.tasks == {}


def test_missing_file_starts_empty(tmp_path: Path) -> None:
    """A non-existent path is created lazily on the first write."""
    path = tmp_path / "subdir" / "memory.json"
    assert not path.exists()

    store = MemoryStore(path=path)
    assert store.tasks == {}

    store.save_task(_task())
    assert path.exists()
