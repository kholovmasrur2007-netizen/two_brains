"""File-operation tools the autonomous agent is allowed to call.

Each tool is a plain Python function that:
    1. Validates its arguments through ``Sandbox.resolve``
    2. Performs the operation
    3. Returns a small string the model can read back

Failures raise ``SandboxError`` so the agent loop can surface them to
the model as a structured tool-result error (the model then decides how
to recover, instead of the loop crashing).

What is intentionally NOT exposed to the agent:
    * shell / subprocess (high-security mode = files only)
    * network I/O (no ``urllib``, no ``requests``)
    * arbitrary path globs that could enumerate the host filesystem

A future "medium-security" mode can add a ``run_python`` tool wrapped in
a subprocess sandbox; today's surface is deliberately minimal.
"""

from __future__ import annotations

import re
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
    """Create or overwrite ``path`` with ``content``. Parent dirs are created."""
    if not isinstance(content, str):
        raise SandboxError("write_file: content must be a string")
    if len(content.encode("utf-8")) > _MAX_FILE_BYTES:
        raise SandboxError(
            f"refusing to write more than {_MAX_FILE_BYTES} bytes"
        )
    target = sandbox.resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
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
