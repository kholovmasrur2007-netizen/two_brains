"""Plan produced by Brain 1 (Planner)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PlanOutput(BaseModel):
    """A structured plan for solving a TaskInput.

    Produced by the Planner; consumed by the Critic and the Orchestrator.
    Every list-shaped field defaults to an empty list so callers can safely
    iterate without None-checks.
    """

    task_id: str = Field(..., description="Id of the TaskInput this plan belongs to.")
    objective: str = Field("", description="Single-sentence statement of what must be achieved.")
    assumptions: list[str] = Field(default_factory=list, description="Assumptions the plan relies on.")
    constraints: list[str] = Field(default_factory=list, description="Hard constraints the plan must respect.")
    risks: list[str] = Field(default_factory=list, description="Things that can go wrong and must be watched.")
    steps: list[str] = Field(default_factory=list, description="Ordered list of actionable steps.")
    success_criteria: list[str] = Field(default_factory=list, description="How we know the plan succeeded.")
    planner_notes: str = Field("", description="Free-form notes from the planner (summary, context).")
    # TODO: add inter-step dependencies, estimated cost and a numeric confidence score.
