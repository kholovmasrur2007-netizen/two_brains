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

from app.types import CritiqueOutput, PlanOutput, TaskInput


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
