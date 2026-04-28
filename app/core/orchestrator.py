"""Orchestrator — pipelines Brain 1 (Planner), Brain 2 (Critic) and
optionally Brain 3 (Executor).

Flow:

    TaskInput ──▶ PlannerBrain.create_plan ──▶ PlanOutput
              │
              └──▶ CriticBrain.review_plan ──▶ CritiqueOutput
                                                   │
                               ┌───────────────────┘
                               ▼
                          FinalResult ──▶ (if ready_for_execution
                                           and execute=True)
                                          ExecutorBrain.execute_plan
                                                   │
                                                   ▼
                                          ExecutionOutput
                                          attached to FinalResult

The executor only runs when:
    1. ``execute=True`` was passed to ``run()`` (default: False)
    2. AND the orchestrator already flagged the plan ready_for_execution

Refusing to execute an unready plan is a deliberate safety bar.
"""

from __future__ import annotations

from typing import Any, Callable

from app import config
from app.brains import (
    Critic,
    Executor,
    Planner,
    build_critic,
    build_executor,
    build_planner,
)
from app.brains.base import RevisingPlanner
from app.core.logger import get_logger
from app.memory.store import MemoryStore
from app.types import CritiqueOutput, ExecutionOutput, FinalResult, TaskInput

EventCallback = Callable[[dict[str, Any]], None]
"""Optional callback invoked at every pipeline phase.

The Web UI uses this to stream live updates over a WebSocket. Tests use
it to assert which phases ran. The callback receives a dict with at
least a ``"type"`` key — payload shape per event is documented inline
where it is emitted.
"""


class TwoBrainOrchestrator:
    """Wire Brain 1, Brain 2 and (optionally) Brain 3 into a single call.

    Collaborators are accepted via Protocols (``Planner`` / ``Critic`` /
    ``Executor``) so any implementation — deterministic today, LLM-backed
    or sandboxed tomorrow — plugs in without changing this class. If an
    instance is not supplied, the orchestrator asks the brain factories
    for the providers configured in ``app.config.settings``. Memory
    defaults to a fresh in-process store.
    """

    # A plan is only flagged ready_for_execution when the score passes
    # this bar *and* no blocking issue (missing element or contradiction)
    # has been reported by the critic.
    MIN_READY_SCORE: int = 85

    def __init__(
        self,
        planner: Planner | None = None,
        critic: Critic | None = None,
        executor: Executor | None = None,
        memory: MemoryStore | None = None,
    ) -> None:
        self.planner: Planner = planner or build_planner(config.settings.planner_provider)
        self.critic:  Critic  = critic  or build_critic(config.settings.critic_provider)
        # The executor is built lazily — most callers (CLI without --execute,
        # tests, the show/history commands) never need one, so we avoid
        # importing the LLM SDK on construction.
        self._executor_override: Executor | None = executor
        self.memory = memory or MemoryStore()
        self._log = get_logger(__name__)

    # ── public entry points ───────────────────────────────────────────

    def run(
        self,
        task: TaskInput,
        *,
        execute: bool = False,
        on_event: EventCallback | None = None,
    ) -> FinalResult:
        """Run the pipeline end-to-end for one task.

        Args:
            task: the task to plan + critique.
            execute: when True and the plan is ready, also run the
                executor and attach its report to the FinalResult.
                Default False — the orchestrator stops after the critic.
            on_event: optional callback invoked at every phase. Used by
                the Web UI to stream live progress. Exceptions raised
                inside the callback are swallowed and logged so a buggy
                listener can never crash the pipeline.

        Flow:
            1. Planner.create_plan -> Critic.review_plan.
            2. If the planner also implements ``RevisingPlanner`` and the
               critique is not already "accepted", loop through
               ``revise_plan -> review_plan`` up to ``max_iterations`` times
               or until the critique accepts the plan, whichever comes first.
            3. Wrap the final plan + critique in a FinalResult.
            4. If ``execute`` and the result is ready, run the executor
               and attach the ExecutionOutput.
        """
        emit = self._make_emitter(on_event)

        self._log.info("task received id=%s prompt=%r", task.id, task.prompt)
        self.memory.save_task(task)
        emit("task_received", task=task.model_dump())

        # ── Iteration 1: initial plan + critique ─────────────────────
        emit("planner_started", iteration=1)
        self._log.info("brain1: planning...")
        plan = self.planner.create_plan(task)
        self.memory.save_plan(plan)
        self._log.info(
            "brain1: done steps=%d risks=%d assumptions=%d",
            len(plan.steps), len(plan.risks), len(plan.assumptions),
        )
        emit("plan_ready", iteration=1, plan=plan.model_dump())

        emit("critic_started", iteration=1)
        self._log.info("brain2: critiquing...")
        critique = self.critic.review_plan(plan)
        self.memory.save_critique(critique)
        self._log.info(
            "brain2: done score=%d judgement=%s",
            critique.overall_score, critique.final_judgement,
        )
        emit("critique_ready", iteration=1, critique=critique.model_dump())

        iterations = 1

        # ── Iterations 2..N: revise while the planner supports it ───
        can_revise = isinstance(self.planner, RevisingPlanner)
        max_iter = max(1, config.settings.max_iterations)

        while (
            can_revise
            and critique.final_judgement != "accepted"
            and iterations < max_iter
        ):
            next_iter = iterations + 1
            emit("planner_started", iteration=next_iter, revising=True)
            self._log.info("iteration %d/%d: revising plan...", next_iter, max_iter)
            plan = self.planner.revise_plan(task, plan, critique)
            self.memory.save_plan(plan)
            emit("plan_ready", iteration=next_iter, plan=plan.model_dump())

            emit("critic_started", iteration=next_iter)
            critique = self.critic.review_plan(plan)
            self.memory.save_critique(critique)
            iterations = next_iter
            self._log.info(
                "iteration %d: score=%d judgement=%s",
                iterations, critique.overall_score, critique.final_judgement,
            )
            emit("critique_ready", iteration=iterations, critique=critique.model_dump())

        # ── Assemble FinalResult ─────────────────────────────────────
        ready = self._is_ready(critique)
        recommendation = self._compose_recommendation(critique, ready)

        execution: ExecutionOutput | None = None
        if execute and ready:
            emit("executor_started")
            self._log.info("brain3: executing plan...")
            executor = self._get_executor()
            # If the executor exposes an ``on_event`` slot (the autonomous
            # agent does), wire it to the orchestrator's emitter so live
            # tool_call / tool_result events bubble up to the WebSocket.
            previous_listener = getattr(executor, "on_event", None)
            if hasattr(executor, "on_event") and on_event is not None:
                executor.on_event = lambda ev: emit(ev["type"], **{k: v for k, v in ev.items() if k != "type"})
            try:
                execution = executor.execute_plan(task, plan)
            finally:
                if hasattr(executor, "on_event"):
                    executor.on_event = previous_listener
            self._log.info(
                "brain3: done overall=%s steps=%d",
                execution.overall_status, len(execution.step_results),
            )
            emit("execution_ready", execution=execution.model_dump())
        elif execute and not ready:
            self._log.info("brain3: skipped — plan is not ready_for_execution")
            emit("executor_skipped", reason="plan_not_ready")

        result = FinalResult(
            task_id=task.id,
            original_task=task,
            plan=plan,
            critique=critique,
            execution=execution,
            final_recommendation=recommendation,
            ready_for_execution=ready,
            iterations=iterations,
        )
        self.memory.save_result(result)

        self._log.info(
            "pipeline done iterations=%d ready_for_execution=%s executed=%s recommendation=%r",
            iterations, ready, execution is not None, recommendation,
        )
        emit("done", result=result.model_dump())
        return result

    # ── event emission helper ─────────────────────────────────────────

    def _make_emitter(self, on_event: EventCallback | None) -> Callable[..., None]:
        """Wrap an optional callback so calls are safe even when it raises."""
        if on_event is None:
            def _noop(_type: str, **_payload: Any) -> None:
                return
            return _noop

        def _emit(event_type: str, **payload: Any) -> None:
            try:
                on_event({"type": event_type, **payload})
            except Exception as e:  # noqa: BLE001 - listener must not crash the pipeline
                self._log.warning("on_event listener raised %s: %s", e.__class__.__name__, e)
        return _emit

    # ── lazy executor accessor ────────────────────────────────────────

    def _get_executor(self) -> Executor:
        """Return the executor, building one from config on first use."""
        if self._executor_override is not None:
            return self._executor_override
        self._executor_override = build_executor(config.settings.executor_provider)
        return self._executor_override

    # ── derivation of the two summary fields ──────────────────────────

    def _is_ready(self, critique: CritiqueOutput) -> bool:
        """A plan is ready only when nothing blocks execution.

        Explicit rule (kept independent of the critic's own thresholds so
        the orchestrator has its own bar):

        * score must be >= MIN_READY_SCORE
        * no missing_elements
        * no contradictions
        """
        if critique.overall_score < self.MIN_READY_SCORE:
            return False
        if critique.missing_elements:
            return False
        if critique.contradictions:
            return False
        return True

    def _compose_recommendation(self, critique: CritiqueOutput, ready: bool) -> str:
        """Return a short human-readable recommendation string."""
        if ready:
            return "Plan is ready to execute."
        parts: list[str] = []
        if critique.missing_elements:
            parts.append(f"fill {len(critique.missing_elements)} missing element(s)")
        if critique.contradictions:
            parts.append(f"resolve {len(critique.contradictions)} contradiction(s)")
        if critique.overall_score < self.MIN_READY_SCORE:
            parts.append(
                f"raise score from {critique.overall_score} to at least {self.MIN_READY_SCORE}"
            )
        if not parts:
            parts.append("address the weaknesses reported above")
        return "Revise plan: " + "; ".join(parts) + "."
