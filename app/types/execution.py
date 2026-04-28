"""Execution artefacts produced by Brain 3 (Executor).

The executor walks the steps of a finalised plan and reports, per step,
whether the step succeeded, what the produced output looked like, and
any error it ran into. The pipeline never runs arbitrary shell commands
on the user's machine — execution is *simulated* in the sense that the
deterministic backend produces a templated report and the LLM backend
asks the model to reason about each step's outcome. A future, sandboxed
backend could perform real tool calls behind the same contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

StepStatus = Literal["succeeded", "failed", "skipped"]
"""Per-step outcome — kept tight on purpose so renderers can colour-map it."""

OverallStatus = Literal["completed", "partial", "failed", "not_run"]
"""Overall execution outcome derived from individual step statuses."""


class StepResult(BaseModel):
    """Outcome of executing a single step from the plan."""

    index: int = Field(..., ge=1, description="1-based position of the step inside the plan.")
    step: str = Field(..., description="The original step text from PlanOutput.steps.")
    status: StepStatus = Field(..., description="Whether the step succeeded, failed or was skipped.")
    output: str = Field("", description="What the step produced — short human-readable summary.")
    error: str = Field("", description="Error message if status == 'failed', empty otherwise.")


class ExecutionOutput(BaseModel):
    """Result of running every step of a plan through the executor."""

    task_id: str = Field(..., description="Id of the TaskInput the plan belongs to.")
    overall_status: OverallStatus = Field(
        "not_run",
        description="completed = all steps succeeded; partial = some failed; "
                    "failed = all/blocking failure; not_run = executor was skipped.",
    )
    step_results: list[StepResult] = Field(
        default_factory=list,
        description="One StepResult per plan step, in plan order.",
    )
    summary: str = Field("", description="One-line human-readable summary of the run.")
    executor_notes: str = Field("", description="Free-form notes from the executor (rationale, caveats).")