"""Abstract base for any LLM provider.

Real subclasses will live alongside this file:

    app/llm/openai_client.py    — OpenAIClient(LLMClient)
    app/llm/anthropic_client.py — AnthropicClient(LLMClient)
    app/llm/local_client.py     — LocalClient(LLMClient)

All subclasses obey the same ``complete()`` contract so the brains never
know which one they are talking to.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProviderError(RuntimeError):
    """Provider-level failure: network, auth, rate-limit, server error."""


class LLMResponseError(RuntimeError):
    """The model returned content we could not parse or validate."""


class LLMClient(ABC):
    """Single entry point brains use to talk to any LLM."""

    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> str:
        """Return the model's text response.

        Args:
            system: System prompt (role / instructions).
            user: User prompt (the actual request).
            json_mode: When True, the client should ask the provider for
                strict JSON and raise ``LLMResponseError`` if the string
                is not valid JSON.
            temperature: 0.0 for deterministic output; higher for variety.
            max_tokens: Upper bound on the response length; ``None`` means
                provider default.

        Returns:
            The model's text reply. In ``json_mode`` the caller is
            responsible for ``json.loads`` / ``model_validate_json``.

        Raises:
            LLMProviderError: network / auth / rate-limit errors.
            LLMResponseError: model returned unusable output.
        """
        raise NotImplementedError
