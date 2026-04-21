"""Task input passed to the planner."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TaskInput(BaseModel):
    """A single unit of work the system is asked to plan for.

    The planner reads this and produces a PlanOutput; the task is never
    mutated downstream, so treat fields as read-only once constructed.
    """

    id: str = Field(..., description="Stable task identifier.")
    prompt: str = Field(..., description="What the user wants done, in free-form text.")
    constraints: list[str] = Field(
        default_factory=list,
        description="Explicit constraints supplied by the caller (e.g. 'no backend').",
    )
    # TODO: add priority, deadline, source metadata once callers need them.
