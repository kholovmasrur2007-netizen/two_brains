"""Combined output of the Planner → Critic pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.types.critique import CritiqueOutput
from app.types.plan import PlanOutput
from app.types.task import TaskInput


class FinalResult(BaseModel):
    """Everything the orchestrator emits after one pass through both brains.

    The model is fully self-contained: given a FinalResult the caller has
    the original task, the plan that was produced, the critique that was
    derived from it, a human-readable recommendation and a single boolean
    that tells execution agents whether they may proceed.
    """

    task_id: str = Field(..., description="Id of the TaskInput.")
    original_task: TaskInput = Field(..., description="The task that was submitted to the pipeline.")
    plan: PlanOutput = Field(..., description="Plan produced by Brain 1.")
    critique: CritiqueOutput = Field(..., description="Critique produced by Brain 2.")
    final_recommendation: str = Field(
        "",
        description="Single-line recommendation: either 'ready to execute' or what to revise.",
    )
    ready_for_execution: bool = Field(
        False,
        description="True only when score is high enough and no blockers exist.",
    )
    # TODO: attach execution artefacts once an execution agent runs the plan.
