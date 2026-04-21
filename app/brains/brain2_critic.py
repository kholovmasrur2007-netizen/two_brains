"""Brain 2 - Critic / Judge.

Given a PlanOutput, produces a structured CritiqueOutput.

Responsibilities (kept deliberately narrow):
    * inspect the plan and score it
    * surface strengths, weaknesses and missing elements
    * flag contradictions between constraints and steps
    * flag declared risks that have no matching mitigation step
    * suggest improvements and per-step notes
    * render a single final_judgement the orchestrator can route on

Non-responsibilities:
    * producing a new plan (that is Brain 1)
    * executing the plan

The implementation is deterministic for now; an LLM backend can slot in
behind the same public interface later.
"""

from __future__ import annotations

from app.types import CritiqueOutput, PlanOutput
from app.types.critique import Judgement

# Constraint phrase → forbidden step keywords.
# Matched as substrings on lowercase text.
_CONSTRAINT_CONFLICTS: dict[str, tuple[str, ...]] = {
    "no backend":  ("server", "backend", "database", "deploy server", "microservice"),
    "no database": ("database", "sql ", "schema", "migration"),
    "no server":   ("server", "backend", "deploy"),
    "offline":     ("http", "fetch", " api ", "network request", "download"),
    "single-file": ("multiple files", "separate file", "split into files"),
    "no framework": ("react", "vue", "angular", "django", "flask"),
}

# Risk keyword (scanned in plan.risks) → mitigation keywords that must appear in plan.steps.
_MITIGATION_MAP: dict[str, tuple[str, ...]] = {
    "destructive": ("confirm", "validate", "backup", "dry run", "rollback"),
    "production":  ("rollback", "staging", "canary", "feature flag"),
    "database":    ("backup", "snapshot", "migration plan"),
    "delete":      ("confirm", "verify", "soft delete", "backup"),
    "migration":   ("rollback", "back up", "snapshot", "dry run"),
    "payment":     ("staging", "sandbox", "idempotent", "reconcile"),
    "security":    ("review", "audit", "scan", "threat model"),
}

# Tokens that make a success criterion measurable.
_MEASURABLE_HINTS: tuple[str, ...] = (
    "%", "within", "under ", "less than", "more than", "at least", "at most",
    "exceeds", "seconds", "second", "ms", "minutes", "hours", "days",
    "pass", "fail", "error", "coverage", "no ", "all ", "every ",
    "zero ", "100", "= ", "<=", ">=", "==",
)

# Words that flag vague or lazy phrasing in steps.
_VAGUE_WORDS: tuple[str, ...] = (
    "somehow", "maybe", "probably", "etc", "etc.", " things ", " stuff ",
    "something", "some kind of",
)


class CriticBrain:
    """Review a PlanOutput and return a structured CritiqueOutput.

    Public method is ``review_plan``. Everything else is a private heuristic.
    All methods are pure: they read the plan and derive output without side effects.
    """

    # Tuning knobs. Keep them as class attributes so tests can override.
    MIN_STEPS: int = 3
    MIN_SUCCESS_CRITERIA: int = 2
    MIN_STEP_LENGTH: int = 20

    # Score penalties (subtracted from 100).
    PENALTY_MISSING: int = 18
    PENALTY_CONTRADICTION: int = 12
    PENALTY_RISK_FLAG: int = 8
    PENALTY_WEAKNESS: int = 6

    # Judgement thresholds (on the 0-100 score).
    ACCEPT_AT: int = 85
    MINOR_AT: int = 60
    MAJOR_AT: int = 35

    def review_plan(self, plan: PlanOutput) -> CritiqueOutput:
        """Inspect the plan and produce a full critique."""
        strengths = self._find_strengths(plan)
        missing = self._find_missing(plan)
        weaknesses = self._find_weaknesses(plan)
        contradictions = self._find_contradictions(plan)
        risk_flags = self._find_risk_flags(plan)
        step_notes = self._make_step_notes(plan)
        suggestions = self._make_suggestions(plan, missing, weaknesses, contradictions, risk_flags)
        score = self._score(missing, contradictions, risk_flags, weaknesses)
        judgement = self._final_judgement(score, missing, contradictions)

        return CritiqueOutput(
            task_id=plan.task_id,
            overall_score=score,
            strengths=strengths,
            weaknesses=weaknesses,
            missing_elements=missing,
            contradictions=contradictions,
            risk_flags=risk_flags,
            improvement_suggestions=suggestions,
            revised_step_notes=step_notes,
            final_judgement=judgement,
        )

    # ── strengths / weaknesses / missing ───────────────────────────────

    @staticmethod
    def _find_strengths(plan: PlanOutput) -> list[str]:
        """Highlight aspects of the plan that are already good."""
        out: list[str] = []
        if plan.objective and not _is_placeholder_objective(plan.objective):
            out.append("Objective is stated directly with an action verb.")
        if len(plan.steps) >= CriticBrain.MIN_STEPS:
            out.append(f"Plan contains {len(plan.steps)} concrete step(s).")
        if len(plan.success_criteria) >= CriticBrain.MIN_SUCCESS_CRITERIA:
            out.append(f"{len(plan.success_criteria)} success criteria are defined.")
        if plan.risks:
            out.append("Risks have been surfaced.")
        if plan.assumptions:
            out.append("Assumptions are documented.")
        if plan.constraints:
            out.append("Constraints are explicit.")
        return out

    @staticmethod
    def _find_missing(plan: PlanOutput) -> list[str]:
        """List hard gaps - things that must be filled before execution."""
        out: list[str] = []
        if not plan.objective.strip() or _is_placeholder_objective(plan.objective):
            out.append("Objective is empty or a placeholder.")
        if not plan.steps:
            out.append("Plan has no steps.")
        if not plan.success_criteria:
            out.append("No success criteria defined.")
        if not plan.assumptions:
            out.append("No assumptions documented.")
        if not plan.risks:
            out.append("No risks identified.")
        return out

    def _find_weaknesses(self, plan: PlanOutput) -> list[str]:
        """Soft problems - the plan works but can be improved."""
        out: list[str] = []

        # Step count.
        if 0 < len(plan.steps) < self.MIN_STEPS:
            out.append(
                f"Only {len(plan.steps)} step(s) - below the {self.MIN_STEPS}-step minimum."
            )

        # Per-step issues, derived from the single source of truth.
        short_indexes: list[int] = []
        vague_indexes: list[int] = []
        for i, step in enumerate(plan.steps, start=1):
            issues = self._step_issues(step)
            if "too short" in issues:
                short_indexes.append(i)
            if "vague" in issues:
                vague_indexes.append(i)
        if short_indexes:
            out.append(f"Step(s) {short_indexes} are too short to be actionable.")
        if vague_indexes:
            out.append(f"Step(s) {vague_indexes} contain vague language - be specific.")

        # Duplicates.
        seen: dict[str, int] = {}
        duplicates: list[str] = []
        for i, step in enumerate(plan.steps):
            key = step.strip().lower()
            if not key:
                continue
            if key in seen:
                duplicates.append(f"step {i + 1} duplicates step {seen[key] + 1}")
            else:
                seen[key] = i
        if duplicates:
            out.append("Duplicate steps detected: " + "; ".join(duplicates) + ".")

        # Measurable criteria.
        if plan.success_criteria:
            unmeasurable = [
                i + 1 for i, c in enumerate(plan.success_criteria) if not _is_measurable(c)
            ]
            if unmeasurable:
                out.append(
                    f"Success criteria {unmeasurable} lack measurable language "
                    "(no numbers, thresholds or pass/fail tokens)."
                )

        # Baseline-only risks.
        if len(plan.risks) == 1 and "scope creep" in plan.risks[0].lower():
            out.append(
                "Only the baseline 'scope creep' risk - domain-specific risks are likely missing."
            )

        # Objective without an action verb.
        if plan.objective and _is_placeholder_objective(plan.objective):
            out.append("Objective lacks a clear action verb.")

        return out

    # ── contradictions / risks ─────────────────────────────────────────

    @staticmethod
    def _find_contradictions(plan: PlanOutput) -> list[str]:
        """Flag steps whose keywords violate one of the plan's constraints."""
        out: list[str] = []
        steps_text = " ".join(plan.steps).lower()
        for constraint in plan.constraints:
            low = constraint.lower()
            for phrase, forbidden in _CONSTRAINT_CONFLICTS.items():
                if phrase in low:
                    hits = [w for w in forbidden if w in steps_text]
                    if hits:
                        out.append(
                            f"Constraint '{constraint}' is contradicted by step keyword(s): "
                            f"{', '.join(hits)}."
                        )
        return out

    @staticmethod
    def _find_risk_flags(plan: PlanOutput) -> list[str]:
        """For every declared risk, check that a mitigation appears in steps."""
        out: list[str] = []
        steps_text = " ".join(plan.steps).lower()
        risks_text = " ".join(plan.risks).lower()
        for trigger, mitigations in _MITIGATION_MAP.items():
            if trigger in risks_text:
                if not any(m in steps_text for m in mitigations):
                    out.append(
                        f"Risk signal '{trigger}' has no matching mitigation step "
                        f"(expected one of: {', '.join(mitigations)})."
                    )
        return out

    # ── per-step notes and suggestions ─────────────────────────────────

    def _make_step_notes(self, plan: PlanOutput) -> list[str]:
        """Render per-step feedback from _step_issues into human-readable notes."""
        messages = {
            "too short": "too short - expand with specifics",
            "heading":   "looks like a heading - replace with an actionable sentence",
            "vague":     "contains vague language",
        }
        notes: list[str] = []
        for i, step in enumerate(plan.steps, start=1):
            issues = self._step_issues(step)
            if issues:
                notes.append(f"Step {i}: " + "; ".join(messages[tag] for tag in issues) + ".")
        return notes

    def _step_issues(self, step: str) -> list[str]:
        """Return a list of issue tags for a single step.

        Tags are stable identifiers - see ``_make_step_notes`` for the
        human-readable message each one maps to. Keeping this helper as the
        single source of truth prevents weaknesses and per-step notes from
        drifting apart.
        """
        stripped = step.strip()
        tags: list[str] = []
        if len(stripped) < self.MIN_STEP_LENGTH:
            tags.append("too short")
        if stripped.endswith(":"):
            tags.append("heading")
        lowered = f" {stripped.lower()} "
        if any(v in lowered for v in _VAGUE_WORDS):
            tags.append("vague")
        return tags

    @staticmethod
    def _make_suggestions(
        plan: PlanOutput,
        missing: list[str],
        weaknesses: list[str],
        contradictions: list[str],
        risk_flags: list[str],
    ) -> list[str]:
        """Actionable recommendations derived from the above findings."""
        out: list[str] = []
        if missing:
            out.append("Fill in the missing sections before sending the plan to execution.")
        if contradictions:
            out.append("Resolve every constraint/step contradiction or drop the offending step.")
        if risk_flags:
            out.append("Add explicit mitigation steps for each flagged risk (backup, rollback, dry run, etc.).")
        if any("measurable" in w for w in weaknesses):
            out.append("Rewrite success criteria with concrete numbers (thresholds, counts, time limits, pass/fail).")
        if any("below the" in w and "step minimum" in w for w in weaknesses):
            out.append("Break the main step into at least three smaller verifiable actions.")
        if any("baseline" in w for w in weaknesses):
            out.append("Replace the baseline risk with domain-specific risks relevant to this task.")
        if not plan.constraints:
            out.append("Ask the requester whether any hard constraints apply (scope, stack, budget, deadline).")
        return out

    # ── scoring ────────────────────────────────────────────────────────

    def _score(
        self,
        missing: list[str],
        contradictions: list[str],
        risk_flags: list[str],
        weaknesses: list[str],
    ) -> int:
        """Aggregate 0–100 score; lower is worse.

        Each category subtracts from a perfect 100. Weights express how
        severe each category is relative to the others.
        """
        score = 100
        score -= self.PENALTY_MISSING * len(missing)
        score -= self.PENALTY_CONTRADICTION * len(contradictions)
        score -= self.PENALTY_RISK_FLAG * len(risk_flags)
        score -= self.PENALTY_WEAKNESS * len(weaknesses)
        return max(0, min(100, score))

    def _final_judgement(
        self,
        score: int,
        missing: list[str],
        contradictions: list[str],
    ) -> Judgement:
        """Route the plan: accepted / minor / major / rejected.

        Hard gaps (missing elements or contradictions) never upgrade to
        'accepted' regardless of the numeric score - they block the plan.
        """
        if missing or contradictions:
            if score < self.MAJOR_AT:
                return "rejected"
            return "needs_major_revision"
        if score >= self.ACCEPT_AT:
            return "accepted"
        if score >= self.MINOR_AT:
            return "needs_minor_revision"
        if score >= self.MAJOR_AT:
            return "needs_major_revision"
        return "rejected"


# ── module-level helpers (shared by methods above) ─────────────────────


def _is_placeholder_objective(objective: str) -> bool:
    """True when the planner couldn't derive a real objective."""
    lowered = objective.strip().lower()
    return lowered.startswith("address:") or lowered.startswith("clarify the task")


def _is_measurable(text: str) -> bool:
    """True when the criterion contains at least one measurable token."""
    low = text.lower()
    return any(hint in low for hint in _MEASURABLE_HINTS)
