"""JWT authentication module.

Exports:
    router          — FastAPI router with /auth/login and /auth/register
    get_current_user — FastAPI dependency for protected endpoints
    get_optional_user — same but returns None when auth is disabled
    create_first_admin — creates admin/admin on first startup if no users exist
"""

from app.auth.core import (
    create_first_admin,
    get_current_user,
    get_optional_user,
    router,
)

__all__ = [
    "router",
    "get_current_user",
    "get_optional_user",
    "create_first_admin",
]
