"""Brain 1 — LLM-backed Planner.

Uses any ``LLMClient`` to turn a ``TaskInput`` into a ``PlanOutput``.
On any failure (network, auth, invalid JSON, schema mismatch) it falls
back to the deterministic ``PlannerBrain`` so the pipeline never breaks.

The class has no knowledge of which provider is behind the ``LLMClient``
— swap in Anthropic, OpenAI or a local model without changing this file.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.brains.base import Planner
from app.brains.brain1_planner import PlannerBrain
from app.core.logger import get_logger
from app.llm.base import LLMClient, LLMProviderError, LLMResponseError
from app.types import PlanOutput, TaskInput

_log = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are a careful planner. Given a task, produce a structured plan as JSON. "
    "Output ONLY valid JSON — no prose, no markdown fences. The JSON must have these fields: "
    '"task_id" (string), '
    '"objective" (one-sentence string), '
    '"assumptions" (array of strings), '
    '"constraints" (array of strings), '
    '"risks" (array of strings), '
    '"steps" (array of strings, at least three), '
    '"success_criteria" (array of strings), '
    '"planner_notes" (string). '
    "Do not execute the task. Do not critique yourself. Focus only on planning."
)


class LLMPlannerBrain:
    """Planner that delegates to an ``LLMClient`` and validates the JSON reply.

    Args:
        llm: the backend to call.
        fallback: planner used when the LLM fails. Defaults to the
            deterministic ``PlannerBrain``. Pass any object with a
            ``create_plan(task)`` method to override in tests.
    """

    def __init__(self, llm: LLMClient, fallback: Planner | None = None) -> None:
        self.llm = llm
        self.fallback: Planner = fallback or PlannerBrain()

    def create_plan(self, task: TaskInput) -> PlanOutput:
        """Ask the LLM for a plan; return the parsed PlanOutput or a fallback."""
        user_prompt = self._build_user_prompt(task)
        try:
            raw = self.llm.complete(_SYSTEM_PROMPT, user_prompt, json_mode=True)
        except (LLMProviderError, LLMResponseError) as e:
            _log.warning("LLMPlannerBrain: provider failed (%s) - using fallback", e)
            return self.fallback.create_plan(task)

        try:
            plan = PlanOutput.model_validate_json(raw)
        except ValidationError as e:
            _log.warning("LLMPlannerBrain: invalid JSON/schema (%s) - using fallback", e)
            return self.fallback.create_plan(task)

        # Pin the task_id to the caller's value — never trust the model to echo it correctly.
        if plan.task_id != task.id:
            plan = plan.model_copy(update={"task_id": task.id})
        return plan

    @staticmethod
    def _build_user_prompt(task: TaskInput) -> str:
        """Render a TaskInput into the user message sent to the LLM."""
        constraints = ", ".join(task.constraints) if task.constraints else "(none)"
        return (
            f"TASK ID: {task.id}\n"
            f"TASK: {task.prompt}\n"
            f"CONSTRAINTS: {constraints}\n\n"
            "Produce the plan JSON now."
        )
