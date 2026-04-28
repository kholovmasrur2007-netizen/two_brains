"""Single source of truth for the agent's tool surface.

Defines:
    * ``TOOL_DEFS`` — Anthropic Tool-Use schema list (passed to the API).
    * ``dispatch_tool`` — runs a named tool against the sandbox and returns
      a ``ToolResult``. Sandbox failures are caught and surfaced as
      ``status="error"`` so the agent loop never crashes on a bad call.

Adding a new tool requires editing exactly two places:
    1. Append a JSON-schema entry to ``TOOL_DEFS``.
    2. Add a branch to ``dispatch_tool`` that calls the implementation.
"""

from __future__ import annotations

from typing import Any

from app.sandbox.fs import Sandbox, SandboxError
from app.sandbox.tools import edit_file, grep, list_dir, read_file, write_file
from app.types import ToolCall, ToolResult

# Anthropic Tool-Use schema (https://docs.anthropic.com/en/docs/agents-and-tools/tool-use).
# Descriptions are read by the model — be precise about what each tool does and what
# it does NOT do. Required-arg lists keep the model from hallucinating optional flags.
TOOL_DEFS: list[dict[str, Any]] = [
    {
        "name": "read_file",
        "description": (
            "Read the UTF-8 text contents of a file inside the sandbox. "
            "Returns the file body. Fails if the path escapes the sandbox or the file is missing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the sandbox root."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a file inside the sandbox. Parent directories are created "
            "automatically. Use this for new files; use edit_file to tweak existing ones."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Path relative to the sandbox root."},
                "content": {"type": "string", "description": "Full text content to write."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Replace the unique occurrence of `old_string` with `new_string` in an existing file. "
            "Fails if `old_string` is missing or appears more than once — make it specific."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path":       {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "list_dir",
        "description": (
            "List the entries of a directory inside the sandbox. Returns a newline-separated list. "
            "Pass '.' (or omit) for the sandbox root."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path; defaults to the sandbox root."},
            },
            "required": [],
        },
    },
    {
        "name": "grep",
        "description": (
            "Search for a regex pattern across a file or directory inside the sandbox. "
            "Returns matching `path:line: text` rows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Python regular expression."},
                "path":    {"type": "string", "description": "File or directory; defaults to the sandbox root."},
            },
            "required": ["pattern"],
        },
    },
]


def dispatch_tool(call: ToolCall, sandbox: Sandbox) -> ToolResult:
    """Run ``call`` against ``sandbox`` and return a structured ToolResult.

    SandboxError is caught and surfaced as ``status="error"`` so the
    agent loop can hand the failure back to the model without crashing.
    Any other exception is treated the same way — better to let the
    model decide how to recover than to abort the whole run.
    """
    args = call.arguments or {}
    try:
        if call.name == "read_file":
            output = read_file(sandbox, _str_arg(args, "path"))
        elif call.name == "write_file":
            output = write_file(sandbox, _str_arg(args, "path"), _str_arg(args, "content"))
        elif call.name == "edit_file":
            output = edit_file(
                sandbox,
                _str_arg(args, "path"),
                _str_arg(args, "old_string"),
                _str_arg(args, "new_string"),
            )
        elif call.name == "list_dir":
            output = list_dir(sandbox, args.get("path", "."))
        elif call.name == "grep":
            output = grep(sandbox, _str_arg(args, "pattern"), args.get("path", "."))
        else:
            return ToolResult(
                name=call.name, status="error",
                error=f"unknown tool: {call.name!r}",
            )
    except SandboxError as e:
        return ToolResult(name=call.name, status="error", error=str(e))
    except Exception as e:  # noqa: BLE001 - never crash the loop on a bad arg
        return ToolResult(
            name=call.name, status="error",
            error=f"{e.__class__.__name__}: {e}",
        )

    return ToolResult(name=call.name, status="ok", output=output)


def _str_arg(args: dict, key: str) -> str:
    """Pull a string argument out of the model's input dict, or fail loudly."""
    if key not in args:
        raise SandboxError(f"missing required argument: {key!r}")
    val = args[key]
    if not isinstance(val, str):
        raise SandboxError(f"argument {key!r} must be a string, got {type(val).__name__}")
    return val
