"""Tests for the brain factory registry and the Planner/Critic Protocols."""

from __future__ import annotations

import pytest

from app.brains import (
    Critic,
    Planner,
    PlannerBrain,
    CriticBrain,
    build_critic,
    build_planner,
    registered_critic_providers,
    registered_planner_providers,
)


def test_deterministic_provider_is_registered() -> None:
    assert "deterministic" in registered_planner_providers()
    assert "deterministic" in registered_critic_providers()


def test_build_planner_default_returns_deterministic_brain() -> None:
    planner = build_planner()
    assert isinstance(planner, PlannerBrain)
    # Protocol conformance — isinstance works because Planner is @runtime_checkable.
    assert isinstance(planner, Planner)


def test_build_critic_default_returns_deterministic_brain() -> None:
    critic = build_critic()
    assert isinstance(critic, CriticBrain)
    assert isinstance(critic, Critic)


def test_build_planner_unknown_provider_raises() -> None:
    with pytest.raises(ValueError) as exc:
        build_planner("does-not-exist")
    assert "available" in str(exc.value)


def test_build_critic_unknown_provider_raises() -> None:
    with pytest.raises(ValueError) as exc:
        build_critic("does-not-exist")
    assert "available" in str(exc.value)


def test_protocol_accepts_duck_typed_implementations() -> None:
    """A class doesn't need to inherit from the Protocol to satisfy it."""
    from app.types import PlanOutput, TaskInput

    class MyPlanner:
        def create_plan(self, task: TaskInput) -> PlanOutput:
            return PlanOutput(task_id=task.id, objective="duck")

    assert isinstance(MyPlanner(), Planner)
