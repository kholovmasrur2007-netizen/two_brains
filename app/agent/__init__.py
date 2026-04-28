"""Autonomous agent loop and clients.

This package is the bridge between an LLM that supports *tool use*
(structured function calling) and the file-operation tools the sandbox
exposes. Each ``AgentClient`` implementation hides one provider's
tool-use protocol behind the same ``step()`` contract.
"""

from app.agent.client import AgentClient, AgentStep, AgentClientError, MockAgentClient
from app.agent.local import LocalAgentClient
from app.agent.tools_registry import TOOL_DEFS, dispatch_tool

__all__ = [
    "AgentClient",
    "AgentStep",
    "AgentClientError",
    "MockAgentClient",
    "LocalAgentClient",
    "TOOL_DEFS",
    "dispatch_tool",
]
