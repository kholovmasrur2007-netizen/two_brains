"""MockLLMClient — deterministic LLM stand-in for tests and offline dev.

It never touches the network. Tests set ``responses`` to script what the
"model" should say; every call to ``complete()`` returns the next queued
response, or ``default`` once the queue is exhausted.
"""

from __future__ import annotations

from app.llm.base import LLMClient


class MockLLMClient(LLMClient):
    """An ``LLMClient`` that returns pre-configured responses in order.

    Example:
        >>> client = MockLLMClient(responses=['{"ok": true}'], default="")
        >>> client.complete("sys", "user")
        '{"ok": true}'
        >>> client.complete("sys", "user")   # queue exhausted -> default
        ''

    Every call is recorded in ``self.calls`` so tests can assert what the
    brain under test sent to the model.
    """

    def __init__(
        self,
        responses: list[str] | None = None,
        default: str = "",
    ) -> None:
        self._queue: list[str] = list(responses) if responses else []
        self._default: str = default
        self.calls: list[dict[str, object]] = []

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        """Record the call and pop the next queued response (or default)."""
        self.calls.append({
            "system": system,
            "user": user,
            "json_mode": json_mode,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        if self._queue:
            return self._queue.pop(0)
        return self._default
