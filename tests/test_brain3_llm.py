"""Tests for the LLM-backed executor (Brain 3)."""

from __future__ import annotations

import json

from app.brains.brain3_executor_llm import LLMExecutorBrain
from app.llm.base import LLMClient, LLMProviderError
from app.llm.mock import MockLLMClient
from app.types import PlanOutput, TaskInput


def _task() -> TaskInput:
    return TaskInput(id="t-1", prompt="Ship X")


def _plan() -> PlanOutput:
    return PlanOutput(task_id="t-1", objective="obj", steps=["Do A.", "Do B."])


def _good_execution_json(task_id: str = "t-1") -> str:
    return json.dumps({
        "task_id": task_id,
        "overall_status": "completed",
        "step_results": [
            {"index": 1, "step": "Do A.", "status": "succeeded",
             "output": "A produced X.", "error": ""},
            {"index": 2, "step": "Do B.", "status": "succeeded",
             "output": "B produced Y.", "error": ""},
        ],
        "summary": "completed: 2 succeeded.",
        "executor_notes": "All steps simulated cleanly.",
    })


def test_llm_executor_parses_valid_json_response() -> None:
    llm = MockLLMClient(responses=[_good_execution_json()])

    out = LLMExecutorBrain(llm=llm).execute_plan(_task(), _plan())

    assert out.task_id == "t-1"
    assert out.overall_status == "completed"
    assert len(out.step_results) == 2
    assert out.step_results[0].output == "A produced X."


def test_llm_executor_forwards_system_and_user_prompts() -> None:
    llm = MockLLMClient(responses=[_good_execution_json()])

    LLMExecutorBrain(llm=llm).execute_plan(_task(), _plan())

    assert len(llm.calls) == 1
    call = llm.calls[0]
    assert call["json_mode"] is True
    assert "execution agent" in call["system"].lower()
    # Both task prompt and the plan must be visible to the model.
    assert "Ship X" in call["user"]
    assert "Do A." in call["user"]


def test_llm_executor_forces_task_id_from_input() -> None:
    """Even if the model returns a different task_id, we override it."""
    llm = MockLLMClient(responses=[_good_execution_json("model-picked-something-else")])
    task = TaskInput(id="caller-id", prompt="Ship X")
    plan = PlanOutput(task_id="caller-id", objective="obj", steps=["Do A."])

    out = LLMExecutorBrain(llm=llm).execute_plan(task, plan)

    assert out.task_id == "caller-id"


def test_llm_executor_falls_back_on_invalid_json() -> None:
    """Garbage response must not raise — fall back to deterministic executor."""
    llm = MockLLMClient(responses=["definitely not json"])

    out = LLMExecutorBrain(llm=llm).execute_plan(_task(), _plan())

    assert out.task_id == "t-1"
    assert out.step_results, "fallback executor must still produce step results"


def test_llm_executor_falls_back_on_schema_mismatch() -> None:
    llm = MockLLMClient(responses=['{"unrelated": "payload"}'])

    out = LLMExecutorBrain(llm=llm).execute_plan(_task(), _plan())

    assert out.task_id == "t-1"
    assert out.step_results


def test_llm_executor_falls_back_on_provider_error() -> None:
    """Network / auth failures must surface as a fallback, not an exception."""

    class _BrokenLLM(LLMClient):
        def complete(self, system, user, *, json_mode=False, temperature=0.0, max_tokens=None):
            raise LLMProviderError("simulated network failure")

    out = LLMExecutorBrain(llm=_BrokenLLM()).execute_plan(_task(), _plan())

    assert out.task_id == "t-1"
    assert out.step_results
