"""Tests for the deterministic Executor (Brain 3)."""

from __future__ import annotations

from app.brains.brain3_executor import ExecutorBrain
from app.types import PlanOutput, TaskInput


def _task(prompt: str = "Ship X") -> TaskInput:
    return TaskInput(id="t-1", prompt=prompt)


def _plan(steps: list[str]) -> PlanOutput:
    return PlanOutput(task_id="t-1", objective="obj", steps=steps)


def test_executor_returns_one_step_result_per_plan_step() -> None:
    plan = _plan(["First step.", "Second step.", "Third step."])
    out = ExecutorBrain().execute_plan(_task(), plan)

    assert out.task_id == "t-1"
    assert len(out.step_results) == 3
    assert [r.index for r in out.step_results] == [1, 2, 3]
    assert [r.step for r in out.step_results] == plan.steps


def test_executor_marks_routine_steps_succeeded() -> None:
    plan = _plan(["Outline the high-level solution.", "Implement the helper module."])
    out = ExecutorBrain().execute_plan(_task(), plan)

    assert all(r.status == "succeeded" for r in out.step_results)
    assert out.overall_status == "completed"


def test_executor_skips_steps_requiring_human_action() -> None:
    """Steps that need a stakeholder / approval must be reported as skipped, never invented."""
    plan = _plan([
        "Confirm with the requester that the scope is correct.",
        "Implement the feature.",
    ])
    out = ExecutorBrain().execute_plan(_task(), plan)

    statuses = [r.status for r in out.step_results]
    assert statuses[0] == "skipped"
    assert statuses[1] == "succeeded"
    # Skipped + succeeded with no failure → still "completed".
    assert out.overall_status == "completed"


def test_executor_flags_risky_steps_in_output() -> None:
    plan = _plan(["Migrate the production database to the new schema."])
    out = ExecutorBrain().execute_plan(_task(), plan)

    r = out.step_results[0]
    assert r.status == "succeeded"
    assert "high-risk" in r.output.lower() or "caveat" in r.output.lower()


def test_executor_handles_empty_plan() -> None:
    out = ExecutorBrain().execute_plan(_task(), _plan([]))

    assert out.step_results == []
    assert out.overall_status == "not_run"
    assert "no steps" in out.summary.lower()


def test_executor_summary_counts_match_step_results() -> None:
    plan = _plan([
        "Confirm with the requester that the scope is correct.",  # skipped
        "Implement the feature.",                                  # succeeded
        "Validate the deliverable.",                               # succeeded
    ])
    out = ExecutorBrain().execute_plan(_task(), plan)

    assert "1 skipped" in out.summary
    assert "2 succeeded" in out.summary
    assert "0 failed" in out.summary


def test_executor_notes_explain_no_side_effects() -> None:
    """The deterministic executor must make its dry-run nature explicit."""
    out = ExecutorBrain().execute_plan(_task(), _plan(["Do something."]))
    assert "no side effects" in out.executor_notes.lower()
