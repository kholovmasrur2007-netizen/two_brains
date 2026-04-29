"""Filesystem sandbox for the autonomous agent.

Every file operation the agent runs goes through ``Sandbox.resolve()`` so
paths cannot escape the configured root. The sandbox refuses:

    * absolute paths
    * any segment containing ``..``
    * symlinks that point outside the root (resolved with ``Path.resolve``)
    * paths whose resolved form lies outside the root

Nothing here imports an LLM SDK — the sandbox is pure stdlib so unit
tests run instantly.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.sandbox.fs import Sandbox, SandboxError

__all__ = ["Sandbox", "SandboxError", "user_workspace"]


# Strict allowlist for the per-user directory name. Reject anything that
# could break out of the parent workspace via traversal or odd OS chars.
_SAFE_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def user_workspace(base: str | Path, username: str) -> Path:
    """Return ``base/<username>`` after validating ``username`` is filesystem-safe.

    Raises:
        SandboxError: if the username contains anything outside
        ``[A-Za-z0-9_.-]`` or is longer than 64 chars or is a traversal
        token (``.`` or ``..``). This is a defence-in-depth check;
        auth-layer usernames already pass.
    """
    if not username or username in (".", "..") or not _SAFE_USERNAME_RE.match(username):
        raise SandboxError(f"unsafe username: {username!r}")
    return Path(base) / username
