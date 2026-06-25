"""Tests for TTS generation (tts.py) and GET /api/family/{fid}/member/{mid}/audio."""

import pytest
from fastapi.testclient import TestClient

import main as _main
from llm import LLMConfigError
from main import app
from tts import split_sentences, strip_markdown

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

    import tts as _tts

    monkeypatch.setattr(_tts, "generate_tts", lambda text: FAKE_MP3)
    from tts import generate_tts

    result = generate_tts("Hello world")
    assert result == FAKE_MP3


def test_generate_tts_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    import tts as _tts

    # Restore real generate_tts to test the key check
    import importlib

    importlib.reload(_tts)
    from tts import generate_tts as real_generate_tts

    with pytest.raises(LLMConfigError, match="OPENAI_API_KEY"):
        real_generate_tts("Hello world")


# ── endpoint tests: GET /api/family/{fid}/member/{mid}/audio ─────────────────


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def stub_family_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_main, "get_family_summary", lambda fid, mid: APPROVED_RECORD)


def test_audio_endpoint_invalid_lang(client: TestClient) -> None:
    resp = client.get("/api/family/fid-1/member/mid-1/audio?lang=fr")
    assert resp.status_code == 400


def test_audio_endpoint_invalid_fid_mid(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_main, "get_family_summary", lambda fid, mid: None)
    resp = client.get("/api/family/bad-fid/member/bad-mid/audio?lang=en")
    assert resp.status_code == 404


def test_audio_endpoint_cache_hit_skips_generation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_main, "get_audio_url", lambda comm_id, lang: AUDIO_URL)
    generate_called: list[bool] = []
    monkeypatch.setattr(
        _main, "generate_tts", lambda text: generate_called.append(True) or b""
    )

    resp = client.get("/api/family/fid-1/member/mid-1/audio?lang=en")
    assert resp.status_code == 200
    body = resp.json()
    assert body["url"] == AUDIO_URL
    assert isinstance(body["sentences"], list)
    assert len(body["sentences"]) > 0
    assert not generate_called


def test_audio_endpoint_cache_miss_generates_and_caches(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_main, "get_audio_url", lambda comm_id, lang: None)
    monkeypatch.setattr(_main, "generate_tts", lambda text: FAKE_MP3)
    monkeypatch.setattr(_main, "upload_audio", lambda comm_id, lang, data: AUDIO_URL)
    set_calls: list[tuple] = []
    monkeypatch.setattr(
        _main, "set_audio_url", lambda c, lg, u: set_calls.append((c, lg, u))
    )

    resp = client.get("/api/family/fid-1/member/mid-1/audio?lang=en")
    assert resp.status_code == 200
    body = resp.json()
    assert body["url"] == AUDIO_URL
    assert isinstance(body["sentences"], list)
    assert set_calls == [("comm-001", "en", AUDIO_URL)]
