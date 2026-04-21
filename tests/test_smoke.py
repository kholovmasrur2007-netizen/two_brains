"""Smoke tests: scaffold imports and the full Planner→Critic pipeline runs."""

from __future__ import annotations

from app.core.orchestrator import TwoBrainOrchestrator
from app.types import FinalResult, TaskInput
from app.utils.helpers import new_id


def test_scaffold_imports() -> None:
    """Every top-level module must import without error."""
    from app import config, main  # noqa: F401
    from app.brains import brain1_planner, brain2_critic  # noqa: F401
    from app.core import logger, orchestrator  # noqa: F401
    from app.memory import store  # noqa: F401


def test_end_to_end_pipeline_returns_final_result() -> None:
    """TaskInput in → fully-populated FinalResult out."""
    task = TaskInput(
        id=new_id(),
        prompt="Build a small calculator web app.",
        constraints=["single-file HTML"],
    )

    result = TwoBrainOrchestrator().run(task)

    assert isinstance(result, FinalResult)
    assert result.task_id == task.id
    assert result.original_task.id == task.id
    assert result.plan.task_id == task.id
    assert result.critique.task_id == task.id
    assert isinstance(result.ready_for_execution, bool)
    assert result.final_recommendation.strip(), "recommendation must not be empty"


def test_pipeline_blocks_execution_when_critique_has_blockers() -> None:
    """Empty prompt → many missing elements → ready_for_execution must be False."""
    task = TaskInput(id=new_id(), prompt="")

    result = TwoBrainOrchestrator().run(task)

    assert result.ready_for_execution is False
    assert "revise" in result.final_recommendation.lower()


def test_pipeline_persists_artefacts_in_memory() -> None:
    """Orchestrator should have recorded every artefact in its MemoryStore."""
    orchestrator = TwoBrainOrchestrator()
    task = TaskInput(id=new_id(), prompt="Build a simple REST API.")

    result = orchestrator.run(task)

    store = orchestrator.memory
    assert task.id in store.tasks
    assert store.plans[task.id]
    assert store.critiques[task.id]
    assert store.results[task.id] is result


def test_pipeline_runs_through_mock_llm_providers() -> None:
    """The `mock` providers wire LLM brains end-to-end without touching the network.

    Covers: factory registration, LLM brain JSON parsing, task_id pinning,
    orchestrator readiness rule — all in one pass.
    """
    from app.brains import build_critic, build_planner

    orchestrator = TwoBrainOrchestrator(
        planner=build_planner("mock"),
        critic=build_critic("mock"),
    )
    task = TaskInput(id=new_id(), prompt="Ship the next release.")

    result = orchestrator.run(task)

    # task_id pinning: LLM brains must rewrite the canned "mock" id back to task.id.
    assert result.plan.task_id == task.id
    assert result.critique.task_id == task.id
    # The canned mock plan is good enough to pass the orchestrator's readiness bar.
    assert result.ready_for_execution is True
    # The canned content is actually what was used, not the deterministic fallback.
    assert "[MOCK]" in result.plan.objective
