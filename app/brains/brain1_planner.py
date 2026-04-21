"""Brain 1 - Planner / Architect.

Given a TaskInput, produces a structured PlanOutput.

Responsibilities (kept deliberately narrow):
    * analyse the task and extract the objective
    * surface assumptions and risks
    * break the work into ordered steps
    * define success criteria

Non-responsibilities:
    * executing the plan
    * deep self-critique (that's Brain 2)

The implementation is deterministic for now; an LLM backend can slot in
behind the same public interface later without touching callers.
"""

from __future__ import annotations

import re

from app.types import PlanOutput, TaskInput

# Verbs that typically mark the primary action in a user request.
_ACTION_VERBS: frozenset[str] = frozenset({
    "build", "create", "make", "write", "implement", "code", "design",
    "develop", "fix", "debug", "refactor", "analyze", "analyse", "research",
    "plan", "calculate", "compute", "translate", "convert", "migrate",
    "summarize", "summarise", "explain", "review", "test", "deploy",
})

# Keyword → risk description.
_RISK_KEYWORDS: dict[str, str] = {
    "production": "Touches production - prepare a safe rollback path.",
    "database":   "Schema or data changes can be destructive - back up first.",
    "delete":     "Destructive operation - require explicit confirmation.",
    "api":        "External API may be unavailable, rate-limited or change shape.",
    "security":   "Security-sensitive work - double-check for secret or credential leaks.",
    "legacy":     "Legacy code may have hidden coupling - read before touching.",
    "migration":  "Migrations are hard to roll back - test on a copy first.",
    "payment":    "Payment flows are high-impact - verify end-to-end in staging.",
}


class PlannerBrain:
    """Turn a TaskInput into a structured PlanOutput.

    Every public method is pure - it inspects the input and returns a value
    without side effects. This keeps the planner trivial to test and swap.
    """

    def create_plan(self, task: TaskInput) -> PlanOutput:
        """Produce a structured plan for the given task."""
        prompt = task.prompt.strip()
        return PlanOutput(
            task_id=task.id,
            objective=self._detect_objective(prompt),
            assumptions=self._detect_assumptions(prompt),
            constraints=list(task.constraints),
            risks=self._detect_risks(prompt),
            steps=self._generate_steps(prompt),
            success_criteria=self._generate_success_criteria(prompt),
            planner_notes=self._summarize(prompt),
        )

    # ── internal deterministic heuristics ──────────────────────────────

    @staticmethod
    def _summarize(prompt: str) -> str:
        """Return a one-line summary: first sentence, trimmed to 140 chars."""
        if not prompt:
            return ""
        first = re.split(r"(?<=[.!?])\s+", prompt, maxsplit=1)[0].strip()
        return (first[:140] + "...") if len(first) > 140 else first

    def _detect_objective(self, prompt: str) -> str:
        """Derive the objective from the prompt.

        If the first sentence begins with a known action verb we use it as-is.
        Otherwise we prepend ``Address:`` so the field is never empty.
        """
        summary = self._summarize(prompt)
        if not summary:
            return "Clarify the task with the requester."
        first_word = summary.split(maxsplit=1)[0].lower()
        if first_word in _ACTION_VERBS:
            return summary[0].upper() + summary[1:]
        return f"Address: {summary}"

    @staticmethod
    def _detect_assumptions(prompt: str) -> list[str]:
        """Return generic assumptions, tailored by prompt keywords."""
        low = prompt.lower()
        assumptions = [
            "The task description is complete and accurate.",
            "Required tools and runtime environment are available.",
        ]
        if any(w in low for w in ("api", "fetch", "http", "request", "url")):
            assumptions.append("Network access to the target endpoint is available.")
        if any(w in low for w in ("file", "read", "write", "disk", "folder", "directory")):
            assumptions.append("Filesystem read/write permissions are granted where needed.")
        if any(w in low for w in ("user", "customer", "client")):
            assumptions.append("Affected users are informed about relevant changes.")
        return assumptions

    @staticmethod
    def _detect_risks(prompt: str) -> list[str]:
        """Return risks inferred from keywords, plus a baseline risk."""
        low = prompt.lower()
        risks = [desc for kw, desc in _RISK_KEYWORDS.items() if kw in low]
        if not risks:
            risks.append("Scope creep - confirm the objective before starting implementation.")
        return risks

    @staticmethod
    def _generate_steps(prompt: str) -> list[str]:
        """Produce a generic but useful step-by-step plan.

        A stable template so the orchestrator can be tested end-to-end.
        A future LLM-backed version will tailor each step to the concrete prompt.
        """
        return [
            "Restate the objective in your own words and confirm anything unclear with the requester.",
            "Identify concrete inputs, outputs and constraints.",
            "Split the work into the smallest useful sub-tasks.",
            "For each sub-task, pick a tool or technique and note the expected result.",
            "Execute the sub-tasks in order, verifying output at each step.",
            "Collect the outputs into the final deliverable.",
            "Validate the deliverable against the success criteria.",
        ]

    @staticmethod
    def _generate_success_criteria(prompt: str) -> list[str]:
        """Return generic success criteria; later brains can refine them."""
        return [
            "The produced artefact satisfies the objective as stated.",
            "All identified constraints are respected.",
            "No critical risk has materialised during execution.",
            "The outcome is reproducible from the recorded plan.",
        ]
