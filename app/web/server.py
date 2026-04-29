"""FastAPI server exposing the two_brains pipeline over HTTP + WebSocket.

REST surface:

    POST /auth/login             get JWT token
    POST /auth/register          create user (admin only)
    GET  /auth/status            whether auth is enabled
    GET  /                       single-page UI (static/index.html)
    GET  /api/providers          available planner / critic / executor names
    GET  /api/history            list of stored task summaries  [protected]
    GET  /api/tasks/{task_id}    full FinalResult for a task    [protected]
    POST /api/run                run a task, return FinalResult [protected]

WebSocket:

    /ws/run                      run a task with live phase events [protected]

Auth is opt-in: set AUTH_ENABLED=true in .env to require JWT tokens.
When disabled (default) all endpoints are freely accessible so fresh
installs work out of the box.

Storage: JSON file by default.  Set USE_DB=true to switch to SQLite
(or PostgreSQL via DATABASE_URL=postgresql+psycopg2://...).
"""

from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from slowapi.errors import RateLimitExceeded

from app.auth import create_first_admin, get_current_user, router as auth_router
from app.brains import (
    build_critic,
    build_executor,
    build_per_user_executor,
    build_planner,
    registered_critic_providers,
    registered_executor_providers,
    registered_planner_providers,
)
from app.config import settings
from app.core.logger import get_logger
from app.core.orchestrator import TwoBrainOrchestrator
from app.memory.store import MemoryStore
from app.security.audit import AuditLogger, _client_ip, audit_router
from app.security.health import health_router, increment as metric_inc
from app.security.quotas import DailyQuotaExceeded, check_and_record_quota
from app.security.rate_limit import RATE_LIMIT_RUN, limiter, rate_limit_handler
from app.types import FinalResult, TaskInput
from app.utils.helpers import new_id

_log = get_logger(__name__)

_STATIC_DIR: Path = Path(__file__).parent / "static"
_INDEX_FILE: Path = _STATIC_DIR / "index.html"


# ── request / response shapes ─────────────────────────────────────────


class RunRequest(BaseModel):
    """Body of POST /api/run and the first WS message on /ws/run."""

    prompt: str = Field(..., min_length=1, description="The user task prompt.")
    constraints: list[str] = Field(default_factory=list, description="Hard constraints.")
    execute: bool = Field(False, description="Run Brain 3 if the plan is ready.")
    planner_provider: str | None = Field(
        None,
        description="Override PLANNER_PROVIDER for this run only.",
    )
    critic_provider: str | None = Field(
        None,
        description="Override CRITIC_PROVIDER for this run only.",
    )
    executor_provider: str | None = Field(
        None,
        description="Override EXECUTOR_PROVIDER for this run only.",
    )


class TaskSummary(BaseModel):
    """One row of GET /api/history."""

    task_id: str
    prompt: str
    score: int | None = None
    judgement: str | None = None
    ready_for_execution: bool | None = None
    executed: bool = False


class ProviderDefaults(BaseModel):
    """Configured default provider for each brain kind."""

    planner: str
    critic: str
    executor: str


class ProvidersResponse(BaseModel):
    """Body of GET /api/providers."""

    planner: list[str]
    critic: list[str]
    executor: list[str]
    defaults: ProviderDefaults


# ── shared state ──────────────────────────────────────────────────────


def _build_memory():
    """Single shared store for the lifetime of the server."""
    if settings.use_db:
        from app.db.store import SQLMemoryStore
        return SQLMemoryStore()
    return MemoryStore(path=settings.memory_path)


def create_app(memory=None) -> FastAPI:
    """Build the FastAPI app. Tests pass an isolated store."""
    app = FastAPI(
        title="two_brains",
        description="Planner → Critic → Executor pipeline with live streaming.",
        version="2.0.0",
    )

    store = memory if memory is not None else _build_memory()
    app.state.memory = store

    # Ensure all tables exist when DB mode is on. Idempotent — safe to
    # call on every restart. SQLMemoryStore already does this in its
    # constructor, but the audit + quota tables are needed even when
    # the test fixture supplies a non-DB store.
    if settings.use_db:
        try:
            from app.db.engine import init_db
            init_db()
        except Exception as e:  # noqa: BLE001
            _log.warning("init_db failed at startup: %s", e)

    # Rate limiting (slowapi). The middleware adds /Retry-After/ headers and
    # 429s; the handler converts the slowapi exception to a JSON body.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    # Auth router (login / register / me / status)
    app.include_router(auth_router)
    # Audit log REST surface (admin-only)
    app.include_router(audit_router)
    # Ops endpoints (/health, /ready, /metrics)
    app.include_router(health_router)

    # Bootstrap first admin when auth + DB are enabled
    create_first_admin()

    # ── static UI ────────────────────────────────────────────────────

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        if not _INDEX_FILE.exists():
            raise HTTPException(
                status_code=500,
                detail=f"index.html missing under {_STATIC_DIR}",
            )
        return FileResponse(_INDEX_FILE)

    # ── REST: providers (public) ─────────────────────────────────────

    @app.get("/api/providers", response_model=ProvidersResponse)
    def providers() -> ProvidersResponse:
        return ProvidersResponse(
            planner=registered_planner_providers(),
            critic=registered_critic_providers(),
            executor=registered_executor_providers(),
            defaults=ProviderDefaults(
                planner=settings.planner_provider,
                critic=settings.critic_provider,
                executor=settings.executor_provider,
            ),
        )

    # ── REST: per-user quota usage (protected) ───────────────────────

    @app.get("/api/usage")
    def usage(user=Depends(get_current_user)) -> dict:
        """Return today's quota usage and remaining budget for the caller."""
        from app.security.quotas import DAILY_TASK_QUOTA, usage_today
        used = usage_today(user.username)
        return {
            "username": user.username,
            "used_today": used,
            "daily_quota": DAILY_TASK_QUOTA,
            "remaining": max(0, DAILY_TASK_QUOTA - used),
        }

    # ── REST: history (protected) ────────────────────────────────────

    @app.get("/api/history", response_model=list[TaskSummary])
    def history(_user=Depends(get_current_user)) -> list[TaskSummary]:
        rows: list[TaskSummary] = []
        for tid in store.known_task_ids():
            task = store.get_task(tid)
            critique = store.get_critique(tid)
            result = store.get_result(tid)
            rows.append(TaskSummary(
                task_id=tid,
                prompt=textwrap.shorten(task.prompt, 80, placeholder="...") if task else "",
                score=critique.overall_score if critique else None,
                judgement=critique.final_judgement if critique else None,
                ready_for_execution=result.ready_for_execution if result else None,
                executed=bool(result and result.execution is not None),
            ))
        return rows

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str, _user=Depends(get_current_user)) -> FinalResult:
        result = store.get_result(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"no result for task_id={task_id}")
        return result

    # ── REST: synchronous run (protected, rate-limited, quota'd) ─────

    @app.post("/api/run", response_model=FinalResult)
    @limiter.limit(RATE_LIMIT_RUN)
    def run(
        request: Request,
        req: RunRequest,
        user=Depends(get_current_user),
    ) -> FinalResult:
        metric_inc("two_brains_requests_total")
        ip = _client_ip(request)

        # Daily quota check (returns 429 with Retry-After-like detail).
        try:
            check_and_record_quota(user.username)
        except DailyQuotaExceeded as e:
            metric_inc("two_brains_quota_exceeded_total")
            AuditLogger.log(
                action="run", username=user.username, ip=ip,
                status="quota_exceeded", details=str(e),
            )
            raise HTTPException(status_code=429, detail=str(e)) from None

        try:
            orchestrator = _make_orchestrator(req, store, username=user.username)
        except ValueError as e:
            AuditLogger.log(action="run", username=user.username, ip=ip,
                            status="error", details=str(e))
            raise HTTPException(status_code=400, detail=str(e)) from None

        task = TaskInput(id=new_id(), prompt=req.prompt, constraints=list(req.constraints))
        try:
            result = orchestrator.run(task, execute=req.execute)
        except Exception as e:  # noqa: BLE001
            metric_inc("two_brains_runs_failed_total")
            AuditLogger.log(action="run", username=user.username, ip=ip,
                            target=task.id, status="error",
                            details=f"{e.__class__.__name__}: {e}")
            raise HTTPException(status_code=500, detail=str(e)) from None

        metric_inc("two_brains_runs_total")
        AuditLogger.log(
            action="run", username=user.username, ip=ip, target=task.id,
            status="ok",
            details=f"executor={req.executor_provider} ready={result.ready_for_execution}",
        )
        return result

    # ── WebSocket: streamed run ──────────────────────────────────────

    @app.websocket("/ws/run")
    async def ws_run(ws: WebSocket) -> None:
        await ws.accept()
        try:
            payload = await ws.receive_json()
        except WebSocketDisconnect:
            return
        except Exception as e:  # noqa: BLE001
            await _send_error(ws, f"invalid first message: {e}")
            await ws.close()
            return

        # Auth check: if auth is enabled, first message must carry a token.
        from app.auth.core import _AUTH_ENABLED, _decode_token, _get_user_row
        username: str | None = None
        if _AUTH_ENABLED:
            token = payload.get("token") or ""
            username = _decode_token(token)
            if not username or (settings.use_db and _get_user_row(username) is None):
                await _send_error(ws, "Unauthorized — include valid JWT as 'token' field")
                await ws.close()
                return

        try:
            req = RunRequest.model_validate(payload)
        except Exception as e:  # noqa: BLE001 - pydantic.ValidationError, etc.
            await _send_error(ws, f"invalid request body: {e}")
            await ws.close()
            return

        try:
            orchestrator = _make_orchestrator(req, store, username=username)
        except ValueError as e:
            await _send_error(ws, str(e))
            await ws.close()
            return

        task = TaskInput(id=new_id(), prompt=req.prompt, constraints=list(req.constraints))

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def on_event(event: dict[str, Any]) -> None:
            # Hopped from the worker thread back onto the event loop.
            loop.call_soon_threadsafe(queue.put_nowait, event)

        async def pump() -> None:
            """Drain the event queue into the WebSocket until the run finishes."""
            while True:
                event = await queue.get()
                try:
                    await ws.send_json(event)
                except WebSocketDisconnect:
                    return
                if event.get("type") == "done":
                    return

        # Run the orchestrator in a thread so its sync work doesn't block
        # the event loop. Phase events flow through the queue → pump → WS.
        run_task = asyncio.create_task(asyncio.to_thread(
            orchestrator.run, task, execute=req.execute, on_event=on_event,
        ))
        pump_task = asyncio.create_task(pump())

        try:
            await asyncio.gather(run_task, pump_task)
        except Exception as e:  # noqa: BLE001
            await _send_error(ws, f"pipeline error: {e.__class__.__name__}: {e}")
        finally:
            try:
                await ws.close()
            except RuntimeError:
                pass  # already closed by the client

    return app


# ── internal helpers ──────────────────────────────────────────────────


def _make_orchestrator(
    req: RunRequest,
    store,
    username: str | None = None,
) -> TwoBrainOrchestrator:
    """Build a TwoBrainOrchestrator honouring per-request provider overrides.

    When a username is supplied, agent-style executors are sandboxed to
    ``workspace/<username>/`` so concurrent users cannot read or
    overwrite each other's generated files.
    """
    planner = build_planner(req.planner_provider) if req.planner_provider else None
    critic = build_critic(req.critic_provider) if req.critic_provider else None
    executor = (
        build_per_user_executor(req.executor_provider, username)
        if req.executor_provider
        else None
    )
    return TwoBrainOrchestrator(
        planner=planner,
        critic=critic,
        executor=executor,
        memory=store,
    )


async def _send_error(ws: WebSocket, message: str) -> None:
    """Send an error event over the WebSocket if it is still open."""
    try:
        await ws.send_json({"type": "error", "message": message})
    except (WebSocketDisconnect, RuntimeError):
        pass


# Module-level app for uvicorn (``uvicorn app.web.server:app``).
app = create_app()


# ── HTML fallback ─────────────────────────────────────────────────────


@app.exception_handler(404)
async def _not_found(_request, exc):  # type: ignore[no-untyped-def]
    """Return JSON 404s for /api/* paths, HTML index otherwise (SPA-friendly)."""
    return JSONResponse(status_code=404, content={"detail": getattr(exc, "detail", "not found")})
