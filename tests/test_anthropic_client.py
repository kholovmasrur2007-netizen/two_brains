"""Tests for AnthropicClient.

These tests never touch the network or the real ``anthropic`` SDK.
They replace ``sys.modules['anthropic']`` with a fake module before
constructing the client, so the lazy ``import anthropic`` inside
``AnthropicClient.__init__`` picks up our stub.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest


# ── fake anthropic SDK ─────────────────────────────────────────────────


class _FakeAPIError(Exception):
    """Stand-in for ``anthropic.APIError``."""


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeMessage:
    def __init__(self, content: list[Any]) -> None:
        self.content = content


class _FakeMessagesAPI:
    """Records calls and returns a scripted response."""

    def __init__(self) -> None:
        self.last_call: dict[str, Any] | None = None
        self.next_message: _FakeMessage | None = None
        self.raise_exc: BaseException | None = None

    def create(self, **kwargs: Any) -> _FakeMessage:
        self.last_call = kwargs
        if self.raise_exc is not None:
            raise self.raise_exc
        assert self.next_message is not None, "test must set next_message"
        return self.next_message


class _FakeAnthropicClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.messages = _FakeMessagesAPI()


def _install_fake_anthropic(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """Register a fake ``anthropic`` module and return hooks for the test."""
    module = types.ModuleType("anthropic")
    module.APIError = _FakeAPIError
    module.Anthropic = _FakeAnthropicClient
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return types.SimpleNamespace(module=module, client_cls=_FakeAnthropicClient)


# ── tests ──────────────────────────────────────────────────────────────


def test_client_requires_api_key(monkeypatch) -> None:
    _install_fake_anthropic(monkeypatch)
    from app.llm.anthropic_client import AnthropicClient

    with pytest.raises(ValueError, match="non-empty api_key"):
        AnthropicClient(api_key="")


def test_client_forwards_system_user_and_tuning(monkeypatch) -> None:
    _install_fake_anthropic(monkeypatch)
    from app.llm.anthropic_client import AnthropicClient

    client = AnthropicClient(api_key="sk-test", model="claude-sonnet-4-5")
    client._client.messages.next_message = _FakeMessage([_FakeTextBlock("ok")])

    client.complete(
        system="be precise",
        user="plan the migration",
        temperature=0.2,
        max_tokens=500,
    )

    call = client._client.messages.last_call
    assert call is not None
    assert call["model"] == "claude-sonnet-4-5"
    assert call["system"] == "be precise"
    assert call["messages"] == [{"role": "user", "content": "plan the migration"}]
    assert call["temperature"] == 0.2
    assert call["max_tokens"] == 500


def test_client_returns_text_of_first_content_block(monkeypatch) -> None:
    _install_fake_anthropic(monkeypatch)
    from app.llm.anthropic_client import AnthropicClient

    client = AnthropicClient(api_key="sk-test")
    client._client.messages.next_message = _FakeMessage([_FakeTextBlock("hello world")])

    assert client.complete("sys", "user") == "hello world"


def test_client_wraps_sdk_errors_in_provider_error(monkeypatch) -> None:
    _install_fake_anthropic(monkeypatch)
    from app.llm.anthropic_client import AnthropicClient
    from app.llm.base import LLMProviderError

    client = AnthropicClient(api_key="sk-test")
    client._client.messages.raise_exc = _FakeAPIError("401 Unauthorized")

    with pytest.raises(LLMProviderError, match="401"):
        client.complete("sys", "user")


def test_client_rejects_empty_content(monkeypatch) -> None:
    _install_fake_anthropic(monkeypatch)
    from app.llm.anthropic_client import AnthropicClient
    from app.llm.base import LLMResponseError

    client = AnthropicClient(api_key="sk-test")
    client._client.messages.next_message = _FakeMessage([])

    with pytest.raises(LLMResponseError, match="empty"):
        client.complete("sys", "user")


def test_client_rejects_non_text_block(monkeypatch) -> None:
    _install_fake_anthropic(monkeypatch)
    from app.llm.anthropic_client import AnthropicClient
    from app.llm.base import LLMResponseError

    class _ImageBlock:
        type = "image"

    client = AnthropicClient(api_key="sk-test")
    client._client.messages.next_message = _FakeMessage([_ImageBlock()])

    with pytest.raises(LLMResponseError, match="'image'"):
        client.complete("sys", "user")


def test_get_llm_client_anthropic_requires_env_var(monkeypatch) -> None:
    """Factory must fail fast with a clear error when the API key is missing."""
    import app.config
    from app.llm import get_llm_client
    from app.llm.base import LLMProviderError

    class _Stub:
        anthropic_api_key = None
    monkeypatch.setattr(app.config, "settings", _Stub())

    with pytest.raises(LLMProviderError, match="ANTHROPIC_API_KEY"):
        get_llm_client("anthropic")


def test_anthropic_is_registered_in_brain_factories() -> None:
    """Shallow check: the provider name appears in both registries."""
    from app.brains import (
        registered_critic_providers,
        registered_planner_providers,
    )
    assert "anthropic" in registered_planner_providers()
    assert "anthropic" in registered_critic_providers()
