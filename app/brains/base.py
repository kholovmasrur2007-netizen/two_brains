"""Protocols the orchestrator uses to talk to any brain.

These are ``typing.Protocol`` classes, not abstract base classes: existing
deterministic brains (and any future LLM-backed ones) are accepted as long as
they expose the right method signature — no inheritance required.

Why Protocol and not ABC?
    * zero-impact on existing classes — PlannerBrain already fits the contract
    * lets us plug in classes from third-party packages without subclassing
    * @runtime_checkable still lets ``isinstance(obj, Planner)`` work for
      defensive assertions in the orchestrator
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.types import CritiqueOutput, ExecutionOutput, PlanOutput, TaskInput


@runtime_checkable
class Planner(Protocol):
    """Anything that turns a TaskInput into a PlanOutput is a Planner."""

    def create_plan(self, task: TaskInput) -> PlanOutput:
        """Produce a structured plan for the given task."""
        ...


@runtime_checkable
class Critic(Protocol):
    """Anything that turns a PlanOutput into a CritiqueOutput is a Critic."""

    def review_plan(self, plan: PlanOutput) -> CritiqueOutput:
        """Return structured feedback on the given plan."""
        ...


@runtime_checkable
class RevisingPlanner(Planner, Protocol):
    """A Planner that can also revise a plan given a critique.

    The orchestrator checks for this Protocol to decide whether to run
    the iterative plan -> critique -> revise loop. A planner that only
    implements ``create_plan`` gets exactly one pass.
    """

    def revise_plan(
        self,
        task: TaskInput,
        prior_plan: PlanOutput,
        critique: CritiqueOutput,
    ) -> PlanOutput:
        """Return an improved plan that addresses the critique."""
        ...


@runtime_checkable
class Executor(Protocol):
    """Anything that walks a PlanOutput and produces an ExecutionOutput.

    Implementations may simulate execution (deterministic, LLM-reasoned)
    or perform real side effects in a sandbox. The orchestrator never
    inspects the implementation — it only consumes the report.
    """

    def execute_plan(self, task: TaskInput, plan: PlanOutput) -> ExecutionOutput:
        """Run the plan's steps in order and return a structured report."""
        ...
