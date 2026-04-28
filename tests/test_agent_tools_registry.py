"""Tests for the tool dispatcher used by the agent loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.tools_registry import TOOL_DEFS, dispatch_tool
from app.sandbox.fs import Sandbox
from app.sandbox.tools import write_file
from app.types import ToolCall


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path / "ws")


def test_tool_defs_match_documented_surface() -> None:
    """If you add a tool, both the schema list and the dispatcher must agree."""
    schema_names = {t["name"] for t in TOOL_DEFS}
    assert schema_names == {"read_file", "write_file", "edit_file", "list_dir", "grep"}
    for t in TOOL_DEFS:
        assert "description" in t and t["description"]
        assert "input_schema" in t


def test_dispatch_write_file_returns_ok(sandbox: Sandbox) -> None:
    res = dispatch_tool(
        ToolCall(name="write_file", arguments={"path": "a.txt", "content": "hi"}),
        sandbox,
    )
    assert res.status == "ok"
    assert "wrote" in res.output
    assert (sandbox.root / "a.txt").read_text(encoding="utf-8") == "hi"


def test_dispatch_read_file_returns_ok(sandbox: Sandbox) -> None:
    write_file(sandbox, "a.txt", "hello")
    res = dispatch_tool(
        ToolCall(name="read_file", arguments={"path": "a.txt"}),
        sandbox,
    )
    assert res.status == "ok"
    assert res.output == "hello"


def test_dispatch_unknown_tool_returns_error(sandbox: Sandbox) -> None:
    res = dispatch_tool(ToolCall(name="rm_minus_rf", arguments={}), sandbox)
    assert res.status == "error"
    assert "unknown tool" in res.error


def test_dispatch_traversal_returns_error(sandbox: Sandbox) -> None:
    """Even if the model invents a hostile path, the dispatcher must refuse."""
    res = dispatch_tool(
        ToolCall(name="write_file", arguments={"path": "../escape", "content": "x"}),
        sandbox,
    )
    assert res.status == "error"
    assert ".." in res.error


def test_dispatch_missing_required_arg_returns_error(sandbox: Sandbox) -> None:
    res = dispatch_tool(ToolCall(name="read_file", arguments={}), sandbox)
    assert res.status == "error"
    assert "path" in res.error


def test_dispatch_wrong_arg_type_returns_error(sandbox: Sandbox) -> None:
    res = dispatch_tool(
        ToolCall(name="write_file", arguments={"path": "a.txt", "content": 123}),
        sandbox,
    )
    assert res.status == "error"
