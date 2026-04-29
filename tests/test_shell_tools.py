"""Tests for sandbox shell-execution tools: run_python and run_pytest."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.sandbox.fs import Sandbox, SandboxError
from app.sandbox.tools import run_pytest, run_python, write_file


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path / "ws")


# ── run_python ───────────────────────────────────────────────────────


def test_run_python_executes_script_and_captures_stdout(sandbox: Sandbox) -> None:
    write_file(sandbox, "hello.py", 'print("hello from agent")\n')
    out = run_python(sandbox, "hello.py")
    assert "exit_code=0" in out
    assert "hello from agent" in out


def test_run_python_captures_nonzero_exit(sandbox: Sandbox) -> None:
    write_file(sandbox, "fail.py", "raise SystemExit(42)\n")
    out = run_python(sandbox, "fail.py")
    assert "exit_code=42" in out


def test_run_python_captures_stderr(sandbox: Sandbox) -> None:
    write_file(sandbox, "err.py", "import sys; sys.stderr.write('oops\\n')\n")
    out = run_python(sandbox, "err.py")
    assert "oops" in out


def test_run_python_rejects_non_py_file(sandbox: Sandbox) -> None:
    write_file(sandbox, "notes.txt", "hello")
    with pytest.raises(SandboxError, match=".py"):
        run_python(sandbox, "notes.txt")


def test_run_python_rejects_missing_file(sandbox: Sandbox) -> None:
    with pytest.raises(SandboxError):
        run_python(sandbox, "nope.py")


def test_run_python_rejects_traversal(sandbox: Sandbox) -> None:
    with pytest.raises(SandboxError):
        run_python(sandbox, "../escape.py")


# ── run_pytest ───────────────────────────────────────────────────────


def test_run_pytest_passes_on_green_test(sandbox: Sandbox) -> None:
    write_file(sandbox, "test_sample.py", "def test_ok():\n    assert 1 + 1 == 2\n")
    out = run_pytest(sandbox, "test_sample.py")
    assert "exit_code=0" in out
    assert "passed" in out


def test_run_pytest_fails_on_red_test(sandbox: Sandbox) -> None:
    write_file(sandbox, "test_bad.py", "def test_fail():\n    assert False\n")
    out = run_pytest(sandbox, "test_bad.py")
    assert "exit_code=1" in out
    assert "failed" in out


def test_run_pytest_rejects_traversal(sandbox: Sandbox) -> None:
    with pytest.raises(SandboxError):
        run_pytest(sandbox, "..")


# ── tools_registry integration ───────────────────────────────────────


def test_registry_dispatches_run_python(sandbox: Sandbox) -> None:
    from app.agent.tools_registry import dispatch_tool
    from app.types import ToolCall

    write_file(sandbox, "hi.py", 'print("registry ok")\n')
    res = dispatch_tool(ToolCall(name="run_python", arguments={"path": "hi.py"}), sandbox)
    assert res.status == "ok"
    assert "registry ok" in res.output


def test_registry_dispatches_run_pytest(sandbox: Sandbox) -> None:
    from app.agent.tools_registry import dispatch_tool
    from app.types import ToolCall

    write_file(sandbox, "test_x.py", "def test_pass():\n    pass\n")
    res = dispatch_tool(ToolCall(name="run_pytest", arguments={"path": "test_x.py"}), sandbox)
    assert res.status == "ok"
    assert "passed" in res.output
