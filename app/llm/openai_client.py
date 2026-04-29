"""LLMClient backed by OpenAI's Chat Completions API.

The ``openai`` package is imported lazily so this module is importable
even when the SDK is not installed. Selecting provider="openai" in
planner/critic configuration is the only thing that triggers the import.
"""

from __future__ import annotations

from app.llm.base import LLMClient, LLMProviderError, LLMResponseError

DEFAULT_MODEL: str = "gpt-4o-mini"
DEFAULT_MAX_TOKENS: int = 2048


class OpenAIClient(LLMClient):
    """``LLMClient`` that talks to OpenAI Chat Completions.

    Args:
        api_key: OpenAI API key (``sk-...``).
        model: model id. Defaults to ``gpt-4o-mini`` (cheap + capable).
        default_max_tokens: used when per-call ``max_tokens`` is not given.
        base_url: optional override for Azure OpenAI or other compatible APIs.
    """

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        default_max_tokens: int = DEFAULT_MAX_TOKENS,
        base_url: str | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAIClient requires a non-empty api_key")
        import openai  # noqa: PLC0415 - intentionally lazy

        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._sdk = openai
        self._client = openai.OpenAI(**kwargs)
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
        """Send one request to OpenAI Chat Completions and return the text reply."""
        kwargs: dict = dict(
            model=self._model,
            max_tokens=max_tokens or self._default_max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._client.chat.completions.create(**kwargs)
        except self._sdk.APIError as e:
            raise LLMProviderError(f"OpenAI API error: {e}") from e
        except Exception as e:  # noqa: BLE001
            raise LLMProviderError(f"OpenAI unexpected error: {e}") from e

        choice = (response.choices or [None])[0]
        if choice is None:
            raise LLMResponseError("OpenAI returned no choices")

        text = getattr(choice.message, "content", None) or ""
        if not text:
            raise LLMResponseError("OpenAI returned empty content")
        return text
