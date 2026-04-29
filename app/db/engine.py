"""SQLAlchemy engine + table definitions.

Supports:
    SQLite   — default, zero config, file ``two_brains.db`` next to the app.
    PostgreSQL — set DATABASE_URL=postgresql+psycopg2://user:pass@host/db

Switching is one env-var change; no application code needs to change.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class TaskRow(Base):
    __tablename__ = "tasks"
    id         = Column(String(64), primary_key=True)
    data       = Column(JSON,    nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class PlanRow(Base):
    __tablename__ = "plans"
    task_id    = Column(String(64), primary_key=True)
    data       = Column(JSON,    nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CritiqueRow(Base):
    __tablename__ = "critiques"
    task_id    = Column(String(64), primary_key=True)
    data       = Column(JSON,    nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ResultRow(Base):
    __tablename__ = "results"
    task_id    = Column(String(64), primary_key=True)
    data       = Column(JSON,    nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class UserRow(Base):
    __tablename__ = "users"
    username      = Column(String(64), primary_key=True)
    password_hash = Column(Text, nullable=False)
    is_admin      = Column(String(5), default="false")  # "true"/"false" — sqlite compat


class AuditLogRow(Base):
    __tablename__ = "audit_log"
    id        = Column(String(64), primary_key=True)
    timestamp = Column(DateTime, server_default=func.now(), index=True)
    username  = Column(String(64), index=True)
    action    = Column(String(64), nullable=False)        # login / register / run / view_task
    target    = Column(String(256), default="")           # task_id, username, etc.
    ip        = Column(String(64), default="")
    status    = Column(String(16), default="ok")          # ok / fail / error
    details   = Column(Text, default="")


class QuotaRow(Base):
    """Daily per-user task counter. Reset by date in app code."""
    __tablename__ = "quotas"
    username = Column(String(64), primary_key=True)
    date_ymd = Column(String(10), primary_key=True)       # "2026-04-29"
    count    = Column(String(8),  default="0")            # stored as str for sqlite/pg compat


# ── engine singleton ─────────────────────────────────────────────────

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = settings.database_url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, echo=False)
    return _engine


def get_session() -> Session:
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return SessionLocal()


def init_db() -> None:
    """Create tables if they don't exist (idempotent)."""
    Base.metadata.create_all(get_engine())
