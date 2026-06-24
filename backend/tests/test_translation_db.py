"""Tests for db.get_translation and db.set_translation."""

from unittest.mock import MagicMock, call

import pytest

import db


# ── get_translation ───────────────────────────────────────────────────────────


def test_get_translation_returns_none_when_record_missing(mock_supabase) -> None:
    mock_supabase.table("care_plan_translations").execute.return_value = MagicMock(data=[])
    assert db.get_translation("nonexistent-id", "zh") is None


def test_get_translation_returns_none_when_translations_json_null(mock_supabase) -> None:
    mock_supabase.table("care_plan_translations").execute.return_value = MagicMock(
        data=[{"translations_json": None}]
    )
    assert db.get_translation("comm-1", "zh") is None


def test_get_translation_returns_none_on_cache_miss(mock_supabase) -> None:
    mock_supabase.table("care_plan_translations").execute.return_value = MagicMock(
        data=[{"translations_json": {"ms": "Pelan rawatan..."}}]
    )
    assert db.get_translation("comm-1", "zh") is None


def test_get_translation_returns_cached_value(mock_supabase) -> None:
    mock_supabase.table("care_plan_translations").execute.return_value = MagicMock(
        data=[{"translations_json": {"zh": "谭美玲被诊断患有癌症。"}}]
    )
    assert db.get_translation("comm-1", "zh") == "谭美玲被诊断患有癌症。"


def test_get_translation_handles_json_string(mock_supabase) -> None:
    """translations_json may arrive as a JSON string rather than a parsed dict."""
    import json

    mock_supabase.table("care_plan_translations").execute.return_value = MagicMock(
        data=[{"translations_json": json.dumps({"ta": "புற்றுநோய்"})}]
    )
    assert db.get_translation("comm-1", "ta") == "புற்றுநோய்"


# ── set_translation ───────────────────────────────────────────────────────────


def test_set_translation_writes_new_language(mock_supabase) -> None:
    mock_supabase.table("care_plan_translations").execute.side_effect = [
        MagicMock(data=[{"translations_json": {}}]),   # select
        MagicMock(data=[{"id": "comm-1"}]),            # update
    ]
    db.set_translation("comm-1", "zh", "谭美玲被诊断患有癌症。")
    mock_supabase.table("care_plan_translations").update.assert_called_once_with(
        {"translations_json": {"zh": "谭美玲被诊断患有癌症。"}}
    )


def test_set_translation_preserves_existing_languages(mock_supabase) -> None:
    existing = {"ms": "Pelan rawatan telah bermula."}
    mock_supabase.table("care_plan_translations").execute.side_effect = [
        MagicMock(data=[{"translations_json": existing}]),  # select
        MagicMock(data=[{"id": "comm-1"}]),                 # update
    ]
    db.set_translation("comm-1", "zh", "谭美玲被诊断患有癌症。")
    mock_supabase.table("care_plan_translations").update.assert_called_once_with(
        {"translations_json": {"ms": "Pelan rawatan telah bermula.", "zh": "谭美玲被诊断患有癌症。"}}
    )


def test_set_translation_noop_when_record_missing(mock_supabase) -> None:
    mock_supabase.table("care_plan_translations").execute.return_value = MagicMock(data=[])
    db.set_translation("nonexistent-id", "zh", "text")
    mock_supabase.table("care_plan_translations").update.assert_not_called()
