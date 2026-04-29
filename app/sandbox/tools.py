"""File-operation + execution tools the autonomous agent is allowed to call.

Each tool is a plain Python function that:
    1. Validates its arguments through ``Sandbox.resolve``
    2. Performs the operation
    3. Returns a small string the model can read back

Failures raise ``SandboxError`` so the agent loop can surface them to
the model as a structured tool-result error (the model then decides how
to recover, instead of the loop crashing).

Shell-execution surface (medium-security):
    * ``run_python`` — runs a .py file inside the sandbox with the same
      interpreter that launched the server; 30s timeout.
    * ``run_pytest`` — runs pytest on a path inside the sandbox; 60s timeout.
    Both operations are executed with cwd=sandbox.root so relative imports
    resolve correctly, and stdout+stderr are captured and returned to the
    model (truncated at 8 KB so the context window stays manageable).

What is intentionally NOT exposed to the agent:
    * arbitrary shell commands (no sh/bash/cmd, no curl, no pip install)
    * network I/O from agent tools (no urllib, no requests)
    * deletion of files (no rm / unlink via tools)
    * arbitrary path globs that could enumerate the host filesystem

A future "medium-security" mode can add a ``run_python`` tool wrapped in
a subprocess sandbox; today's surface is deliberately minimal.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from app.sandbox.fs import Sandbox, SandboxError

# Limits — kept conservative to prevent the agent from filling the disk
# or producing megabyte-sized results that blow up the model's context.
_MAX_FILE_BYTES: int = 200_000        # ~200 KB per read or write
_MAX_LIST_ENTRIES: int = 200          # cap list_dir output
_MAX_GREP_MATCHES: int = 50           # cap grep output


# ── read_file ────────────────────────────────────────────────────────


def read_file(sandbox: Sandbox, path: str) -> str:
    """Return the text contents of ``path`` (UTF-8) inside the sandbox."""
    target = sandbox.resolve(path)
    if not target.exists():
        raise SandboxError(f"file not found: {path}")
    if not target.is_file():
        raise SandboxError(f"not a regular file: {path}")
    if target.stat().st_size > _MAX_FILE_BYTES:
        raise SandboxError(
            f"file too large to read ({target.stat().st_size} bytes; "
            f"max {_MAX_FILE_BYTES})"
        )
    return target.read_text(encoding="utf-8", errors="replace")


# ── write_file ───────────────────────────────────────────────────────


def write_file(sandbox: Sandbox, path: str, content: str) -> str:
    """Create or overwrite ``path`` with ``content``. Parent dirs are created.

    Refuses early when:
        * ``content`` is not a string
        * encoded size exceeds ``_MAX_FILE_BYTES`` (200 KB)
        * the underlying filesystem doesn't have enough free space —
          this is the safety net for runaway agents that could otherwise
          fill the host disk.
    """
    if not isinstance(content, str):
        raise SandboxError("write_file: content must be a string")
    encoded_size = len(content.encode("utf-8"))
    if encoded_size > _MAX_FILE_BYTES:
        raise SandboxError(
            f"refusing to write more than {_MAX_FILE_BYTES} bytes"
        )
    target = sandbox.resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Disk-space pre-flight. shutil.disk_usage works on Windows and POSIX.
    try:
        free = shutil.disk_usage(sandbox.root).free
    except OSError as e:  # pragma: no cover - extremely rare
        raise SandboxError(f"write_file: disk_usage failed: {e}") from e
    if encoded_size > free:
        raise SandboxError(
            f"Недостаточно места: нужно {encoded_size} байт, "
            f"свободно {free} байт"
        )
    target.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {sandbox.relative(target)}"


# ── edit_file ────────────────────────────────────────────────────────


def edit_file(sandbox: Sandbox, path: str, old_string: str, new_string: str) -> str:
    """Replace the unique occurrence of ``old_string`` with ``new_string``.

    Mirrors the Edit-tool contract Claude Code uses: the match must be
    unique, and the file must already exist. Saves the agent from
    accidentally rewriting whole files when it meant to tweak a line.
    """
    if not old_string:
        raise SandboxError("edit_file: old_string must not be empty")
    target = sandbox.resolve(path)
    if not target.exists() or not target.is_file():
        raise SandboxError(f"edit_file: file not found: {path}")
    text = target.read_text(encoding="utf-8")
    occurrences = text.count(old_string)
    if occurrences == 0:
        raise SandboxError(f"edit_file: old_string not found in {path}")
    if occurrences > 1:
        raise SandboxError(
            f"edit_file: old_string is not unique in {path} "
            f"(found {occurrences} occurrences) — make it more specific"
        )
    new_text = text.replace(old_string, new_string, 1)
    if len(new_text.encode("utf-8")) > _MAX_FILE_BYTES:
        raise SandboxError(
            f"edit_file: result would exceed {_MAX_FILE_BYTES} bytes"
        )
    target.write_text(new_text, encoding="utf-8")
    return f"edited {sandbox.relative(target)} (1 replacement)"


# ── list_dir ─────────────────────────────────────────────────────────


def list_dir(sandbox: Sandbox, path: str = ".") -> str:
    """Return a plain-text listing of ``path`` (one entry per line)."""
    target = sandbox.resolve(path) if path not in ("", ".") else sandbox.root
    if not target.exists():
        raise SandboxError(f"list_dir: directory not found: {path}")
    if not target.is_dir():
        raise SandboxError(f"list_dir: not a directory: {path}")
    entries: list[str] = []
    for child in sorted(target.iterdir()):
        suffix = "/" if child.is_dir() else ""
        entries.append(child.name + suffix)
        if len(entries) >= _MAX_LIST_ENTRIES:
            entries.append(f"... (truncated at {_MAX_LIST_ENTRIES} entries)")
            break
    if not entries:
        return "(empty directory)"
    return "\n".join(entries)


# ── grep ─────────────────────────────────────────────────────────────


def grep(sandbox: Sandbox, pattern: str, path: str = ".") -> str:
    """Return lines matching ``pattern`` (regex) under ``path`` (file or dir)."""
    if not pattern:
        raise SandboxError("grep: pattern must not be empty")
    try:
        regex = re.compile(pattern)
    except re.error as e:
        raise SandboxError(f"grep: invalid regex {pattern!r}: {e}") from e

    target = sandbox.resolve(path) if path not in ("", ".") else sandbox.root
    if not target.exists():
        raise SandboxError(f"grep: path not found: {path}")

    matches: list[str] = []
    files: list[Path] = [target] if target.is_file() else [
        p for p in target.rglob("*") if p.is_file()
    ]
    for file in files:
        try:
            for lineno, line in enumerate(
                file.read_text(encoding="utf-8", errors="replace").splitlines(),
                start=1,
            ):
                if regex.search(line):
                    rel = sandbox.relative(file)
                    matches.append(f"{rel}:{lineno}: {line.rstrip()}")
                    if len(matches) >= _MAX_GREP_MATCHES:
                        matches.append(f"... (truncated at {_MAX_GREP_MATCHES} matches)")
                        return "\n".join(matches)
        except (OSError, UnicodeDecodeError):
            continue
    if not matches:
        return "(no matches)"
    return "\n".join(matches)


# ── run_python ───────────────────────────────────────────────────────


_RUN_TIMEOUT_PYTHON: int = 30   # seconds
_RUN_TIMEOUT_PYTEST: int = 60
_RUN_OUTPUT_LIMIT:   int = 8_000   # chars returned to the model


def run_python(sandbox: Sandbox, path: str) -> str:
    """Execute a Python file inside the sandbox and return its output.

    Runs with ``cwd=sandbox.root`` so relative imports resolve. Uses the
    same Python interpreter that launched the server. Stdout and stderr
    are captured together and returned (truncated at 8 KB).

    Raises:
        SandboxError: file not found, not a .py, path escape, or timeout.
    """
    target = sandbox.resolve(path)
    if not target.exists():
        raise SandboxError(f"run_python: file not found: {path}")
    if not target.is_file():
        raise SandboxError(f"run_python: not a file: {path}")
    if target.suffix.lower() != ".py":
        raise SandboxError(f"run_python: only .py files allowed, got: {path}")

    return _run_subprocess(
        [sys.executable, str(target)],
        cwd=sandbox.root,
        timeout=_RUN_TIMEOUT_PYTHON,
        label=f"python {path}",
    )


# ── run_pytest ──────────────────────────────────────────────────────


def run_pytest(sandbox: Sandbox, path: str = ".") -> str:
    """Run pytest on a path inside the sandbox and return the output.

    Args:
        path: file or directory relative to the sandbox root.
              Pass "." (default) to run the whole sandbox.

    Raises:
        SandboxError: path escapes the sandbox or timeout exceeded.
    """
    target = sandbox.resolve(path) if path not in ("", ".") else sandbox.root
    if not target.exists():
        raise SandboxError(f"run_pytest: path not found: {path}")

    return _run_subprocess(
        [sys.executable, "-m", "pytest", "-v", "--tb=short", str(target)],
        cwd=sandbox.root,
        timeout=_RUN_TIMEOUT_PYTEST,
        label=f"pytest {path}",
    )


# ── shared subprocess helper ────────────────────────────────────────


def _run_subprocess(
    cmd: list[str],
    *,
    cwd: Path,
    timeout: int,
    label: str,
) -> str:
    """Run ``cmd`` with captured output. Returns combined stdout+stderr."""
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            # Never let the child inherit the parent's environment variables
            # that might contain secrets (ANTHROPIC_API_KEY, DATABASE_URL …).
            env={
                "PATH": _safe_path(),
                "PYTHONPATH": str(cwd),
                # Needed on Windows for Python to find itself.
                "SYSTEMROOT": _env_val("SYSTEMROOT"),
                "TEMP": _env_val("TEMP"),
                "TMP":  _env_val("TMP"),
            },
        )
    except subprocess.TimeoutExpired:
        raise SandboxError(
            f"{label}: timed out after {timeout}s — increase timeout or simplify the script"
        )
    except FileNotFoundError as e:
        raise SandboxError(f"{label}: interpreter not found — {e}") from e

    out = (result.stdout or "") + (result.stderr or "")
    header = f"exit_code={result.returncode}\n"
    body = out if len(out) <= _RUN_OUTPUT_LIMIT else out[: _RUN_OUTPUT_LIMIT - 32] + "\n... (truncated)"
    return header + body


def _safe_path() -> str:
    """Return a minimal PATH that lets python/pytest find themselves."""
    import os
    return os.environ.get("PATH", "")


def _env_val(key: str) -> str:
    """Safely pull an env var (empty string if unset)."""
    import os
    return os.environ.get(key, "")
