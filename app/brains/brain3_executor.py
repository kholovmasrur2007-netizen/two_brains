"""Brain 3 - Executor (deterministic).

Walks every step of a plan and produces a structured ExecutionOutput.
The deterministic backend does not perform real side effects — it
classifies each step against a small set of heuristics and emits a
templated "would do X, expect Y" report. That is enough for:

    * end-to-end pipeline tests with no network
    * a CLI demo that returns instantly
    * a baseline executor a future LLM/sandbox backend can be compared against

Non-responsibilities:
    * running shell commands
    * editing files
    * calling external APIs

A future ``SandboxedExecutorBrain`` can plug in behind the same
``Executor`` Protocol without changing callers.
"""

from __future__ import annotations

from app.types import (
    ExecutionOutput,
    OverallStatus,
    PlanOutput,
    StepResult,
    TaskInput,
)

# Keywords that flag a step as a "delegated" / human-only action. The
# deterministic executor refuses to claim it executed any of these — they
# are reported as ``skipped`` so a downstream caller can pick them up.
_DELEGATED_KEYWORDS: frozenset[str] = frozenset({
    "confirm with the requester",
    "ask the requester",
    "consult",
    "stakeholder",
    "manually",
    "human review",
    "approval",
    "deploy to production",
})

# Keywords that flag a step as inherently risky in a deterministic
# simulation: we still report ``succeeded`` but emit a caveat in output.
_RISKY_KEYWORDS: frozenset[str] = frozenset({
    "production",
    "delete",
    "drop ",
    "destructive",
    "migrate",
    "payment",
})


class ExecutorBrain:
    """Deterministic Executor — simulates a run, never touches the system."""

    def execute_plan(self, task: TaskInput, plan: PlanOutput) -> ExecutionOutput:
        """Walk the plan and produce a templated execution report."""
        if not plan.steps:
            return ExecutionOutput(
                task_id=task.id,
                overall_status="not_run",
                step_results=[],
                summary="No steps to execute.",
                executor_notes="Plan contained zero steps; nothing to simulate.",
            )

        results: list[StepResult] = []
        for index, step in enumerate(plan.steps, start=1):
            results.append(self._simulate_step(index, step))

        overall = self._derive_overall_status(results)
        return ExecutionOutput(
            task_id=task.id,
            overall_status=overall,
            step_results=results,
            summary=self._compose_summary(results, overall),
            executor_notes=(
                "Deterministic executor: outputs are templated, no side effects "
                "were performed. Wire an LLM or sandbox backend for real work."
            ),
        )

    # ── per-step simulation ────────────────────────────────────────────

    @staticmethod
    def _simulate_step(index: int, step: str) -> StepResult:
        low = step.lower()
        if any(kw in low for kw in _DELEGATED_KEYWORDS):
            return StepResult(
                index=index,
                step=step,
                status="skipped",
                output="Skipped — step requires human action or external approval.",
                error="",
            )
        risky = any(kw in low for kw in _RISKY_KEYWORDS)
        output = (
            "Simulated successfully (caveat: high-risk action — verify before real run)."
            if risky
            else "Simulated successfully — would produce the expected artefact."
        )
        return StepResult(
            index=index,
            step=step,
            status="succeeded",
            output=output,
            error="",
        )

    # ── overall status / summary ───────────────────────────────────────

    @staticmethod
    def _derive_overall_status(results: list[StepResult]) -> OverallStatus:
        statuses = {r.status for r in results}
        if "failed" in statuses:
            # Any failure with at least one success is partial; otherwise full failure.
            return "partial" if "succeeded" in statuses else "failed"
        # No failures: fully completed even if some steps were skipped.
        return "completed"

    @staticmethod
    def _compose_summary(results: list[StepResult], overall: OverallStatus) -> str:
        ok = sum(1 for r in results if r.status == "succeeded")
        skipped = sum(1 for r in results if r.status == "skipped")
        failed = sum(1 for r in results if r.status == "failed")
        return (
            f"{overall}: {ok} succeeded, {skipped} skipped, {failed} failed "
            f"out of {len(results)} step(s)."
        )
