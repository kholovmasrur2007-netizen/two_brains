"""Brain 2 — Safety critic.

A deterministic, regex-driven critic that ignores the plan's
*correctness* and focuses only on **execution safety**: would running
this plan touch dangerous shell, escape the sandbox, hit the network,
or leak privileges? It is meant to run *alongside* the regular critic
in dual-critic mode — the orchestrator combines both verdicts and
takes the worse of the two scores so safety can never be overridden
by a confident-sounding correctness pass.

Score model:
    100  — clean
    -15  per dangerous-pattern hit (rm -rf, sudo, chmod 777, network …)
    -50  per traversal token (`../`, `/c:`) found in any step or risk
    -20  per "module not found" / "unknown command" hint in steps
    -10  per read_file referenced without a corresponding write_file
    -10  if the plan writes anything but declares no risks
     -5  per fuzzy success criterion ("should work", "hopefully", "maybe")

The judgement maps from the final score:
    >= 85   accepted
    >= 70   needs_minor_revision
    >= 40   needs_major_revision
    else    rejected
"""

from __future__ import annotations

import re

from app.brains.base import Critic
from app.types import CritiqueOutput, PlanOutput

DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\brm\s+-rf\s+",           "Удаление с -rf"),
    (r"\bsudo\b",                "sudo"),
    (r"\bchmod\s+777\b",         "широкие права (chmod 777)"),
    (r"\bcurl\b|\bwget\b",       "сетевые запросы (curl/wget)"),
    (r"\bpython\s+-m\s+http\.server\b", "веб-сервер (python -m http.server)"),
    (r"\bsubprocess\b|\bos\.system\b",  "shell-вызов (subprocess / os.system)"),
    (r"\.\./",                   "выход из песочницы (../)"),
]

# Compile once.
_DANGEROUS = [(re.compile(pat, re.IGNORECASE), desc) for pat, desc in DANGEROUS_PATTERNS]

_TRAVERSAL_RE = re.compile(r"\.\./|/c:|\\\\?[A-Za-z]:[\\/]")
_READ_RE      = re.compile(r"\bread_file\s*\(\s*['\"]([^'\"]+)['\"]")
_WRITE_RE     = re.compile(r"\bwrite_file\s*\(\s*['\"]([^'\"]+)['\"]")
_MODULE_RE    = re.compile(r"\b(module not found|unknown command|no such file|command not found)\b", re.IGNORECASE)
_FUZZY_RE     = re.compile(r"\b(should work|hopefully|maybe|might work)\b", re.IGNORECASE)


def _judgement_for(score: int):
    if score >= 85:
        return "accepted"
    if score >= 70:
        return "needs_minor_revision"
    if score >= 40:
        return "needs_major_revision"
    return "rejected"


class SafetyCritic:
    """Static-analysis safety critic. Implements the ``Critic`` Protocol."""

    def review_plan(self, plan: PlanOutput) -> CritiqueOutput:
        score = 100
        weaknesses: list[str] = []
        missing: list[str] = []
        contradictions: list[str] = []
        suggestions: list[str] = []

        joined_steps = "\n".join(plan.steps)

        # ── 1. Dangerous shell / network / privilege patterns ─────────
        # -20 per match: even a single dangerous keyword must drop the
        # plan below the orchestrator's 85-point bar so the executor refuses.
        for regex, desc in _DANGEROUS:
            if regex.search(joined_steps):
                weaknesses.append(f"Опасный паттерн: {desc}")
                score -= 20

        # ── 2. Traversal escape (../, /c:, C:\) anywhere in the plan ─
        full_text = joined_steps + "\n" + " ".join(plan.risks) + "\n" + plan.objective
        if _TRAVERSAL_RE.search(full_text):
            contradictions.append("Найдена попытка выхода из песочницы (../ или drive-letter)")
            score -= 50

        # ── 3. Module-not-found / unknown-command hints ──────────────
        for step in plan.steps:
            if _MODULE_RE.search(step):
                weaknesses.append(f"Признак ошибки в шаге: {step[:80]}")
                score -= 20

        # ── 4. Read without matching write ───────────────────────────
        reads  = set(_READ_RE.findall(joined_steps))
        writes = set(_WRITE_RE.findall(joined_steps))
        for path in reads - writes:
            weaknesses.append(f"read_file({path}) без соответствующего write_file")
            score -= 10

        # ── 5. Writes without declared risks ─────────────────────────
        if writes and not plan.risks:
            missing.append("План пишет файлы, но риски не задекларированы")
            score -= 10

        # ── 6. Fuzzy success criteria ────────────────────────────────
        for crit in plan.success_criteria:
            if _FUZZY_RE.search(crit):
                weaknesses.append(f"Расплывчатый критерий: {crit[:80]}")
                score -= 5

        # ── Compose ──────────────────────────────────────────────────
        final_score = max(0, min(100, score))
        if not weaknesses and not missing and not contradictions:
            suggestions.append("План прошёл safety-проверку без замечаний.")
        else:
            suggestions.append("Перепиши шаги без опасных паттернов и добавь mitigation для всех писательских операций.")

        return CritiqueOutput(
            task_id=plan.task_id,
            overall_score=final_score,
            strengths=["Safety-сканер не нашёл критических нарушений."] if final_score >= 85 else [],
            weaknesses=weaknesses,
            missing_elements=missing,
            contradictions=contradictions,
            risk_flags=[],
            improvement_suggestions=suggestions,
            revised_step_notes=[],
            final_judgement=_judgement_for(final_score),
        )


# Self-check that we satisfy the Critic Protocol at import time.
assert isinstance(SafetyCritic(), Critic)  # noqa: S101
