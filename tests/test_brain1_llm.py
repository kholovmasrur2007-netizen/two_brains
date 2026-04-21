"""Tests for the LLM-backed planner (Brain 1)."""

from __future__ import annotations

import json

from app.brains.brain1_planner_llm import LLMPlannerBrain
from app.llm.base import LLMClient, LLMProviderError
from app.llm.mock import MockLLMClient
from app.types import TaskInput


def _good_plan_json(task_id: str = "t-1") -> str:
    """A JSON payload that parses cleanly into a PlanOutput."""
    return json.dumps({
        "task_id": task_id,
        "objective": "Build a small web app.",
        "assumptions": ["Environment is ready."],
        "constraints": ["single-file"],
        "risks": ["Browser incompatibility."],
        "steps": [
            "Set up the HTML skeleton with one style and one script tag.",
            "Implement the core logic with unit tests covering edge cases.",
            "Wire up the UI and verify manually in two browsers.",
        ],
        "success_criteria": ["All tests pass.", "No console errors."],
        "planner_notes": "Small single-file web app.",
    })


def test_llm_planner_parses_valid_json_response() -> None:
    task = TaskInput(id="t-1", prompt="Build a web app", constraints=["single-file"])
    llm = MockLLMClient(responses=[_good_plan_json("t-1")])

    plan = LLMPlannerBrain(llm=llm).create_plan(task)

    assert plan.task_id == "t-1"
    assert plan.objective == "Build a small web app."
    assert len(plan.steps) == 3
    assert plan.success_criteria == ["All tests pass.", "No console errors."]


def test_llm_planner_forwards_system_and_user_prompts() -> None:
    task = TaskInput(id="t-1", prompt="Build X", constraints=["no backend"])
    llm = MockLLMClient(responses=[_good_plan_json("t-1")])

    LLMPlannerBrain(llm=llm).create_plan(task)

    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call["json_mode"] is True
    assert "JSON" in call["system"]
    assert task.prompt in call["user"]
    assert "no backend" in call["user"]


def test_llm_planner_forces_task_id_from_input() -> None:
    """Even if the model returns a different task_id, we override it."""
    task = TaskInput(id="caller-id", prompt="Build X")
    llm = MockLLMClient(responses=[_good_plan_json("model-picked-something-else")])

    plan = LLMPlannerBrain(llm=llm).create_plan(task)

    assert plan.task_id == "caller-id"


def test_llm_planner_falls_back_on_invalid_json() -> None:
    """Garbage response must not raise — fall back to deterministic planner."""
    task = TaskInput(id="t-1", prompt="Build X")
    llm = MockLLMClient(responses=["not json at all"])

    plan = LLMPlannerBrain(llm=llm).create_plan(task)

    assert plan.task_id == "t-1"
    assert plan.steps, "fallback planner must still produce steps"


def test_llm_planner_falls_back_on_schema_mismatch() -> None:
    """Valid JSON but wrong shape must also fall back."""
    task = TaskInput(id="t-1", prompt="Build X")
    llm = MockLLMClient(responses=['{"unrelated": "payload"}'])

    plan = LLMPlannerBrain(llm=llm).create_plan(task)

    assert plan.task_id == "t-1"
    assert plan.steps


def test_llm_planner_falls_back_on_provider_error() -> None:
    """Network / auth failures must surface as a fallback, not an exception."""

    class _BrokenLLM(LLMClient):
        def complete(self, system, user, *, json_mode=False, temperature=0.0, max_tokens=None):
            raise LLMProviderError("simulated network failure")

    task = TaskInput(id="t-1", prompt="Build X")
    plan = LLMPlannerBrain(llm=_BrokenLLM()).create_plan(task)

    assert plan.task_id == "t-1"
    assert plan.steps
