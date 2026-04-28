"""Types specific to the autonomous-agent execution path.

The agent loop produces a *trace*: one entry per turn the model takes,
recording the tool it asked for, the arguments it passed, and what came
back. This sits *inside* an ``ExecutionOutput.executor_notes`` field
when the agent is the active executor backend.

These types are deliberately small — the agent loop already enforces
the schema, so callers don't need rich validation here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ToolStatus = Literal["ok", "error"]


class ToolCall(BaseModel):
    """A single tool invocation the model asked the agent loop to perform."""

    name: str = Field(..., description="Tool name (e.g. 'read_file').")
    arguments: dict = Field(default_factory=dict, description="JSON arguments.")


class ToolResult(BaseModel):
    """Outcome of running a ToolCall against the sandbox."""

    name: str = Field(..., description="Echoes the tool name the model invoked.")
    status: ToolStatus = Field(..., description="ok = tool succeeded, error = sandbox refused or raised.")
    output: str = Field("", description="Stringified tool output (truncated for the model).")
    error: str = Field("", description="Error message when status == 'error'.")


class AgentTraceEntry(BaseModel):
    """One round-trip of the agent loop: model thought + tool call + result."""

    iteration: int = Field(..., ge=1)
    tool_call: ToolCall
    tool_result: ToolResult


class AgentTrace(BaseModel):
    """Full record of every tool the agent invoked while executing a plan."""

    iterations: int = Field(0, ge=0, description="Number of model→tool round-trips taken.")
    entries: list[AgentTraceEntry] = Field(default_factory=list)
    final_text: str = Field("", description="Final non-tool message the model returned.")
    halted_reason: str = Field(
        "",
        description="If the loop stopped before the model finished: why.",
    )
