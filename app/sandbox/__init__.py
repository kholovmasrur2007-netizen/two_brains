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

from app.sandbox.fs import Sandbox, SandboxError

__all__ = ["Sandbox", "SandboxError"]
