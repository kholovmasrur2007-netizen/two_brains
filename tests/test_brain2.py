"""Tests for Brain 2 — Critic."""

from __future__ import annotations

from app.brains.brain2_critic import CriticBrain
from app.types import PlanOutput


def _strong_plan() -> PlanOutput:
    """A plan that should earn a high score — well-formed on every dimension."""
    return PlanOutput(
        task_id="t-strong",
        objective="Build a single-file calculator web app.",
        assumptions=["Modern browser available.", "No internet access required."],
        constraints=["single-file HTML"],
        risks=["Browser compatibility issues may appear across old versions."],
        steps=[
            "Set up the HTML skeleton with one style tag and one script tag.",
            "Implement the arithmetic engine with unit tests covering edge cases.",
            "Wire up the UI and verify manually in Chrome, Firefox and Safari.",
            "Measure page load under 500 ms on a cold cache and fix regressions.",
        ],
        success_criteria=[
            "All unit tests pass with no failures.",
            "Page loads in under 500 ms on mid-range hardware.",
            "No critical console errors during manual QA.",
        ],
        planner_notes="Calculator web app.",
    )


def test_critic_accepts_strong_plan() -> None:
    """A well-formed plan should have no missing/contradictory items and score high."""
    critique = CriticBrain().review_plan(_strong_plan())

    assert critique.task_id == "t-strong"
    assert critique.overall_score >= 85
    assert critique.final_judgement == "accepted"
    assert critique.missing_elements == []
    assert critique.contradictions == []
    assert critique.strengths  # must surface at least one strength


def test_critic_rejects_empty_plan() -> None:
    """A plan missing every section should be rejected outright."""
    critique = CriticBrain().review_plan(PlanOutput(task_id="t-empty"))

    assert critique.final_judgement == "rejected"
    assert critique.overall_score < 35
    # Every hard gap should be reported.
    assert len(critique.missing_elements) >= 4


def test_critic_detects_constraint_contradiction() -> None:
    """'no backend' constraint + steps that introduce a server must be flagged."""
    plan = PlanOutput(
        task_id="t-conflict",
        objective="Build a calculator with persistent history.",
        assumptions=["Browser localStorage is available."],
        constraints=["no backend"],
        risks=["Browser storage has size limits."],
        steps=[
            "Design the calculator UI in HTML.",
            "Store history in a server database via API.",
            "Deploy the server to production and verify with users.",
        ],
        success_criteria=[
            "All calculations produce correct results.",
            "No critical errors reported in 24 hours of use.",
        ],
        planner_notes="Calculator",
    )

    critique = CriticBrain().review_plan(plan)

    assert critique.contradictions, "a contradiction must be reported"
    assert any("no backend" in c.lower() for c in critique.contradictions)
    # A plan with a contradiction can never be accepted.
    assert critique.final_judgement != "accepted"


def test_critic_flags_unmeasurable_success_criteria() -> None:
    """Criteria without numbers/pass-fail tokens should show up as a weakness."""
    plan = PlanOutput(
        task_id="t-vague",
        objective="Implement feature X.",
        assumptions=["Tools available."],
        risks=["Integration may break existing flows."],
        steps=[
            "Write the implementation with tests covering edge cases.",
            "Run the test suite locally and in CI and inspect failures.",
            "Merge after code review from two approvers.",
        ],
        success_criteria=[
            "The feature works correctly.",
            "The code is clean.",
        ],
        planner_notes="Feature X",
    )

    critique = CriticBrain().review_plan(plan)

    assert any("measurable" in w.lower() for w in critique.weaknesses)
    assert any("numbers" in s.lower() or "thresholds" in s.lower() for s in critique.improvement_suggestions)


def test_critic_flags_risk_without_mitigation() -> None:
    """A 'database' risk with no backup/snapshot step in plan.steps must be flagged."""
    plan = PlanOutput(
        task_id="t-risk",
        objective="Migrate the users table to a new schema.",
        assumptions=["Current schema fits the target."],
        constraints=[],
        risks=["Database migration may corrupt user records."],
        steps=[
            "Write the ALTER TABLE statements for the new schema.",
            "Run the statements on production at 2 AM.",
            "Announce completion on the team channel.",
        ],
        success_criteria=[
            "All users load successfully after the migration.",
            "Error rate stays under 0.1% for 24 hours.",
        ],
        planner_notes="Schema migration.",
    )

    critique = CriticBrain().review_plan(plan)

    # Either the 'database' or 'migration' trigger should fire.
    assert critique.risk_flags, "at least one risk flag is expected"
    assert any("mitigation" in f.lower() for f in critique.risk_flags)
