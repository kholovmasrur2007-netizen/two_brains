"""Brain 2 — LLM-backed Critic.

Uses any ``LLMClient`` to turn a ``PlanOutput`` into a ``CritiqueOutput``.
On any failure (network, auth, invalid JSON, schema mismatch) it falls
back to the deterministic ``CriticBrain`` so the pipeline never breaks.

Mirrors the design of ``LLMPlannerBrain`` in the sibling file.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.brains.base import Critic
from app.brains.brain2_critic import CriticBrain
from app.core.logger import get_logger
from app.llm.base import LLMClient, LLMProviderError, LLMResponseError
from app.types import CritiqueOutput, PlanOutput

_log = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are a strict plan critic. Given a plan in JSON, output a critique as JSON. "
    "Output ONLY valid JSON - no prose, no markdown fences. The critique JSON must have: "
    '"task_id" (string, copy from the plan), '
    '"overall_score" (integer 0-100), '
    '"strengths" (array of strings), '
    '"weaknesses" (array of strings), '
    '"missing_elements" (array of strings - hard gaps that must be filled), '
    '"contradictions" (array of strings - steps that violate the plans constraints), '
    '"risk_flags" (array of strings - risks without mitigation), '
    '"improvement_suggestions" (array of strings), '
    '"revised_step_notes" (array of strings - per-step feedback like "Step 3: ..."), '
    '"final_judgement" (one of: "accepted", "needs_minor_revision", '
    '"needs_major_revision", "rejected"). '
    "Do not rewrite the plan. Do not execute anything. Focus only on judging."
)


class LLMCriticBrain:
    """Critic that delegates to an ``LLMClient`` and validates the JSON reply.

    Args:
        llm: the backend to call.
        fallback: critic used when the LLM fails. Defaults to the
            deterministic ``CriticBrain``. Pass any object with a
            ``review_plan(plan)`` method to override in tests.
    """

    def __init__(self, llm: LLMClient, fallback: Critic | None = None) -> None:
        self.llm = llm
        self.fallback: Critic = fallback or CriticBrain()

    def review_plan(self, plan: PlanOutput) -> CritiqueOutput:
        """Ask the LLM for a critique; return a parsed CritiqueOutput or a fallback."""
        user_prompt = self._build_user_prompt(plan)
        try:
            raw = self.llm.complete(_SYSTEM_PROMPT, user_prompt, json_mode=True)
        except (LLMProviderError, LLMResponseError) as e:
            _log.warning("LLMCriticBrain: provider failed (%s) - using fallback", e)
            return self.fallback.review_plan(plan)

        try:
            critique = CritiqueOutput.model_validate_json(raw)
        except ValidationError as e:
            _log.warning("LLMCriticBrain: invalid JSON/schema (%s) - using fallback", e)
            return self.fallback.review_plan(plan)

        # Pin the task_id to the plan's value — never trust the model to echo it correctly.
        if critique.task_id != plan.task_id:
            critique = critique.model_copy(update={"task_id": plan.task_id})
        return critique

    @staticmethod
    def _build_user_prompt(plan: PlanOutput) -> str:
        """Serialise the plan into a user message the LLM can judge."""
        return (
            "Review the following plan and return the critique JSON.\n\n"
            "PLAN:\n"
            f"{plan.model_dump_json(indent=2)}\n\n"
            "Produce the critique JSON now."
        )
