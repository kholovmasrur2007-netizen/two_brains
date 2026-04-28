"""Brain 3 — LLM-backed Executor.

Uses any ``LLMClient`` to ask the model to walk the plan step-by-step
and report what *would* happen if each step were performed. The model
is instructed not to invent side effects on the user's machine — its
job is to reason about expected outputs, surface failures it can
predict, and flag steps that need human action.

On any failure (network, auth, invalid JSON, schema mismatch) it falls
back to the deterministic ``ExecutorBrain`` so the pipeline never breaks.
"""

from __future__ import annotations

from pydantic import ValidationError

from app.brains.base import Executor
from app.brains.brain3_executor import ExecutorBrain
from app.core.logger import get_logger
from app.llm.base import LLMClient, LLMProviderError, LLMResponseError
from app.types import ExecutionOutput, PlanOutput, TaskInput

_log = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are an execution agent. Given a task and a finalised plan, walk every "
    "step in order and report what would happen if the step were performed. "
    "You are NOT permitted to invent side effects on the user's environment — "
    "treat this as a careful dry-run. For each step decide a status: "
    '"succeeded" (the step would clearly produce its intended output), '
    '"failed" (a predictable problem prevents the step from working), or '
    '"skipped" (the step requires a human, an external approval, or '
    "information you do not have). "
    "Output ONLY valid JSON — no prose, no markdown fences. The JSON shape: "
    '{"task_id": string, '
    '"overall_status": one of "completed" | "partial" | "failed" | "not_run", '
    '"step_results": ['
    '  {"index": int starting at 1, '
    '   "step": original step text, '
    '   "status": "succeeded" | "failed" | "skipped", '
    '   "output": short description of what was produced or simulated, '
    '   "error": error message when status == failed else empty string}'
    "], "
    '"summary": one-line summary of the run, '
    '"executor_notes": short rationale, caveats, anything the user should know}.'
)


class LLMExecutorBrain:
    """Executor that delegates to an ``LLMClient`` and validates the JSON reply.

    Args:
        llm: the backend to call.
        fallback: executor used when the LLM fails. Defaults to the
            deterministic ``ExecutorBrain``. Pass any object with an
            ``execute_plan(task, plan)`` method to override in tests.
    """

    def __init__(self, llm: LLMClient, fallback: Executor | None = None) -> None:
        self.llm = llm
        self.fallback: Executor = fallback or ExecutorBrain()

    def execute_plan(self, task: TaskInput, plan: PlanOutput) -> ExecutionOutput:
        """Ask the LLM for an execution report; fall back on any failure."""
        user_prompt = self._build_user_prompt(task, plan)
        try:
            raw = self.llm.complete(_SYSTEM_PROMPT, user_prompt, json_mode=True)
        except (LLMProviderError, LLMResponseError) as e:
            _log.warning("LLMExecutorBrain: provider failed (%s) - using fallback", e)
            return self.fallback.execute_plan(task, plan)

        try:
            execution = ExecutionOutput.model_validate_json(raw)
        except ValidationError as e:
            _log.warning("LLMExecutorBrain: invalid JSON/schema (%s) - using fallback", e)
            return self.fallback.execute_plan(task, plan)

        # Pin the task_id to the caller's value — never trust the model to echo it correctly.
        if execution.task_id != task.id:
            execution = execution.model_copy(update={"task_id": task.id})
        return execution

    @staticmethod
    def _build_user_prompt(task: TaskInput, plan: PlanOutput) -> str:
        """Render task + finalised plan into the user message sent to the LLM."""
        return (
            f"TASK ID: {task.id}\n"
            f"TASK: {task.prompt}\n\n"
            f"FINALISED PLAN:\n{plan.model_dump_json(indent=2)}\n\n"
            "Walk every step and produce the execution-report JSON now."
        )
