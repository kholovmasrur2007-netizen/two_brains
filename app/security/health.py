"""Liveness / readiness / Prometheus endpoints — operations basics.

    GET /health              quick liveness probe (always 200 if process is up)
    GET /ready               readiness — checks DB connectivity when USE_DB=true
    GET /metrics             Prometheus text-format metrics (counts, in-flight)

The metrics module deliberately uses no external client library — we
emit Prometheus exposition format by hand so the binary deps don't
balloon for what is a small set of counters.
"""

from __future__ import annotations

import os
import time
from threading import Lock

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.config import settings

_started_at: float = time.time()
_lock = Lock()

# In-memory counters. Reset on process restart — adequate for a single
# instance; scrape-frequency aggregation handles the rest.
_counters: dict[str, int] = {
    "two_brains_requests_total":      0,
    "two_brains_runs_total":          0,
    "two_brains_runs_failed_total":   0,
    "two_brains_auth_logins_total":   0,
    "two_brains_auth_failures_total": 0,
    "two_brains_quota_exceeded_total": 0,
    "two_brains_rate_limited_total":  0,
}


def increment(metric: str, n: int = 1) -> None:
    """Bump a named counter. Unknown metric names are accepted and added."""
    with _lock:
        _counters[metric] = _counters.get(metric, 0) + n


health_router = APIRouter(tags=["ops"])


@health_router.get("/health")
def health() -> dict:
    """Always-200 liveness probe. Used by k8s livenessProbe."""
    return {"status": "ok", "uptime_seconds": int(time.time() - _started_at)}


@health_router.get("/ready")
def ready() -> dict:
    """Readiness check — verifies dependencies (DB) when configured."""
    checks: dict[str, str] = {"process": "ok"}
    if settings.use_db:
        try:
            from sqlalchemy import text
            from app.db.engine import get_engine
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as e:  # noqa: BLE001
            checks["database"] = f"fail: {e.__class__.__name__}"
            raise HTTPException(status_code=503, detail=checks)
    return {"status": "ready", "checks": checks}


@health_router.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    """Prometheus exposition format. Scrape with prometheus.yml job."""
    lines: list[str] = [
        "# HELP two_brains_uptime_seconds Process uptime in seconds.",
        "# TYPE two_brains_uptime_seconds gauge",
        f"two_brains_uptime_seconds {int(time.time() - _started_at)}",
        "",
    ]
    for metric, value in sorted(_counters.items()):
        lines += [
            f"# HELP {metric} Cumulative count.",
            f"# TYPE {metric} counter",
            f"{metric} {value}",
            "",
        ]
    return "\n".join(lines)
