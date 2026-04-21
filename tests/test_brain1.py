"""Tests for Brain 1 — Planner."""

from __future__ import annotations

from app.brains.brain1_planner import PlannerBrain
from app.types import TaskInput


def test_planner_produces_structured_plan() -> None:
    """create_plan() must fill every semantic field of PlanOutput."""
    task = TaskInput(
        id="t-1",
        prompt="Build a small calculator web app with tests.",
        constraints=["single-file HTML", "no backend"],
    )

    plan = PlannerBrain().create_plan(task)

    assert plan.task_id == "t-1"
    # Objective picks up the action verb "Build" and returns the sentence as-is.
    assert plan.objective.lower().startswith("build")
    # Every list field must be non-empty so the critic has something to review.
    assert plan.steps, "planner must produce at least one step"
    assert plan.success_criteria, "planner must produce at least one success criterion"
    assert plan.assumptions, "planner must produce baseline assumptions"
    assert plan.risks, "planner must surface at least one risk (baseline or keyword-driven)"
    # Constraints from the caller are preserved verbatim.
    assert plan.constraints == ["single-file HTML", "no backend"]
    # Planner notes should contain a summary of the prompt.
    assert "calculator" in plan.planner_notes.lower()
