"""Tool-Use API abstraction.

Plain ``LLMClient`` (in ``app.llm``) is text-in / text-out. That is fine
for the planner and critic — they ask for one JSON blob and we are done.
The autonomous executor needs *multi-turn tool use*: the model returns
either a ``tool_use`` block (asking us to run a tool) or a final ``text``
answer, we run the tool, feed the result back in, and call again.

This file defines a small ``AgentClient`` interface that hides each
provider's specific tool-use protocol behind a uniform ``step()`` call.
The agent loop in ``brain3_executor_agent.py`` only ever sees
``AgentStep`` objects.

Two implementations live here:
    * ``MockAgentClient`` — scriptable, never touches the network.
      Tests preload a list of canned ``AgentStep`` responses.
    * ``AnthropicAgentClient`` — real Claude over the Messages API
      with ``tools=...``. Imported lazily to keep the SDK optional.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.types import ToolCall

StepKind = Literal["tool_use", "final"]


class AgentClientError(RuntimeError):
    """Network / auth / API failure while talking to the model."""


class AgentStep(BaseModel):
    """One model turn — either a request to run tools or a final answer."""

    kind: StepKind = Field(..., description="'tool_use' or 'final'.")
    tool_calls: list[ToolCall] = Field(default_factory=list)
    text: str = Field("", description="Final assistant text when kind == 'final'.")
    raw: dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific blob the loop must echo back on the next step.",
    )


class AgentClient(ABC):
    """One round-trip with a tool-use-capable model."""

    @abstractmethod
    def step(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> AgentStep:
        """Send the current message history; return the model's next step.

        Args:
            system: system prompt.
            messages: full conversation history *in the provider's wire format*
                (the loop maintains it so we can simply append). For Anthropic:
                ``[{"role": "user"|"assistant", "content": [...]}, ...]``.
            tools: provider-formatted tool definitions (see ``TOOL_DEFS``).
            max_tokens: upper bound on the response length.

        Raises:
            AgentClientError: any provider-side failure. The brain wrapping
                this client decides whether to fall back or surface the error.
        """
        raise NotImplementedError


# ── Mock implementation ──────────────────────────────────────────────


class MockAgentClient(AgentClient):
    """Scriptable AgentClient — returns pre-canned steps in order.

    Tests do something like::

        client = MockAgentClient(steps=[
            AgentStep(kind="tool_use", tool_calls=[ToolCall(name="write_file", ...)]),
            AgentStep(kind="final", text="done"),
        ])

    Every call records the messages it was given so tests can assert on
    what the loop sent. When the queue is exhausted the client returns a
    canned final-text step (configurable) so loops cannot hang.
    """

    def __init__(
        self,
        steps: list[AgentStep] | None = None,
        default_final_text: str = "(mock client out of scripted steps)",
    ) -> None:
        self._queue: list[AgentStep] = list(steps) if steps else []
        self._default_final_text = default_final_text
        self.calls: list[dict[str, Any]] = []

    def step(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> AgentStep:
        self.calls.append({
            "system": system,
            "messages": list(messages),
            "tools": list(tools),
            "max_tokens": max_tokens,
        })
        if self._queue:
            return self._queue.pop(0)
        return AgentStep(kind="final", text=self._default_final_text)


# ── Anthropic implementation (lazy import) ──────────────────────────


class AnthropicAgentClient(AgentClient):
    """Real Claude tool-use client. Imports the SDK lazily."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        # Defer the SDK import so tests / deterministic runs never pay for it.
        try:
            import anthropic  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover - simple sanity guard
            raise AgentClientError(
                "anthropic SDK not installed; pip install anthropic"
            ) from e
        self._sdk = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def step(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> AgentStep:
        try:
            response = self._sdk.messages.create(
                model=self._model,
                system=system,
                tools=tools,
                messages=messages,
                max_tokens=max_tokens,
            )
        except Exception as e:  # noqa: BLE001 - SDK can raise many subclasses
            raise AgentClientError(
                f"anthropic API failed: {e.__class__.__name__}: {e}"
            ) from e

        # Decode the response into an AgentStep. Anthropic returns a list of
        # content blocks; we collect every tool_use block and any text.
        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []
        assistant_blocks: list[dict[str, Any]] = []

        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "tool_use":
                tool_calls.append(ToolCall(
                    name=block.name,
                    arguments=dict(block.input or {}),
                ))
                assistant_blocks.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
            elif block_type == "text":
                text_parts.append(block.text)
                assistant_blocks.append({"type": "text", "text": block.text})

        if response.stop_reason == "tool_use" or tool_calls:
            return AgentStep(
                kind="tool_use",
                tool_calls=tool_calls,
                text="\n".join(text_parts),
                raw={"assistant_content": assistant_blocks},
            )
        return AgentStep(
            kind="final",
            text="\n".join(text_parts),
            raw={"assistant_content": assistant_blocks},
        )


# ── OpenAI Tool-Use implementation (lazy import) ─────────────────────


class OpenAIAgentClient(AgentClient):
    """Tool-use agent client that talks to OpenAI function calling.

    Uses the same ``AgentStep`` contract so the agent loop is unaware of
    the provider. OpenAI tool_calls live in ``message.tool_calls`` and
    results are returned as role="tool" messages.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        try:
            import openai  # noqa: PLC0415
        except ImportError as e:  # pragma: no cover
            raise AgentClientError(
                "openai SDK not installed; pip install openai"
            ) from e
        self._sdk = openai
        self._client = openai.OpenAI(api_key=api_key)
        self._model = model

    def step(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int = 1024,
    ) -> AgentStep:
        oai_tools = [_to_oai_tool(t) for t in tools]
        oai_msgs  = [{"role": "system", "content": system}] + _to_oai_messages(messages)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=oai_msgs,
                tools=oai_tools or None,  # type: ignore[arg-type]
                max_tokens=max_tokens,
                temperature=0.0,
            )
        except Exception as e:  # noqa: BLE001
            raise AgentClientError(
                f"OpenAI API failed: {e.__class__.__name__}: {e}"
            ) from e

        choice = (response.choices or [None])[0]
        if choice is None:
            raise AgentClientError("OpenAI returned no choices")

        msg = choice.message
        tool_calls: list[ToolCall] = []
        raw_blocks: list[dict[str, Any]] = []

        for tc in msg.tool_calls or []:
            import json as _json
            args = _json.loads(tc.function.arguments or "{}")
            tool_calls.append(ToolCall(name=tc.function.name, arguments=args))
            raw_blocks.append({
                "id": tc.id, "type": "tool_use",
                "name": tc.function.name, "input": args,
            })

        text = msg.content or ""
        if tool_calls:
            return AgentStep(
                kind="tool_use",
                tool_calls=tool_calls,
                text=text,
                raw={"assistant_content": raw_blocks},
            )
        return AgentStep(kind="final", text=text, raw={"assistant_content": []})


def _to_oai_tool(t: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
        },
    }


def _to_oai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten Anthropic-style history to OpenAI Chat format."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        role    = msg.get("role", "user")
        content = msg.get("content", [])
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            continue
        for block in content:
            btype = block.get("type")
            if btype == "text":
                out.append({"role": role, "content": block.get("text", "")})
            elif btype == "tool_result":
                out.append({
                    "role": "tool",
                    "tool_call_id": block.get("tool_use_id", ""),
                    "content": str(block.get("content", "")),
                })
    return out
