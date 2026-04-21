"""LLMClient backed by Anthropic's Claude API.

The ``anthropic`` package is imported lazily inside ``__init__`` so this
module stays importable even when the SDK is not installed. Only users
who actually select the anthropic provider pay the import cost.
"""

from __future__ import annotations

from app.llm.base import LLMClient, LLMProviderError, LLMResponseError

DEFAULT_MODEL: str = "claude-sonnet-4-5"
DEFAULT_MAX_TOKENS: int = 2048


class AnthropicClient(LLMClient):
    """Concrete ``LLMClient`` that sends requests to Claude.

    Args:
        api_key: Anthropic API key (``sk-ant-...``). Required; empty raises.
        model: Claude model id. Defaults to the current Sonnet.
        default_max_tokens: used when a per-call ``max_tokens`` is not given.

    Notes:
        Anthropic's Messages API has no formal ``json_mode`` flag; our
        system prompt tells the model to produce JSON-only, which is
        reliable enough given the brains also fall back to deterministic
        logic on parse failure. The ``json_mode`` argument is accepted
        for interface compatibility but not forwarded to the SDK.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        default_max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        if not api_key:
            raise ValueError("AnthropicClient requires a non-empty api_key")
        # Lazy import: keeps the `anthropic` package optional at project level.
        import anthropic

        self._sdk = anthropic  # retained for exception classes
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._default_max_tokens = default_max_tokens

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        """Send one request to Claude and return the text reply."""
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens or self._default_max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                temperature=temperature,
            )
        except self._sdk.APIError as e:
            raise LLMProviderError(f"Anthropic API error: {e}") from e

        content = getattr(message, "content", None)
        if not content:
            raise LLMResponseError("Anthropic returned an empty content list")

        first = content[0]
        block_type = getattr(first, "type", None)
        if block_type != "text":
            raise LLMResponseError(
                f"Anthropic returned content of type {block_type!r}, expected 'text'"
            )

        return getattr(first, "text", "")
