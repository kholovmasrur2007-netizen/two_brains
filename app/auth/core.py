"""JWT-based authentication for the two_brains web API.

Flow:
    1. POST /auth/register  — create user (admin only, or first-run)
    2. POST /auth/login     — returns {"access_token": "...", "token_type": "bearer"}
    3. Every protected endpoint calls Depends(get_current_user)

Security choices:
    * HS256 JWT, secret from SECRET_KEY env var (auto-generated if missing).
    * bcrypt password hashing via passlib.
    * Token expiry: 24 hours by default (AUTH_TOKEN_EXPIRE_HOURS).
    * When AUTH_ENABLED=false (default) all endpoints allow anonymous access
      so a fresh install works out of the box without any setup.

First-run:
    If AUTH_ENABLED=true and no users exist in the DB, the server
    auto-creates admin/admin and logs a prominent warning. Change the
    password immediately via POST /auth/register (admin-only endpoint).
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from app.config import settings
from app.core.logger import get_logger

_log = get_logger(__name__)

# ── config ───────────────────────────────────────────────────────────

_AUTH_ENABLED: bool = os.getenv("AUTH_ENABLED", "false").lower() == "true"
_SECRET_KEY:   str  = os.getenv("SECRET_KEY") or secrets.token_hex(32)
_ALGORITHM:    str  = "HS256"
_EXPIRE_HOURS: int  = int(os.getenv("AUTH_TOKEN_EXPIRE_HOURS", "24"))

if not os.getenv("SECRET_KEY") and _AUTH_ENABLED:
    _log.warning(
        "SECRET_KEY not set — using a random key. "
        "All tokens will be invalidated on server restart. "
        "Set SECRET_KEY in your .env file for stable sessions."
    )

# ── password hashing ─────────────────────────────────────────────────

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


# ── JWT helpers ───────────────────────────────────────────────────────

def _create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": username, "exp": expire},
        _SECRET_KEY, algorithm=_ALGORITHM,
    )


def _decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


# ── DB helpers ────────────────────────────────────────────────────────

def _get_user_row(username: str):
    if not settings.use_db:
        return None
    from app.db.engine import UserRow, get_session
    with get_session() as s:
        return s.get(UserRow, username)


def _create_user_row(username: str, password_hash: str, is_admin: bool = False) -> None:
    from app.db.engine import UserRow, get_session
    with get_session() as s:
        existing = s.get(UserRow, username)
        if existing:
            raise ValueError(f"User {username!r} already exists")
        s.add(UserRow(
            username=username,
            password_hash=password_hash,
            is_admin="true" if is_admin else "false",
        ))
        s.commit()


def _user_count() -> int:
    from app.db.engine import UserRow, get_session
    with get_session() as s:
        return s.query(UserRow).count()


# ── FastAPI OAuth2 bearer ─────────────────────────────────────────────

_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


class CurrentUser(BaseModel):
    username: str
    is_admin: bool = False


async def get_current_user(token: str | None = Depends(_oauth2)) -> CurrentUser:
    """Dependency: require a valid JWT. 401 if missing or invalid."""
    if not _AUTH_ENABLED:
        return CurrentUser(username="anonymous", is_admin=True)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username = _decode_token(token)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    row = _get_user_row(username)
    if row is None and settings.use_db:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    is_admin = getattr(row, "is_admin", "false") == "true" if row else True
    return CurrentUser(username=username, is_admin=is_admin)


async def get_optional_user(
    token: str | None = Depends(_oauth2),
) -> CurrentUser | None:
    """Dependency: return user if authenticated, None otherwise."""
    if not _AUTH_ENABLED:
        return CurrentUser(username="anonymous", is_admin=True)
    if not token:
        return None
    username = _decode_token(token)
    if not username:
        return None
    row = _get_user_row(username)
    is_admin = getattr(row, "is_admin", "false") == "true" if row else False
    return CurrentUser(username=username, is_admin=is_admin)


# ── router ────────────────────────────────────────────────────────────

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    username:     str
    expires_in:   int  # seconds


class RegisterRequest(BaseModel):
    username: str
    password: str


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """Exchange username+password for a JWT access token."""
    if not _AUTH_ENABLED:
        return TokenResponse(
            access_token=_create_token(form.username),
            username=form.username,
            expires_in=_EXPIRE_HOURS * 3600,
        )

    row = _get_user_row(form.username)
    if row is None or not verify_password(form.password, row.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=_create_token(form.username),
        username=form.username,
        expires_in=_EXPIRE_HOURS * 3600,
    )


@router.post("/register", status_code=201)
def register(
    req: RegisterRequest,
    current: CurrentUser = Depends(get_current_user),
) -> dict:
    """Create a new user. Requires admin rights."""
    if not current.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    if len(req.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    try:
        _create_user_row(req.username, hash_password(req.password))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return {"username": req.username, "created": True}


@router.get("/me")
def me(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return current


@router.get("/status")
def auth_status() -> dict:
    """Public endpoint — returns whether auth is enabled."""
    return {"auth_enabled": _AUTH_ENABLED}


# ── first-run bootstrap ───────────────────────────────────────────────

def create_first_admin() -> None:
    """If auth is enabled and no users exist, create admin/admin."""
    if not _AUTH_ENABLED:
        return
    try:
        count = _user_count()
    except Exception:  # noqa: BLE001 - DB not ready, skip
        return
    if count == 0:
        _log.warning(
            "AUTH_ENABLED=true but no users in DB. "
            "Creating default admin/admin — CHANGE THIS PASSWORD IMMEDIATELY."
        )
        try:
            _create_user_row("admin", hash_password("admin"), is_admin=True)
        except Exception:  # noqa: BLE001 - race condition, another process beat us
            pass
