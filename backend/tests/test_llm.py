"""Tests for the LLM provider abstraction: factory dispatch and error handling."""

from unittest.mock import MagicMock

import pytest

from app.services.llm import LLMConfigError, LLMError, get_provider
from app.services.llm.providers import AnthropicProvider, GoogleProvider, OpenAIProvider


def test_get_provider_uses_configured_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert isinstance(get_provider(), OpenAIProvider)


def test_get_provider_explicit_name_overrides_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert isinstance(get_provider("anthropic"), AnthropicProvider)
    assert isinstance(get_provider("google"), GoogleProvider)


def test_get_provider_unknown_raises_config_error() -> None:
    with pytest.raises(LLMConfigError, match="Unknown LLM_PROVIDER"):
        get_provider("mistral")


def test_provider_missing_key_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMConfigError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider().complete("hello")


def test_provider_api_failure_wrapped_as_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    import anthropic

    fake_client = MagicMock()
    fake_client.messages.create.side_effect = RuntimeError("network down")
    monkeypatch.setattr(anthropic, "Anthropic", lambda **_: fake_client)

    with pytest.raises(LLMError, match="Anthropic completion failed"):
        AnthropicProvider().complete("hello")
