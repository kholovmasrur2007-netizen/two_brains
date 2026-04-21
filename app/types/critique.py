"""Critique produced by Brain 2 (Critic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Judgement = Literal[
    "accepted",
    "needs_minor_revision",
    "needs_major_revision",
    "rejected",
    "pending",
]


class CritiqueOutput(BaseModel):
    """Structured feedback on a PlanOutput.

    The critic does not modify the plan; it only describes what is strong,
    what is weak and what must be revised before the plan is safe to execute.
    """

    task_id: str = Field(..., description="Id of the TaskInput this critique belongs to.")
    overall_score: int = Field(
        0, ge=0, le=100,
        description="Aggregate score from 0 (unusable) to 100 (excellent).",
    )
    strengths: list[str] = Field(default_factory=list, description="Aspects of the plan that are already good.")
    weaknesses: list[str] = Field(default_factory=list, description="Soft problems to improve.")
    missing_elements: list[str] = Field(default_factory=list, description="Hard gaps that must be filled.")
    contradictions: list[str] = Field(default_factory=list, description="Steps that violate the plan's own constraints.")
    risk_flags: list[str] = Field(default_factory=list, description="Declared risks without a matching mitigation step.")
    improvement_suggestions: list[str] = Field(default_factory=list, description="Actionable recommendations to lift the score.")
    revised_step_notes: list[str] = Field(default_factory=list, description="Per-step feedback: 'Step N: <issue>'.")
    final_judgement: Judgement = Field("pending", description="Single verdict used by the orchestrator to route the plan.")
    # TODO: attach a numeric confidence score and per-dimension sub-scores
    #       (clarity / completeness / feasibility / risk) once they are used downstream.
