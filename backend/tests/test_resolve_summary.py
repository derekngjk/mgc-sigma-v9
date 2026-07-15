"""Unit tests for the resolve_summary_text translation helper (services/summaries)."""

import pytest

from app.services import summaries
from app.services.llm import LLMConfigError, LLMError


def test_english_returns_source_unchanged() -> None:
    assert summaries.resolve_summary_text("c1", "Hello", "en") == "Hello"


def test_cache_hit_skips_translation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summaries, "get_translation", lambda cid, lang: "CACHED")
    calls: list[int] = []
    monkeypatch.setattr(
        summaries, "translate_summary", lambda t, lang: calls.append(1) or "X"
    )
    assert summaries.resolve_summary_text("c1", "src", "zh") == "CACHED"
    assert not calls


def test_cache_miss_translates_and_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summaries, "get_translation", lambda cid, lang: None)
    monkeypatch.setattr(summaries, "translate_summary", lambda t, lang: "TRANSLATED")
    stored: list[tuple] = []
    monkeypatch.setattr(
        summaries, "set_translation", lambda c, lang, t: stored.append((c, lang, t))
    )
    assert summaries.resolve_summary_text("c1", "src", "zh") == "TRANSLATED"
    assert stored == [("c1", "zh", "TRANSLATED")]


def test_config_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summaries, "get_translation", lambda cid, lang: None)

    def boom(text: str, lang: str) -> str:
        raise LLMConfigError("no key")

    monkeypatch.setattr(summaries, "translate_summary", boom)
    # The service raises a domain error; the router (not this layer) maps it to HTTP.
    with pytest.raises(LLMConfigError):
        summaries.resolve_summary_text("c1", "src", "zh")


def test_llm_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(summaries, "get_translation", lambda cid, lang: None)

    def boom(text: str, lang: str) -> str:
        raise LLMError("upstream")

    monkeypatch.setattr(summaries, "translate_summary", boom)
    with pytest.raises(LLMError):
        summaries.resolve_summary_text("c1", "src", "zh")
