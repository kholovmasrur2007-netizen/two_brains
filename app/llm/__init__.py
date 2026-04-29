"""LLM clients.

No provider is wired in yet. This package exposes the abstract ``LLMClient``
contract and a ``get_llm_client`` factory stub. When a real provider is
added (OpenAI, Anthropic, a local model, …), register it inside
``get_llm_client`` so the rest of the codebase never imports the provider
directly.
"""

from __future__ import annotations

from app.llm.base import LLMClient, LLMProviderError, LLMResponseError

__all__ = [
    "LLMClient",
    "LLMProviderError",
    "LLMResponseError",
    "get_llm_client",
]


def get_llm_client(provider: str) -> LLMClient:
    """Return an ``LLMClient`` for the given provider name.

    Registered providers:
        ``mock``      - always available; for tests and offline dev.
        ``anthropic`` - Claude API. Requires ``ANTHROPIC_API_KEY``.

    Provider-specific imports are lazy (inside each branch) so optional
    heavy SDKs are only loaded when the user actually selects them.
    """
    if provider == "mock":
        from app.llm.mock import MockLLMClient
        return MockLLMClient()
    if provider == "anthropic":
        from app import config
        from app.llm.anthropic_client import AnthropicClient
        api_key = config.settings.anthropic_api_key
        if not api_key:
            raise LLMProviderError(
                "ANTHROPIC_API_KEY is not set - export it or put it in your .env file"
            )
        return AnthropicClient(api_key=api_key)
    if provider == "openai":
        from app import config
        from app.llm.openai_client import OpenAIClient
        api_key = config.settings.openai_api_key
        if not api_key:
            raise LLMProviderError(
                "OPENAI_API_KEY is not set - export it or put it in your .env file"
            )
        return OpenAIClient(api_key=api_key, model=config.settings.openai_model)
    raise NotImplementedError(
        f"LLM provider {provider!r} is not available yet. "
        "See app/llm/__init__.py for how to register one."
    )
