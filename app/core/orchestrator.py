"""Orchestrator — pipelines Brain 1 (Planner) and Brain 2 (Critic).

Flow:

    TaskInput ──▶ PlannerBrain.create_plan ──▶ PlanOutput
              │
              └──▶ CriticBrain.review_plan ──▶ CritiqueOutput
                                                   │
                               ┌───────────────────┘
                               ▼
                          FinalResult

There is no execution agent here — the orchestrator just wires the two
brains together, derives a single recommendation and returns the
structured result. Execution is a future concern.
"""

from __future__ import annotations

from app import config
from app.brains import Critic, Planner, build_critic, build_planner
from app.core.logger import get_logger
from app.memory.store import MemoryStore
from app.types import CritiqueOutput, FinalResult, TaskInput


class TwoBrainOrchestrator:
    """Wire Brain 1 and Brain 2 into a single call.

    Collaborators are accepted via Protocols (``Planner`` / ``Critic``) so
    any implementation — deterministic today, LLM-backed tomorrow — plugs
    in without changing this class. If an instance is not supplied, the
    orchestrator asks the brain factories for the providers configured in
    ``app.config.settings``. Memory defaults to a fresh in-process store.
    """

    # A plan is only flagged ready_for_execution when the score passes
    # this bar *and* no blocking issue (missing element or contradiction)
    # has been reported by the critic.
    MIN_READY_SCORE: int = 85

    def __init__(
        self,
        planner: Planner | None = None,
        critic: Critic | None = None,
        memory: MemoryStore | None = None,
    ) -> None:
        self.planner: Planner = planner or build_planner(config.settings.planner_provider)
        self.critic:  Critic  = critic  or build_critic(config.settings.critic_provider)
        self.memory = memory or MemoryStore()
        self._log = get_logger(__name__)

    def run(self, task: TaskInput) -> FinalResult:
        """Run the pipeline end-to-end for one task."""
        self._log.info("task received id=%s prompt=%r", task.id, task.prompt)
        self.memory.save_task(task)

        self._log.info("brain1: planning...")
        plan = self.planner.create_plan(task)
        self.memory.save_plan(plan)
        self._log.info(
            "brain1: done steps=%d risks=%d assumptions=%d",
            len(plan.steps), len(plan.risks), len(plan.assumptions),
        )

        self._log.info("brain2: critiquing...")
        critique = self.critic.review_plan(plan)
        self.memory.save_critique(critique)
        self._log.info(
            "brain2: done score=%d judgement=%s",
            critique.overall_score, critique.final_judgement,
        )

        ready = self._is_ready(critique)
        recommendation = self._compose_recommendation(critique, ready)

        result = FinalResult(
            task_id=task.id,
            original_task=task,
            plan=plan,
            critique=critique,
            final_recommendation=recommendation,
            ready_for_execution=ready,
        )
        self.memory.save_result(result)

        self._log.info(
            "pipeline done ready_for_execution=%s recommendation=%r",
            ready, recommendation,
        )
        return result

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
