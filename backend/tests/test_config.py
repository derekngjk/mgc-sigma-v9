"""Tests for the centralized Settings config and path anchors."""

import pytest

from app.config import MOCK_DATA_DIR, SYNTHEA_DIR, Settings


def test_defaults_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("LLM_PROVIDER", "IMAGE_PROVIDER", "FRONTEND_ORIGIN", "SUPABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    settings = Settings()
    assert settings.llm_provider == "anthropic"
    assert settings.image_provider == "openai"
    assert settings.frontend_origin == "http://localhost:5173"
    assert settings.supabase_url == ""


def test_reads_env_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    settings = Settings()
    assert settings.llm_provider == "openai"
    assert settings.supabase_url == "https://proj.supabase.co"


def test_path_anchors_point_into_backend() -> None:
    assert MOCK_DATA_DIR.name == "mock_data"
    assert MOCK_DATA_DIR.parent.name == "backend"
    assert SYNTHEA_DIR.name == "SyntheticPatientRecords"
