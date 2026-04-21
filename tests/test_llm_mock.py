"""Tests for MockLLMClient and the get_llm_client factory."""

from __future__ import annotations

import pytest

from app.llm import LLMClient, get_llm_client
from app.llm.mock import MockLLMClient


def test_mock_returns_queued_responses_in_order() -> None:
    client = MockLLMClient(responses=["a", "b", "c"])
    assert client.complete("sys", "user") == "a"
    assert client.complete("sys", "user") == "b"
    assert client.complete("sys", "user") == "c"


def test_mock_falls_back_to_default_when_queue_empty() -> None:
    client = MockLLMClient(responses=["once"], default="fallback")
    assert client.complete("s", "u") == "once"
    assert client.complete("s", "u") == "fallback"
    assert client.complete("s", "u") == "fallback"


def test_mock_records_every_call() -> None:
    client = MockLLMClient(default="ok")
    client.complete("sys1", "user1", json_mode=True, temperature=0.5, max_tokens=100)

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["system"] == "sys1"
    assert call["user"] == "user1"
    assert call["json_mode"] is True
    assert call["temperature"] == 0.5
    assert call["max_tokens"] == 100


def test_mock_is_an_llm_client() -> None:
    """The mock must satisfy the LLMClient contract."""
    assert isinstance(MockLLMClient(), LLMClient)


def test_get_llm_client_returns_mock() -> None:
    client = get_llm_client("mock")
    assert isinstance(client, MockLLMClient)


def test_get_llm_client_unknown_provider_raises() -> None:
    with pytest.raises(NotImplementedError) as exc:
        get_llm_client("nonexistent-provider")
    assert "nonexistent-provider" in str(exc.value)
