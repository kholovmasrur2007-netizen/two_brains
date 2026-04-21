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
from app.types import CritiqueOutput, PlanOutput, TaskInput

_log = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are a careful planner. Given a task, produce a structured plan as JSON. "
    "Output ONLY valid JSON - no prose, no markdown fences. The JSON must have these fields: "
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

_REVISION_SYSTEM_PROMPT = (
    "You are a planner revising an earlier plan after a critic reviewed it. "
    "Given the task, your prior plan, and the critique, produce an improved plan "
    "as JSON with the same schema as before. Address every missing element, "
    "resolve every contradiction and add mitigation steps for any flagged risk. "
    "Output ONLY valid JSON."
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

    def revise_plan(
        self,
        task: TaskInput,
        prior_plan: PlanOutput,
        critique: CritiqueOutput,
    ) -> PlanOutput:
        """Ask the LLM for an improved plan that addresses the critique.

        On any failure the *prior* plan is returned unchanged — the
        orchestrator treats that as "no improvement" and will stop iterating.
        """
        user_prompt = self._build_revision_prompt(task, prior_plan, critique)
        try:
            raw = self.llm.complete(_REVISION_SYSTEM_PROMPT, user_prompt, json_mode=True)
        except (LLMProviderError, LLMResponseError) as e:
            _log.warning("LLMPlannerBrain.revise: provider failed (%s) - keeping prior plan", e)
            return prior_plan

        try:
            plan = PlanOutput.model_validate_json(raw)
        except ValidationError as e:
            _log.warning("LLMPlannerBrain.revise: invalid JSON/schema (%s) - keeping prior plan", e)
            return prior_plan

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

    @staticmethod
    def _build_revision_prompt(
        task: TaskInput,
        prior_plan: PlanOutput,
        critique: CritiqueOutput,
    ) -> str:
        """Render task + prior plan + critique into a revision user message."""
        return (
            f"TASK: {task.prompt}\n\n"
            f"PRIOR PLAN:\n{prior_plan.model_dump_json(indent=2)}\n\n"
            f"CRITIQUE:\n{critique.model_dump_json(indent=2)}\n\n"
            "Produce the revised plan JSON now."
        )
