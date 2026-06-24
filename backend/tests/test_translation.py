"""Tests for llm.translate_summary."""

import pytest

import llm
from llm import LLMConfigError, translate_summary

ENGLISH_SUMMARY = (
    "Tan Mei Ling has been diagnosed with cancer. "
    "The treatment plan includes chemotherapy and radiation therapy."
)
MOCK_TRANSLATED = "谭美玲被诊断患有癌症。治疗计划包括化疗和放射治疗。"


# ── early-exit / config guards ────────────────────────────────────────────────


def test_translate_summary_english_returns_unchanged() -> None:
    assert translate_summary("hello", "en") == "hello"


def test_translate_summary_unsupported_lang_raises() -> None:
    with pytest.raises(LLMConfigError, match="Unsupported language"):
        translate_summary("hello", "fr")


# ── happy path (mock _call_llm) ───────────────────────────────────────────────


def test_translate_summary_calls_llm_and_returns_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm, "_call_llm", lambda prompt: MOCK_TRANSLATED)
    assert translate_summary(ENGLISH_SUMMARY, "zh") == MOCK_TRANSLATED


def test_translate_summary_prompt_contains_target_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []
    monkeypatch.setattr(llm, "_call_llm", lambda p: captured.append(p) or "ok")

    translate_summary(ENGLISH_SUMMARY, "zh")
    assert "Simplified Chinese" in captured[0]

    translate_summary(ENGLISH_SUMMARY, "ms")
    assert "Bahasa Melayu" in captured[1]

    translate_summary(ENGLISH_SUMMARY, "ta")
    assert "Tamil" in captured[2]


def test_translate_summary_prompt_contains_source_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []
    monkeypatch.setattr(llm, "_call_llm", lambda p: captured.append(p) or "ok")
    translate_summary(ENGLISH_SUMMARY, "zh")
    assert ENGLISH_SUMMARY in captured[0]


def test_translate_summary_prompt_contains_glossary_terms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []
    monkeypatch.setattr(llm, "_call_llm", lambda p: captured.append(p) or "ok")
    translate_summary(ENGLISH_SUMMARY, "zh")
    # Glossary entries for ZH should appear in the prompt.
    assert "化疗" in captured[0]
    assert "癌症" in captured[0]
