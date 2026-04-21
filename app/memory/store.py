"""Local memory layer for the 2-brain pipeline.

In-memory by default; if a ``path`` is provided the store mirrors its state to
a single JSON file. Writes are atomic (write-temp + rename). Reads happen once,
on construction. This is intentionally simple — single-process, no locking,
no SQL. A database backend can slot in behind the same public API later.

Design decisions kept deliberately tight:

* one task → one plan → one critique → one result (latest wins on repeat save)
* ``get_*`` returns ``None`` for unknown ids instead of raising
* disk failures are logged at warning level and never crash the caller
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.core.logger import get_logger
from app.types import CritiqueOutput, FinalResult, PlanOutput, TaskInput

_log = get_logger(__name__)


class MemoryStore:
    """Keyed, in-memory artefact store with optional JSON persistence."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Create a new store.

        Args:
            path: Optional JSON file to persist to. If given and the file
                exists, its contents are loaded on construction. Each
                subsequent ``save_*`` call rewrites the file atomically.
                Pass ``None`` (default) for a pure in-process store.
        """
        self._path: Path | None = Path(path) if path is not None else None

        self.tasks: dict[str, TaskInput] = {}
        self.plans: dict[str, PlanOutput] = {}
        self.critiques: dict[str, CritiqueOutput] = {}
        self.results: dict[str, FinalResult] = {}

        if self._path is not None and self._path.exists():
            self._load()

    # ── saves ──────────────────────────────────────────────────────────

    def save_task(self, task: TaskInput) -> None:
        """Store a task, overwriting any previous entry with the same id."""
        self.tasks[task.id] = task
        self._flush()

    def save_plan(self, plan: PlanOutput) -> None:
        """Store the plan for its task, overwriting any previous entry."""
        self.plans[plan.task_id] = plan
        self._flush()

    def save_critique(self, critique: CritiqueOutput) -> None:
        """Store the critique for its task, overwriting any previous entry."""
        self.critiques[critique.task_id] = critique
        self._flush()

    def save_result(self, result: FinalResult) -> None:
        """Store the final pipeline result, overwriting any previous entry."""
        self.results[result.task_id] = result
        self._flush()

    # ── getters ────────────────────────────────────────────────────────

    def get_task(self, task_id: str) -> TaskInput | None:
        """Return the stored task or ``None`` if unknown."""
        return self.tasks.get(task_id)

    def get_plan(self, task_id: str) -> PlanOutput | None:
        """Return the stored plan or ``None`` if unknown."""
        return self.plans.get(task_id)

    def get_critique(self, task_id: str) -> CritiqueOutput | None:
        """Return the stored critique or ``None`` if unknown."""
        return self.critiques.get(task_id)

    def get_result(self, task_id: str) -> FinalResult | None:
        """Return the stored final result or ``None`` if unknown."""
        return self.results.get(task_id)

    # ── introspection helpers ──────────────────────────────────────────

    def known_task_ids(self) -> list[str]:
        """Return the ids of every task the store has ever seen."""
        return list(self.tasks.keys())

    # ── persistence internals (only active when a path was provided) ──

    def _flush(self) -> None:
        """Persist the full snapshot to disk atomically. No-op without a path."""
        if self._path is None:
            return
        data = {
            "tasks":     {k: v.model_dump() for k, v in self.tasks.items()},
            "plans":     {k: v.model_dump() for k, v in self.plans.items()},
            "critiques": {k: v.model_dump() for k, v in self.critiques.items()},
            "results":   {k: v.model_dump() for k, v in self.results.items()},
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_name(self._path.name + ".tmp")
            tmp.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            # ``replace`` is atomic on POSIX and best-effort on Windows.
            tmp.replace(self._path)
        except OSError as e:
            _log.warning("memory flush failed for %s: %s", self._path, e)

    def _load(self) -> None:
        """Populate the dicts from the JSON file. Resets to empty on any error."""
        if self._path is None:
            return  # defensive: callers guard this, but don't trust assert under -O
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as e:
            _log.warning("memory load failed for %s (%s) - starting empty", self._path, e)
            return
        try:
            self.tasks = {
                k: TaskInput.model_validate(v) for k, v in data.get("tasks", {}).items()
            }
            self.plans = {
                k: PlanOutput.model_validate(v) for k, v in data.get("plans", {}).items()
            }
            self.critiques = {
                k: CritiqueOutput.model_validate(v) for k, v in data.get("critiques", {}).items()
            }
            self.results = {
                k: FinalResult.model_validate(v) for k, v in data.get("results", {}).items()
            }
        except (TypeError, ValidationError) as e:
            _log.warning(
                "memory schema mismatch in %s (%s) - starting empty",
                self._path, e,
            )
            self.tasks = {}
            self.plans = {}
            self.critiques = {}
            self.results = {}
