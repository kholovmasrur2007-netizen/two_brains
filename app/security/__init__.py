"""Security primitives — rate limiting, per-user quotas, audit log.

Each submodule is self-contained:

    * ``rate_limit`` — slowapi limiter wired into FastAPI
    * ``quotas``     — per-user daily task budget (DB-backed)
    * ``audit``      — append-only log of who did what, when

Nothing here imports an LLM SDK; everything is pure Python so unit
tests run instantly without network access.
"""

from app.security.audit import AuditLogger, audit_router
from app.security.quotas import DailyQuotaExceeded, check_and_record_quota
from app.security.rate_limit import limiter, rate_limit_handler

__all__ = [
    "limiter",
    "rate_limit_handler",
    "AuditLogger",
    "audit_router",
    "DailyQuotaExceeded",
    "check_and_record_quota",
]
