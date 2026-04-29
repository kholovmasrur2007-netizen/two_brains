"""Tests for the brain factory registry and the Planner/Critic/Executor Protocols."""

from __future__ import annotations

import pytest

from app.brains import (
    Critic,
    CriticBrain,
    Executor,
    ExecutorBrain,
    Planner,
    PlannerBrain,
    build_critic,
    build_executor,
    build_planner,
    registered_critic_providers,
    registered_executor_providers,
    registered_planner_providers,
)


def test_deterministic_provider_is_registered() -> None:
    assert "deterministic" in registered_planner_providers()
    assert "deterministic" in registered_critic_providers()
    assert "deterministic" in registered_executor_providers()


def test_safety_critic_provider_is_registered() -> None:
    """v3.0: the SafetyCritic provider must be discoverable through the factory."""
    from app.brains.brain2_critic_safety import SafetyCritic

    assert "safety" in registered_critic_providers()
    critic = build_critic("safety")
    assert isinstance(critic, SafetyCritic)
    assert isinstance(critic, Critic)


def test_build_planner_default_returns_deterministic_brain() -> None:
    planner = build_planner()
    assert isinstance(planner, PlannerBrain)
    # Protocol conformance — isinstance works because Planner is @runtime_checkable.
    assert isinstance(planner, Planner)


def test_build_critic_default_returns_deterministic_brain() -> None:
    critic = build_critic()
    assert isinstance(critic, CriticBrain)
    assert isinstance(critic, Critic)


def test_build_executor_default_returns_deterministic_brain() -> None:
    executor = build_executor()
    assert isinstance(executor, ExecutorBrain)
    assert isinstance(executor, Executor)


def test_build_planner_unknown_provider_raises() -> None:
    with pytest.raises(ValueError) as exc:
        build_planner("does-not-exist")
    assert "available" in str(exc.value)


def test_build_critic_unknown_provider_raises() -> None:
    with pytest.raises(ValueError) as exc:
        build_critic("does-not-exist")
    assert "available" in str(exc.value)


def test_build_executor_unknown_provider_raises() -> None:
    with pytest.raises(ValueError) as exc:
        build_executor("does-not-exist")
    assert "available" in str(exc.value)


def test_mock_executor_provider_is_registered() -> None:
    """The mock provider must wire the LLMExecutorBrain end-to-end."""
    from app.brains.brain3_executor_llm import LLMExecutorBrain

    executor = build_executor("mock")
    assert isinstance(executor, LLMExecutorBrain)
    assert isinstance(executor, Executor)


def test_protocol_accepts_duck_typed_implementations() -> None:
    """A class doesn't need to inherit from the Protocol to satisfy it."""
    from app.types import ExecutionOutput, PlanOutput, TaskInput

    class MyPlanner:
        def create_plan(self, task: TaskInput) -> PlanOutput:
            return PlanOutput(task_id=task.id, objective="duck")

    assert isinstance(MyPlanner(), Planner)

    class MyExecutor:
        def execute_plan(self, task: TaskInput, plan: PlanOutput) -> ExecutionOutput:
            return ExecutionOutput(task_id=task.id, overall_status="not_run")

    assert isinstance(MyExecutor(), Executor)
