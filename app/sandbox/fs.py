"""Sandboxed filesystem root for the autonomous agent.

A ``Sandbox`` wraps a single directory (``workspace/`` by default) and
exposes a tiny path-validation API. Every tool the agent uses calls
``Sandbox.resolve()`` first; if the result is not inside the root, the
operation is rejected with ``SandboxError`` *before* any I/O happens.

Threat model (high-security mode):
    * The model is *not* trusted. Treat every path it produces as hostile.
    * Block absolute paths, ``..`` segments, drive-letter prefixes, and
      paths whose resolved form lies outside the root (catches symlinks
      that try to escape).
    * Refuse to ever write outside the root, even if the directory was
      already created on disk.

What the sandbox *does not* do:
    * It does not run shell commands. There is no subprocess surface here.
    * It does not enforce file-size or call-count limits — that lives in
      the agent loop, not here.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class SandboxError(RuntimeError):
    """Raised when a path or operation would escape the sandbox."""


class Sandbox:
    """A directory-rooted filesystem the agent is allowed to touch.

    Args:
        root: directory the agent is confined to. Created if missing.
            The directory must already exist on disk after construction
            (``mkdir(parents=True, exist_ok=True)`` is run for the caller).
    """

    def __init__(self, root: str | Path) -> None:
        self.root: Path = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    # ── path validation ──────────────────────────────────────────────

    def resolve(self, rel_path: str) -> Path:
        """Validate a relative path and return the resolved absolute path.

        Raises:
            SandboxError: if ``rel_path`` is empty, absolute, contains a
                ``..`` segment, or resolves outside the sandbox root.
        """
        if not rel_path or not isinstance(rel_path, str):
            raise SandboxError("path must be a non-empty string")

        # Reject absolute or drive-letter prefixed paths early.
        candidate = Path(rel_path)
        if candidate.is_absolute() or rel_path.startswith(("/", "\\")):
            raise SandboxError(f"absolute paths are not allowed: {rel_path!r}")
        if len(rel_path) >= 2 and rel_path[1] == ":":  # Windows drive prefix
            raise SandboxError(f"drive-letter paths are not allowed: {rel_path!r}")

        # Reject any traversal segment, regardless of platform separator.
        # PurePosixPath normalises both forward and backslash on input but we
        # still split manually to catch ``foo/../bar`` and ``..\\bar``.
        normalised = rel_path.replace("\\", "/")
        if any(part == ".." for part in PurePosixPath(normalised).parts):
            raise SandboxError(f"'..' is not allowed in paths: {rel_path!r}")

        target = (self.root / candidate).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as e:
            raise SandboxError(
                f"path escapes the sandbox: {rel_path!r} -> {target}"
            ) from e
        return target

    # ── relative-form helpers (for nicer log/UI output) ─────────────

    def relative(self, absolute_path: Path) -> str:
        """Return ``absolute_path`` rendered relative to the sandbox root.

        Used for display only — never for security decisions.
        """
        return str(absolute_path.relative_to(self.root)).replace("\\", "/")
