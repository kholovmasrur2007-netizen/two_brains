"""Brain 3 — Autonomous Executor.

Runs the *real* agent loop: hands the model a finalised plan + a
sandboxed tool surface, lets it call ``read_file`` / ``write_file`` /
``edit_file`` / ``list_dir`` / ``grep`` until the task is done, then
distils the trace into the same ``ExecutionOutput`` shape the rest of
the pipeline expects.

Safety bars (high-security mode):
    * every file operation goes through ``Sandbox.resolve`` (absolute
      paths, ``..`` segments and drive-letter prefixes are rejected
      before any I/O)
    * no shell, no subprocess, no network tools are exposed
    * ``MAX_ITERATIONS`` caps the number of model→tool round-trips so a
      hallucinating model can't loop forever
    * any provider failure falls back to the deterministic
      ``ExecutorBrain`` so the orchestrator pipeline keeps its "never
      crashes mid-run" contract
"""

from __future__ import annotations

from typing import Any, Callable

from app.agent.client import (
    AgentClient,
    AgentClientError,
    AgentStep,
)
from app.agent.tools_registry import TOOL_DEFS, dispatch_tool
from app.brains.base import Executor
from app.brains.brain3_executor import ExecutorBrain
from app.core.logger import get_logger
from app.sandbox.fs import Sandbox
from app.types import (
    AgentTrace,
    AgentTraceEntry,
    ExecutionOutput,
    PlanOutput,
    StepResult,
    TaskInput,
    ToolCall,
    ToolResult,
)

_log = get_logger(__name__)

# Cap the agent loop. 24 round-trips is enough for non-trivial multi-file
# work (read a few files, write a few, verify) while still being a hard
# wall against runaway loops.
MAX_ITERATIONS: int = 24

# Truncate tool output before showing it back to the model — keeps each
# turn cheap and prevents pathological grep results from blowing context.
_TOOL_OUTPUT_LIMIT: int = 4_000

_SYSTEM_PROMPT = (
    "You are an autonomous engineering agent. You have a finalised plan and a "
    "set of file-operation tools that operate inside a sandboxed workspace. "
    "Walk the plan and produce the artefacts it describes by calling tools.\n\n"
    "Rules:\n"
    "1. Use only the tools provided. Do not pretend you ran shell commands or "
    "performed actions you cannot perform.\n"
    "2. All paths are RELATIVE to the sandbox root. Never use absolute paths or "
    "'..' segments — those will be rejected.\n"
    "3. Prefer write_file for new files and edit_file for tweaks. Verify your "
    "work afterwards with read_file or list_dir when sensible.\n"
    "4. When the plan is complete, return a final assistant message summarising "
    "exactly what changed in the sandbox. Do NOT keep calling tools after that.\n"
    "5. If a step is impossible with these tools (it needs the network, a shell, "
    "or human approval), state so plainly in your final message instead of faking it."
)


class AgentExecutorBrain:
    """Executor that drives a tool-use-capable LLM through the plan steps.

    Args:
        client: an ``AgentClient`` (mock for tests, anthropic for prod).
        sandbox: filesystem root the agent is confined to.
        fallback: executor used when the agent client fails. Defaults to
            the deterministic ``ExecutorBrain`` so the orchestrator
            never sees a crash from this path.
        max_iterations: hard cap on model→tool round-trips per run.
        on_event: optional live callback for the Web UI / CLI to report
            tool calls + results as they happen. Receives dicts shaped
            ``{"type": "tool_call" | "tool_result" | ..., **payload}``.
    """

    def __init__(
        self,
        client: AgentClient,
        sandbox: Sandbox,
        *,
        fallback: Executor | None = None,
        max_iterations: int = MAX_ITERATIONS,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.client = client
        self.sandbox = sandbox
        self.fallback: Executor = fallback or ExecutorBrain()
        self.max_iterations = max_iterations
        self.on_event = on_event

    # ── public API ───────────────────────────────────────────────────

    def execute_plan(self, task: TaskInput, plan: PlanOutput) -> ExecutionOutput:
        """Drive the agent loop until the model finishes or we hit the cap."""
        try:
            trace = self._run_loop(task, plan)
        except AgentClientError as e:
            _log.warning(
                "AgentExecutorBrain: provider failed (%s) - using deterministic fallback",
                e,
            )
            # Surface the fallback so the UI can show a clear notice instead of
            # silently looking like the agent did the work.
            self._emit("agent_fallback", reason=str(e))
            result = self.fallback.execute_plan(task, plan)
            # Annotate the executor_notes so static renders (history, /api/tasks)
            # also reflect that the agent didn't actually run.
            return result.model_copy(update={
                "executor_notes": (
                    f"Agent client failed ({e}); "
                    "fell back to deterministic dry-run. "
                    + result.executor_notes
                )
            })

        return self._summarise(task, plan, trace)

    # ── agent loop ───────────────────────────────────────────────────

    def _run_loop(self, task: TaskInput, plan: PlanOutput) -> AgentTrace:
        """Run the model↔tool loop, recording every round-trip."""
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [{"type": "text", "text": self._initial_prompt(task, plan)}],
            }
        ]
        trace = AgentTrace()

        for iteration in range(1, self.max_iterations + 1):
            step = self.client.step(
                system=_SYSTEM_PROMPT,
                messages=messages,
                tools=TOOL_DEFS,
                max_tokens=2048,
            )

            # Always echo the assistant turn back into the conversation so the
            # next call has the model's prior tool_use blocks attached.
            assistant_content = step.raw.get("assistant_content")
            if assistant_content:
                messages.append({"role": "assistant", "content": assistant_content})
            elif step.kind == "final" and step.text:
                # MockAgentClient and similar plain-text providers won't have
                # filled in raw.assistant_content — synthesise it.
                messages.append({"role": "assistant", "content": [{"type": "text", "text": step.text}]})
            elif step.kind == "tool_use":
                # Mock or partial provider returned tool_use without raw blocks
                # — synthesise so subsequent tool_result blocks have something to
                # reference. Real Anthropic clients always populate raw.
                synth = self._synthesise_assistant_blocks(step)
                messages.append({"role": "assistant", "content": synth})

            if step.kind == "final":
                trace.final_text = step.text
                trace.iterations = iteration - 1  # final message is not a round-trip
                return trace

            # tool_use — run every tool the model asked for, append the
            # results in a single user message (Anthropic spec).
            tool_results: list[dict[str, Any]] = []
            for tc, raw_block in self._zip_tool_calls(step):
                self._emit("tool_call", iteration=iteration,
                           tool=tc.name, arguments=tc.arguments)
                result = dispatch_tool(tc, self.sandbox)
                self._emit("tool_result", iteration=iteration,
                           tool=tc.name, status=result.status,
                           output=_truncate(result.output, 200),
                           error=result.error)
                trace.entries.append(AgentTraceEntry(
                    iteration=iteration, tool_call=tc, tool_result=result,
                ))
                tool_results.append(self._tool_result_block(raw_block, result))

            messages.append({"role": "user", "content": tool_results})

        # Hard cap reached — model never said it was done.
        trace.iterations = self.max_iterations
        trace.halted_reason = (
            f"max_iterations ({self.max_iterations}) reached without a final answer"
        )
        return trace

    # ── prompt + summary ─────────────────────────────────────────────

    @staticmethod
    def _initial_prompt(task: TaskInput, plan: PlanOutput) -> str:
        """Render the first user turn — the task plus the plan to execute."""
        constraints = ", ".join(task.constraints) if task.constraints else "(none)"
        return (
            f"TASK: {task.prompt}\n"
            f"CONSTRAINTS: {constraints}\n\n"
            f"FINALISED PLAN:\n{plan.model_dump_json(indent=2)}\n\n"
            "Walk the plan and produce the artefacts it describes by calling tools. "
            "When you're done, return a final message summarising what changed."
        )

    def _summarise(
        self,
        task: TaskInput,
        plan: PlanOutput,
        trace: AgentTrace,
    ) -> ExecutionOutput:
        """Translate an agent trace into the pipeline-wide ExecutionOutput."""
        step_results: list[StepResult] = []
        for index, step_text in enumerate(plan.steps, start=1):
            # Per-step status is heuristic: every plan step is "succeeded" once
            # the agent reaches its final message. If the loop halted on the
            # iteration cap, mark everything past that as skipped.
            if trace.halted_reason:
                step_results.append(StepResult(
                    index=index, step=step_text, status="skipped",
                    output="agent halted before this step",
                    error=trace.halted_reason if index == 1 else "",
                ))
            else:
                step_results.append(StepResult(
                    index=index, step=step_text, status="succeeded",
                    output="executed by autonomous agent",
                    error="",
                ))

        overall = "failed" if trace.halted_reason else "completed"
        ok_calls = sum(1 for e in trace.entries if e.tool_result.status == "ok")
        bad_calls = sum(1 for e in trace.entries if e.tool_result.status == "error")
        summary = (
            f"agent ran {trace.iterations} iteration(s), "
            f"{ok_calls} successful tool call(s), {bad_calls} failed."
        )
        if trace.halted_reason:
            summary += f" halted: {trace.halted_reason}."

        notes = trace.final_text or trace.halted_reason or "agent finished without a final message"

        return ExecutionOutput(
            task_id=task.id,
            overall_status=overall,
            step_results=step_results,
            summary=summary,
            executor_notes=notes,
        )

    # ── helpers ──────────────────────────────────────────────────────

    def _emit(self, event_type: str, **payload: Any) -> None:
        """Forward a live event to the on_event listener if one is wired."""
        if self.on_event is None:
            return
        try:
            self.on_event({"type": event_type, **payload})
        except Exception as e:  # noqa: BLE001 - listener bugs must not crash the agent
            _log.warning("agent on_event raised %s: %s", e.__class__.__name__, e)

    @staticmethod
    def _zip_tool_calls(step: AgentStep) -> list[tuple[ToolCall, dict[str, Any]]]:
        """Pair each ToolCall with its raw provider block (for tool_result wiring)."""
        raw_blocks: list[dict[str, Any]] = [
            b for b in step.raw.get("assistant_content", [])
            if b.get("type") == "tool_use"
        ]
        if len(raw_blocks) == len(step.tool_calls):
            return list(zip(step.tool_calls, raw_blocks))
        # Mock client path: synthesise minimal blocks so ids line up.
        return [(tc, {"id": f"mock-tool-{i}", "name": tc.name, "input": tc.arguments})
                for i, tc in enumerate(step.tool_calls)]

    @staticmethod
    def _synthesise_assistant_blocks(step: AgentStep) -> list[dict[str, Any]]:
        """Build an assistant content list from a step that lacks one."""
        return [
            {"type": "tool_use", "id": f"mock-tool-{i}", "name": tc.name, "input": tc.arguments}
            for i, tc in enumerate(step.tool_calls)
        ]

    @staticmethod
    def _tool_result_block(raw_block: dict[str, Any], result: ToolResult) -> dict[str, Any]:
        """Render a ToolResult as the user-side tool_result block Anthropic expects."""
        body = result.output if result.status == "ok" else f"error: {result.error}"
        return {
            "type": "tool_result",
            "tool_use_id": raw_block.get("id", "missing-id"),
            "is_error": result.status == "error",
            "content": _truncate(body, _TOOL_OUTPUT_LIMIT),
        }


def _truncate(text: str, limit: int) -> str:
    """Cut ``text`` to ``limit`` chars with a clear suffix when truncated."""
    if len(text) <= limit:
        return text
    return text[: limit - 32] + f"\n... (truncated, {len(text)} chars total)"
