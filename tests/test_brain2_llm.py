"""Tests for the LLM-backed critic (Brain 2)."""

from __future__ import annotations

import json

from app.brains.brain2_critic_llm import LLMCriticBrain
from app.llm.base import LLMClient, LLMProviderError
from app.llm.mock import MockLLMClient
from app.types import PlanOutput


def _sample_plan(task_id: str = "t-1") -> PlanOutput:
    return PlanOutput(
        task_id=task_id,
        objective="Build a calculator.",
        assumptions=["Modern browser."],
        constraints=["single-file"],
        risks=["Browser compatibility."],
        steps=[
            "Set up HTML skeleton.",
            "Implement arithmetic logic with tests.",
            "Wire up the UI and verify in Chrome.",
        ],
        success_criteria=["All tests pass."],
        planner_notes="Calculator",
    )


def _good_critique_json(task_id: str = "t-1") -> str:
    """A JSON payload that parses cleanly into a CritiqueOutput."""
    return json.dumps({
        "task_id": task_id,
        "overall_score": 88,
        "strengths": ["Clear objective.", "Three concrete steps."],
        "weaknesses": ["Success criterion is vague."],
        "missing_elements": [],
        "contradictions": [],
        "risk_flags": [],
        "improvement_suggestions": ["Add a measurable threshold to the success criterion."],
        "revised_step_notes": [],
        "final_judgement": "accepted",
    })


def test_llm_critic_parses_valid_json_response() -> None:
    plan = _sample_plan()
    llm = MockLLMClient(responses=[_good_critique_json("t-1")])

    critique = LLMCriticBrain(llm=llm).review_plan(plan)

    assert critique.task_id == "t-1"
    assert critique.overall_score == 88
    assert critique.final_judgement == "accepted"
    assert critique.strengths == ["Clear objective.", "Three concrete steps."]


def test_llm_critic_forwards_system_and_user_prompts() -> None:
    plan = _sample_plan()
    llm = MockLLMClient(responses=[_good_critique_json("t-1")])

    LLMCriticBrain(llm=llm).review_plan(plan)

    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call["json_mode"] is True
    assert "critique" in call["system"].lower()
    # The plan itself must appear in the user prompt so the model can see it.
    assert plan.objective in call["user"]
    assert "Set up HTML skeleton." in call["user"]


def test_llm_critic_forces_task_id_from_plan() -> None:
    """Even if the model returns a different task_id, we override it."""
    plan = _sample_plan(task_id="real-id")
    llm = MockLLMClient(responses=[_good_critique_json("model-picked-this")])

    critique = LLMCriticBrain(llm=llm).review_plan(plan)

    assert critique.task_id == "real-id"


def test_llm_critic_falls_back_on_invalid_json() -> None:
    """Garbage response must not raise — fall back to deterministic critic."""
    plan = _sample_plan()
    llm = MockLLMClient(responses=["not json at all"])

    critique = LLMCriticBrain(llm=llm).review_plan(plan)

    assert critique.task_id == plan.task_id
    # Deterministic critic always produces a score and a judgement.
    assert isinstance(critique.overall_score, int)
    assert critique.final_judgement in {
        "accepted", "needs_minor_revision", "needs_major_revision", "rejected",
    }


def test_llm_critic_falls_back_on_schema_mismatch() -> None:
    """Valid JSON but wrong shape must also fall back."""
    plan = _sample_plan()
    llm = MockLLMClient(responses=['{"unrelated": "payload"}'])

    critique = LLMCriticBrain(llm=llm).review_plan(plan)

    assert critique.task_id == plan.task_id
    assert isinstance(critique.overall_score, int)


def test_llm_critic_falls_back_on_provider_error() -> None:
    """Network / auth failures must surface as a fallback, not an exception."""

    class _BrokenLLM(LLMClient):
        def complete(self, system, user, *, json_mode=False, temperature=0.0, max_tokens=None):
            raise LLMProviderError("simulated auth failure")

    plan = _sample_plan()
    critique = LLMCriticBrain(llm=_BrokenLLM()).review_plan(plan)

    assert critique.task_id == plan.task_id
    assert isinstance(critique.overall_score, int)
