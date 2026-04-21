"""Tests for the orchestrator's iterative plan/critique loop."""

from __future__ import annotations

import pytest

import app.config
from app.brains.base import RevisingPlanner
from app.brains.brain1_planner import PlannerBrain
from app.brains.brain1_planner_llm import LLMPlannerBrain
from app.core.orchestrator import TwoBrainOrchestrator
from app.llm.mock import MockLLMClient
from app.types import CritiqueOutput, PlanOutput, TaskInput


# ── Helpers ────────────────────────────────────────────────────────────


def _strong_plan(task_id: str) -> PlanOutput:
    """A plan that the deterministic critic will accept."""
    return PlanOutput(
        task_id=task_id,
        objective="Build a calculator.",
        assumptions=["Modern browser available."],
        constraints=["single-file"],
        risks=["Browser incompatibility across old versions."],
        steps=[
            "Set up the HTML skeleton with one style and one script tag.",
            "Implement the arithmetic engine with unit tests for edge cases.",
            "Wire up the UI and verify manually in two browsers.",
            "Measure load time under 500 ms and fix any regressions.",
        ],
        success_criteria=[
            "All unit tests pass with no failures.",
            "Page loads in under 500 ms on mid-range hardware.",
            "No critical console errors during manual QA.",
        ],
        planner_notes="Calculator.",
    )


class _StagedPlanner:
    """Returns a scripted sequence: first plan via create, the rest via revise."""

    def __init__(self, plans: list[PlanOutput]) -> None:
        assert plans, "staged planner needs at least one plan"
        self._plans = list(plans)
        self._next = 1  # next index to serve on revise

    def create_plan(self, task: TaskInput) -> PlanOutput:
        return self._plans[0]

    def revise_plan(
        self,
        task: TaskInput,
        prior_plan: PlanOutput,
        critique: CritiqueOutput,
    ) -> PlanOutput:
        if self._next < len(self._plans):
            plan = self._plans[self._next]
            self._next += 1
            return plan
        return prior_plan  # exhausted - no further improvement


# ── Protocol conformance ───────────────────────────────────────────────


def test_deterministic_planner_is_not_a_revising_planner() -> None:
    """Deterministic brain has no revise_plan, so one-shot only."""
    assert not isinstance(PlannerBrain(), RevisingPlanner)


def test_llm_planner_is_a_revising_planner() -> None:
    """The LLM planner can be iterated on."""
    assert isinstance(LLMPlannerBrain(llm=MockLLMClient()), RevisingPlanner)


def test_staged_planner_fixture_satisfies_revising_planner() -> None:
    """Sanity check on the helper used by the remaining tests."""
    assert isinstance(_StagedPlanner([PlanOutput(task_id="x")]), RevisingPlanner)


# ── Orchestrator behaviour ─────────────────────────────────────────────


def test_non_revising_planner_runs_exactly_one_iteration() -> None:
    """Default deterministic path: no loop, iterations == 1."""
    task = TaskInput(id="t-1", prompt="Build a small web app.")
    result = TwoBrainOrchestrator().run(task)
    assert result.iterations == 1


def test_orchestrator_stops_when_critique_accepts() -> None:
    """First plan is weak, second is strong -> loop runs twice and stops."""
    task = TaskInput(id="t-1", prompt="Build X.")
    planner = _StagedPlanner([
        PlanOutput(task_id="t-1"),      # empty -> rejected
        _strong_plan("t-1"),             # accepted -> loop exits
    ])
    result = TwoBrainOrchestrator(planner=planner).run(task)

    assert result.iterations == 2
    assert result.ready_for_execution is True
    # The final plan is the strong one, not the empty one.
    assert result.plan.objective.startswith("Build a calculator")


def test_orchestrator_stops_at_max_iterations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Revisions that never converge must still terminate at MAX_ITERATIONS."""
    # Pin max_iterations for this test.
    class _Stub:
        memory_path = None
        planner_provider = "deterministic"
        critic_provider = "deterministic"
        max_iterations = 3
    monkeypatch.setattr(app.config, "settings", _Stub())

    task = TaskInput(id="t-1", prompt="X")
    bad = PlanOutput(task_id="t-1")  # always rejected by critic

    class _AlwaysBadPlanner(_StagedPlanner):
        def revise_plan(self, task, prior_plan, critique):
            return bad  # never improve

    planner = _AlwaysBadPlanner([bad])
    result = TwoBrainOrchestrator(planner=planner).run(task)

    assert result.iterations == 3
    assert result.ready_for_execution is False


def test_orchestrator_saves_intermediate_iterations_in_memory() -> None:
    """Each iteration's plan overwrites the previous in memory, but the final
    saved artefacts match the last iteration."""
    task = TaskInput(id="t-1", prompt="X")
    planner = _StagedPlanner([
        PlanOutput(task_id="t-1"),
        _strong_plan("t-1"),
    ])
    orchestrator = TwoBrainOrchestrator(planner=planner)

    result = orchestrator.run(task)

    saved = orchestrator.memory.get_plan("t-1")
    assert saved is not None
    assert saved.objective == result.plan.objective  # final, not intermediate


def test_llm_planner_revise_parses_valid_json_response() -> None:
    """LLMPlannerBrain.revise_plan follows the same JSON contract as create_plan."""
    import json

    payload = {
        "task_id": "t-1",
        "objective": "Revised objective.",
        "assumptions": ["a"],
        "constraints": [],
        "risks": ["r"],
        "steps": ["step one.......", "step two.......", "step three......."],
        "success_criteria": ["All checks pass."],
        "planner_notes": "Revised.",
    }
    llm = MockLLMClient(responses=[json.dumps(payload)])
    task = TaskInput(id="t-1", prompt="Build X")
    prior = PlanOutput(task_id="t-1")
    critique = CritiqueOutput(task_id="t-1", overall_score=40, final_judgement="rejected")

    revised = LLMPlannerBrain(llm=llm).revise_plan(task, prior, critique)

    assert revised.task_id == "t-1"
    assert revised.objective == "Revised objective."


def test_llm_planner_revise_returns_prior_on_broken_response() -> None:
    """If the LLM response is garbage, keep the prior plan (no improvement)."""
    llm = MockLLMClient(responses=["not json"])
    task = TaskInput(id="t-1", prompt="Build X")
    prior = PlanOutput(task_id="t-1", objective="original")
    critique = CritiqueOutput(task_id="t-1", overall_score=40, final_judgement="rejected")

    revised = LLMPlannerBrain(llm=llm).revise_plan(task, prior, critique)

    assert revised is prior
