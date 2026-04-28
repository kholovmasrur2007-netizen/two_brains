"""Combined output of the Planner → Critic → (optional) Executor pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.types.critique import CritiqueOutput
from app.types.execution import ExecutionOutput
from app.types.plan import PlanOutput
from app.types.task import TaskInput


class FinalResult(BaseModel):
    """Everything the orchestrator emits after one pass through the brains.

    Self-contained: given a FinalResult the caller has the original task,
    the plan that was produced, the critique that was derived from it, a
    human-readable recommendation, the ready/not-ready verdict, and — if
    the executor ran — the per-step execution report.
    """

    task_id: str = Field(..., description="Id of the TaskInput.")
    original_task: TaskInput = Field(..., description="The task that was submitted to the pipeline.")
    plan: PlanOutput = Field(..., description="Plan produced by Brain 1.")
    critique: CritiqueOutput = Field(..., description="Critique produced by Brain 2.")
    execution: ExecutionOutput | None = Field(
        None,
        description="Execution report from Brain 3. None if the executor was not invoked.",
    )
    final_recommendation: str = Field(
        "",
        description="Single-line recommendation: either 'ready to execute' or what to revise.",
    )
    ready_for_execution: bool = Field(
        False,
        description="True only when score is high enough and no blockers exist.",
    )
    iterations: int = Field(
        1,
        ge=1,
        description="Number of plan/critique cycles executed (1 = no revision happened).",
    )
