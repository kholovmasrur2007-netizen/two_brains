"""SQLMemoryStore — database-backed drop-in for MemoryStore.

Implements the exact same public API as ``app.memory.store.MemoryStore``
so the orchestrator, CLI and Web server can use either without any
conditional logic — just swap which class is injected.

Differences from the JSON-file store:
    * Concurrent-safe: multiple processes can read/write simultaneously.
    * Persistent across restarts without any file-path configuration.
    * Switches from SQLite to PostgreSQL with one DATABASE_URL env var.
"""

from __future__ import annotations

import textwrap

from pydantic import ValidationError

from app.core.logger import get_logger
from app.db.engine import Base, CritiqueRow, PlanRow, ResultRow, TaskRow, UserRow, get_session, init_db
from app.types import CritiqueOutput, FinalResult, PlanOutput, TaskInput

_log = get_logger(__name__)


class SQLMemoryStore:
    """Persistent memory store backed by SQLAlchemy.

    Drop-in replacement for ``MemoryStore``. Pass an instance wherever
    the orchestrator / web server expect a ``MemoryStore``.

    Args:
        url: optional SQLAlchemy database URL. When given, a private
             engine is created for this store instance (used in tests
             to get an isolated per-test database). When omitted the
             global shared engine from ``app.db.engine`` is used.
    """

    def __init__(self, url: str | None = None) -> None:
        if url is not None:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
            self._private_engine = create_engine(url, connect_args=connect_args, echo=False)
            Base.metadata.create_all(self._private_engine)
            self._Session = sessionmaker(bind=self._private_engine)
        else:
            self._private_engine = None
            self._Session = None
            init_db()

    # ── session helper ─────────────────────────────────────────────────

    def _session(self):
        """Return a session from the private engine (tests) or global engine."""
        if self._Session is not None:
            return self._Session()
        return get_session()

    # ── saves ──────────────────────────────────────────────────────────

    def save_task(self, task: TaskInput) -> None:
        with self._session() as s:
            row = s.get(TaskRow, task.id)
            if row:
                row.data = task.model_dump()
            else:
                s.add(TaskRow(id=task.id, data=task.model_dump()))
            s.commit()

    def save_plan(self, plan: PlanOutput) -> None:
        with self._session() as s:
            row = s.get(PlanRow, plan.task_id)
            if row:
                row.data = plan.model_dump()
            else:
                s.add(PlanRow(task_id=plan.task_id, data=plan.model_dump()))
            s.commit()

    def save_critique(self, critique: CritiqueOutput) -> None:
        with self._session() as s:
            row = s.get(CritiqueRow, critique.task_id)
            if row:
                row.data = critique.model_dump()
            else:
                s.add(CritiqueRow(task_id=critique.task_id, data=critique.model_dump()))
            s.commit()

    def save_result(self, result: FinalResult) -> None:
        with self._session() as s:
            row = s.get(ResultRow, result.task_id)
            if row:
                row.data = result.model_dump()
            else:
                s.add(ResultRow(task_id=result.task_id, data=result.model_dump()))
            s.commit()

    # ── getters ────────────────────────────────────────────────────────

    def get_task(self, task_id: str) -> TaskInput | None:
        with self._session() as s:
            row = s.get(TaskRow, task_id)
            if row is None:
                return None
            try:
                return TaskInput.model_validate(row.data)
            except (ValidationError, TypeError):
                return None

    def get_plan(self, task_id: str) -> PlanOutput | None:
        with self._session() as s:
            row = s.get(PlanRow, task_id)
            if row is None:
                return None
            try:
                return PlanOutput.model_validate(row.data)
            except (ValidationError, TypeError):
                return None

    def get_critique(self, task_id: str) -> CritiqueOutput | None:
        with self._session() as s:
            row = s.get(CritiqueRow, task_id)
            if row is None:
                return None
            try:
                return CritiqueOutput.model_validate(row.data)
            except (ValidationError, TypeError):
                return None

    def get_result(self, task_id: str) -> FinalResult | None:
        with self._session() as s:
            row = s.get(ResultRow, task_id)
            if row is None:
                return None
            try:
                return FinalResult.model_validate(row.data)
            except (ValidationError, TypeError):
                return None

    # ── introspection ──────────────────────────────────────────────────

    def known_task_ids(self) -> list[str]:
        with self._session() as s:
            rows = s.query(TaskRow.id).order_by(TaskRow.created_at.desc()).all()
            return [r.id for r in rows]

    # ── MemoryStore compat attrs (orchestrator accesses these directly) ─

    @property
    def tasks(self) -> dict[str, TaskInput]:
        with self._session() as s:
            rows = s.query(TaskRow).all()
            result = {}
            for row in rows:
                try:
                    result[row.id] = TaskInput.model_validate(row.data)
                except (ValidationError, TypeError):
                    pass
            return result

    @property
    def plans(self) -> dict[str, PlanOutput]:
        with self._session() as s:
            rows = s.query(PlanRow).all()
            result = {}
            for row in rows:
                try:
                    result[row.task_id] = PlanOutput.model_validate(row.data)
                except (ValidationError, TypeError):
                    pass
            return result

    @property
    def critiques(self) -> dict[str, CritiqueOutput]:
        with self._session() as s:
            rows = s.query(CritiqueRow).all()
            result = {}
            for row in rows:
                try:
                    result[row.task_id] = CritiqueOutput.model_validate(row.data)
                except (ValidationError, TypeError):
                    pass
            return result

    @property
    def results(self) -> dict[str, FinalResult]:
        with self._session() as s:
            rows = s.query(ResultRow).all()
            result = {}
            for row in rows:
                try:
                    result[row.task_id] = FinalResult.model_validate(row.data)
                except (ValidationError, TypeError):
                    pass
            return result
