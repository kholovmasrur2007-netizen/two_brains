"""Append-only audit log — who did what, when, from where.

Backed by the ``audit_log`` table; no-ops when ``USE_DB=false`` so dev
runs without a database remain frictionless. Every write goes through
``AuditLogger.log()`` which is exception-safe — a failing log write
must never abort the user's actual operation.

Read access:

    GET /api/audit                  list every entry (admin only)
    GET /api/audit?username=alice   filter by user
    GET /api/audit?action=run       filter by action type
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.auth.core import CurrentUser, get_current_user
from app.config import settings
from app.core.logger import get_logger
from app.utils.helpers import new_id

_log = get_logger(__name__)


class AuditEntry(BaseModel):
    """One row of the audit log surfaced over the REST API."""

    id:        str
    timestamp: str
    username:  str
    action:    str
    target:    str
    ip:        str
    status:    str
    details:   str


# ── writer ────────────────────────────────────────────────────────────


class AuditLogger:
    """Singleton entry point for writing audit entries.

    ``log()`` swallows every exception. The audit log is best-effort —
    losing a row is bad, but failing the user's request because of an
    audit-write error is worse.
    """

    @staticmethod
    def log(
        *,
        action: str,
        username: str | None = None,
        target: str = "",
        ip: str = "",
        status: str = "ok",
        details: str = "",
    ) -> None:
        if not settings.use_db:
            _log.debug("audit (in-memory): user=%s action=%s target=%s status=%s",
                       username, action, target, status)
            return
        try:
            from app.db.engine import AuditLogRow, get_session
            with get_session() as s:
                s.add(AuditLogRow(
                    id=new_id(),
                    username=username or "anonymous",
                    action=action,
                    target=target[:256],
                    ip=ip[:64],
                    status=status,
                    details=details[:4000],
                ))
                s.commit()
        except Exception as e:  # noqa: BLE001
            _log.warning("audit write failed: %s", e)


def _client_ip(request: Request) -> str:
    """Best-effort client IP extraction (handles proxies behind X-Forwarded-For)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


# ── reader (router) ───────────────────────────────────────────────────


audit_router = APIRouter(prefix="/api/audit", tags=["audit"])


@audit_router.get("", response_model=list[AuditEntry])
def list_audit(
    username: str | None = Query(None),
    action: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    user: CurrentUser = Depends(get_current_user),
) -> list[AuditEntry]:
    """Return audit-log entries. Admin-only — non-admins get 403."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    if not settings.use_db:
        raise HTTPException(status_code=503, detail="Audit log requires USE_DB=true")

    from app.db.engine import AuditLogRow, get_session
    with get_session() as s:
        q = s.query(AuditLogRow).order_by(AuditLogRow.timestamp.desc())
        if username:
            q = q.filter(AuditLogRow.username == username)
        if action:
            q = q.filter(AuditLogRow.action == action)
        rows = q.limit(limit).all()
        return [
            AuditEntry(
                id=r.id,
                timestamp=(r.timestamp or datetime.now(timezone.utc)).isoformat(),
                username=r.username or "",
                action=r.action,
                target=r.target or "",
                ip=r.ip or "",
                status=r.status or "ok",
                details=r.details or "",
            )
            for r in rows
        ]
