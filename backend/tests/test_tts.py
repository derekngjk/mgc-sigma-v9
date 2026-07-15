"""Tests for TTS generation (tts.py) and GET /api/account/reports/{comm_id}/audio."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import account
from app.services import tts
from app.services.llm import LLMConfigError
from app.services.tts import split_sentences, strip_markdown

ENGLISH_TEXT = "Cancer treatment is underway. The care team is here for you."
AUDIO_URL = (
    "https://example.supabase.co/storage/v1/object/public/tts-audio/comm-001/en.mp3"
)
FAKE_MP3 = b"ID3fake"

APPROVED_RECORD = {
    "id": "comm-001",
    "status": "Approved",
    "patient_name": "Tan Mei Ling",
    "ai_summary_text": ENGLISH_TEXT,
    "approved_at": "2024-01-01T00:00:00+00:00",
    "condition_diff": '{"added": [], "removed": [], "ongoing": ["Breast cancer"]}',
    "patients": {
        "patient_name": "Tan Mei Ling",
        "epic_patient_id": "mock-oncology-123",
    },
}


# ── unit tests: strip_markdown ────────────────────────────────────────────────


def test_strip_markdown_removes_headings_bold_bullets() -> None:
    md = "## My Heading\n**Important** note.\n- Item one\n- Item two"
    result = strip_markdown(md)
    assert "##" not in result
    assert "**" not in result
    assert result.startswith("My Heading")
    assert "Important" in result
    assert "Item one" in result


def test_strip_markdown_preserves_plain_text() -> None:
    plain = "No markdown here. Just plain text."
    assert strip_markdown(plain) == plain


# ── unit tests: split_sentences ───────────────────────────────────────────────


def test_split_sentences_basic() -> None:
    text = "First sentence. Second sentence. Third sentence."
    parts = split_sentences(text)
    assert parts == ["First sentence.", "Second sentence.", "Third sentence."]


def test_split_sentences_multiline() -> None:
    text = "Line one. Line two.\nLine three."
    parts = split_sentences(text)
    assert "Line one." in parts
    assert "Line two." in parts
    assert "Line three." in parts


def test_split_sentences_skips_blank_lines() -> None:
    text = "Hello world.\n\nGoodbye world."
    parts = split_sentences(text)
    assert all(p.strip() for p in parts)


# ── unit tests: generate_tts ─────────────────────────────────────────────────


def test_generate_tts_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    class FakeResponse:
        content = FAKE_MP3

    class FakeAudio:
        def create(self, **_kwargs):
            return FakeResponse()

        speech = property(lambda self: self)

    class FakeClient:
        audio = FakeAudio()

    import app.services.tts as _tts

    monkeypatch.setattr(_tts, "generate_tts", lambda text: FAKE_MP3)
    from app.services.tts import generate_tts

    result = generate_tts("Hello world")
    assert result == FAKE_MP3


def test_generate_tts_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Restore real generate_tts to test the key check
    import importlib

    import app.services.tts as _tts

    importlib.reload(_tts)
    from app.services.tts import generate_tts as real_generate_tts

    with pytest.raises(LLMConfigError, match="OPENAI_API_KEY"):
        real_generate_tts("Hello world")


# ── endpoint tests: GET /api/account/reports/{comm_id}/audio ─────────────────


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def stub_report(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        account, "get_portal_user", lambda uid: {"role": "patient", "patient_id": "p1"}
    )
    monkeypatch.setattr(
        account,
        "get_role_report_for_user",
        lambda comm_id, patient_id, role: APPROVED_RECORD,
    )


def test_audio_endpoint_invalid_lang(client: TestClient) -> None:
    resp = client.get("/api/account/reports/comm-001/audio?lang=fr")
    assert resp.status_code == 400


def test_audio_endpoint_report_not_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        account, "get_role_report_for_user", lambda comm_id, pid, role: None
    )
    resp = client.get("/api/account/reports/other-comm/audio?lang=en")
    assert resp.status_code == 404


def test_audio_endpoint_returns_url_and_sentences(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        account, "get_or_create_audio", lambda comm_id, lang, text: AUDIO_URL
    )
    resp = client.get("/api/account/reports/comm-001/audio?lang=en")
    assert resp.status_code == 200
    body = resp.json()
    assert body["url"] == AUDIO_URL
    assert isinstance(body["sentences"], list)
    assert len(body["sentences"]) > 0


# ── service: get_or_create_audio cache behavior ──────────────────────────────


def test_get_or_create_audio_cache_hit_skips_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tts, "get_audio_url", lambda comm_id, lang: AUDIO_URL)
    generated: list[bool] = []
    monkeypatch.setattr(tts, "generate_tts", lambda text: generated.append(True) or b"")

    assert tts.get_or_create_audio("comm-001", "en", "hello") == AUDIO_URL
    assert not generated


def test_get_or_create_audio_generates_and_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tts, "get_audio_url", lambda comm_id, lang: None)
    monkeypatch.setattr(tts, "generate_tts", lambda text: FAKE_MP3)
    monkeypatch.setattr(tts, "upload_audio", lambda comm_id, lang, data: AUDIO_URL)
    set_calls: list[tuple] = []
    monkeypatch.setattr(
        tts, "set_audio_url", lambda c, lg, u: set_calls.append((c, lg, u))
    )

    assert tts.get_or_create_audio("comm-001", "en", "hello") == AUDIO_URL
    assert set_calls == [("comm-001", "en", AUDIO_URL)]
