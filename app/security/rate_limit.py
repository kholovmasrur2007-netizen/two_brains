"""Per-IP rate limiting via slowapi.

Defaults (override via env vars):
    RATE_LIMIT_GLOBAL = "200/minute"   # any authenticated request
    RATE_LIMIT_AUTH   = "10/minute"    # /auth/login attempts
    RATE_LIMIT_RUN    = "30/minute"    # /api/run + /ws/run

Disable everything by setting RATE_LIMIT_DISABLED=true (used by tests).
"""

from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

RATE_LIMIT_GLOBAL: str = os.getenv("RATE_LIMIT_GLOBAL", "200/minute")
RATE_LIMIT_AUTH:   str = os.getenv("RATE_LIMIT_AUTH",   "10/minute")
RATE_LIMIT_RUN:    str = os.getenv("RATE_LIMIT_RUN",    "30/minute")

_DISABLED: bool = os.getenv("RATE_LIMIT_DISABLED", "false").lower() == "true"


def _key_func(request: Request) -> str:
    """Use the user's IP as the rate-limit bucket; fall back to anonymous."""
    return get_remote_address(request) or "anonymous"


# Single limiter instance shared by the whole app — the FastAPI dependency
# system attaches it to ``request.app.state.limiter`` during create_app().
limiter = Limiter(
    key_func=_key_func,
    default_limits=[] if _DISABLED else [RATE_LIMIT_GLOBAL],
    enabled=not _DISABLED,
)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """JSON 429 response with a clear ``Retry-After`` header."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": f"rate limit exceeded: {exc.detail}",
            "retry_after_seconds": getattr(exc, "retry_after", 60),
        },
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
    )
