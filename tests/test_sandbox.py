"""Tests for the filesystem sandbox — both path safety and tool ops.

These tests are the security spine of the autonomous agent. Every path
the model could pick MUST go through ``Sandbox.resolve``; if any of
these tests start passing for a path that escapes the root, the agent
just gained the ability to touch the rest of the host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.sandbox.fs import Sandbox, SandboxError
from app.sandbox.tools import edit_file, grep, list_dir, read_file, write_file


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    """A fresh sandbox rooted at a per-test temp directory."""
    return Sandbox(tmp_path / "ws")


# ── path safety ──────────────────────────────────────────────────────


def test_sandbox_creates_root_if_missing(tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    assert not root.exists()
    sb = Sandbox(root)
    assert sb.root.exists() and sb.root.is_dir()


def test_resolve_accepts_a_simple_relative_path(sandbox: Sandbox) -> None:
    p = sandbox.resolve("notes.txt")
    assert p.parent == sandbox.root


def test_resolve_accepts_nested_paths(sandbox: Sandbox) -> None:
    p = sandbox.resolve("src/util/helpers.py")
    assert sandbox.relative(p) == "src/util/helpers.py"


@pytest.mark.parametrize("bad", [
    "/etc/passwd",
    "C:/Windows/System32/cmd.exe",
    "C:\\Users\\x",
])
def test_resolve_rejects_absolute_paths(sandbox: Sandbox, bad: str) -> None:
    with pytest.raises(SandboxError):
        sandbox.resolve(bad)


@pytest.mark.parametrize("bad", [
    "../escape.txt",
    "..\\escape.txt",
    "subdir/../../escape.txt",
    "a/b/../../../escape.txt",
])
def test_resolve_rejects_traversal_segments(sandbox: Sandbox, bad: str) -> None:
    with pytest.raises(SandboxError):
        sandbox.resolve(bad)


def test_resolve_rejects_empty_or_non_string(sandbox: Sandbox) -> None:
    with pytest.raises(SandboxError):
        sandbox.resolve("")
    with pytest.raises(SandboxError):
        sandbox.resolve(None)  # type: ignore[arg-type]


# ── read_file / write_file round-trip ────────────────────────────────


def test_write_then_read_round_trip(sandbox: Sandbox) -> None:
    write_file(sandbox, "hello.txt", "Hi, agent!")
    assert read_file(sandbox, "hello.txt") == "Hi, agent!"


def test_write_creates_parent_directories(sandbox: Sandbox) -> None:
    write_file(sandbox, "src/util/h.py", "x = 1\n")
    assert (sandbox.root / "src" / "util" / "h.py").is_file()


def test_read_file_missing_raises(sandbox: Sandbox) -> None:
    with pytest.raises(SandboxError):
        read_file(sandbox, "nope.txt")


def test_write_file_rejects_traversal(sandbox: Sandbox) -> None:
    with pytest.raises(SandboxError):
        write_file(sandbox, "../escape.txt", "hostile")


def test_read_file_rejects_directory(sandbox: Sandbox) -> None:
    (sandbox.root / "subdir").mkdir()
    with pytest.raises(SandboxError):
        read_file(sandbox, "subdir")


def test_write_file_rejects_oversize_content(sandbox: Sandbox) -> None:
    huge = "x" * 300_000
    with pytest.raises(SandboxError):
        write_file(sandbox, "big.txt", huge)


# ── edit_file ────────────────────────────────────────────────────────


def test_edit_file_replaces_unique_match(sandbox: Sandbox) -> None:
    write_file(sandbox, "a.py", "def foo():\n    return 1\n")
    edit_file(sandbox, "a.py", "return 1", "return 42")
    assert "return 42" in read_file(sandbox, "a.py")


def test_edit_file_refuses_when_old_string_missing(sandbox: Sandbox) -> None:
    write_file(sandbox, "a.py", "x = 1\n")
    with pytest.raises(SandboxError):
        edit_file(sandbox, "a.py", "y = 2", "y = 3")


def test_edit_file_refuses_when_old_string_not_unique(sandbox: Sandbox) -> None:
    write_file(sandbox, "a.py", "x = 1\nx = 1\n")
    with pytest.raises(SandboxError) as exc:
        edit_file(sandbox, "a.py", "x = 1", "x = 2")
    assert "not unique" in str(exc.value)


def test_edit_file_rejects_missing_file(sandbox: Sandbox) -> None:
    with pytest.raises(SandboxError):
        edit_file(sandbox, "nope.py", "old", "new")


# ── list_dir ─────────────────────────────────────────────────────────


def test_list_dir_returns_entries_sorted(sandbox: Sandbox) -> None:
    write_file(sandbox, "b.txt", "")
    write_file(sandbox, "a.txt", "")
    (sandbox.root / "z_dir").mkdir()
    listing = list_dir(sandbox, ".")
    assert listing.split("\n") == ["a.txt", "b.txt", "z_dir/"]


def test_list_dir_rejects_traversal(sandbox: Sandbox) -> None:
    with pytest.raises(SandboxError):
        list_dir(sandbox, "..")


# ── grep ─────────────────────────────────────────────────────────────


def test_grep_finds_matches_across_files(sandbox: Sandbox) -> None:
    write_file(sandbox, "a.py", "import os\nimport sys\n")
    write_file(sandbox, "b.py", "print('hello')\n")
    out = grep(sandbox, "import")
    assert "a.py:1:" in out
    assert "a.py:2:" in out
    assert "b.py" not in out


def test_grep_returns_empty_on_no_match(sandbox: Sandbox) -> None:
    write_file(sandbox, "a.py", "x = 1\n")
    assert grep(sandbox, "nothing-matches") == "(no matches)"


def test_grep_rejects_invalid_regex(sandbox: Sandbox) -> None:
    write_file(sandbox, "a.py", "x")
    with pytest.raises(SandboxError):
        grep(sandbox, "[")
