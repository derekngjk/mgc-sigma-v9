"""Tests for the ?lang= query param on GET /api/family/{fid}/member/{mid}
and the legacy GET /api/communications/{id} endpoint."""

import pytest
from fastapi.testclient import TestClient

import main as _main
from app.services.llm import LLMConfigError, LLMError
from main import app

ENGLISH_TEXT = "Cancer treatment is underway. The care team is here for you."
ZH_TEXT = "癌症治疗正在进行中。护理团队随时为您服务。"

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


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# ── /api/family/{fid}/member/{mid} ────────────────────────────────────────────


@pytest.fixture(autouse=True)
def stub_get_family_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_main, "get_family_summary", lambda fid, mid: APPROVED_RECORD)
    monkeypatch.setattr(_main, "get_image_url", lambda cid: None)


def test_family_member_default_lang_returns_english(client: TestClient) -> None:
    resp = client.get("/api/family/fid-1/member/mid-1")
    assert resp.status_code == 200
    assert resp.json()["ai_summary_text"] == ENGLISH_TEXT


def test_family_member_lang_en_returns_english(client: TestClient) -> None:
    resp = client.get("/api/family/fid-1/member/mid-1?lang=en")
    assert resp.status_code == 200
    assert resp.json()["ai_summary_text"] == ENGLISH_TEXT


def test_family_member_invalid_lang_returns_400(client: TestClient) -> None:
    resp = client.get("/api/family/fid-1/member/mid-1?lang=fr")
    assert resp.status_code == 400


def test_family_member_cache_hit_returns_cached_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_main, "get_translation", lambda comm_id, lang: ZH_TEXT)
    translate_called = []
    monkeypatch.setattr(
        _main, "translate_summary", lambda t, _lang: translate_called.append(1) or ""
    )

    resp = client.get("/api/family/fid-1/member/mid-1?lang=zh")
    assert resp.status_code == 200
    assert resp.json()["ai_summary_text"] == ZH_TEXT
    assert not translate_called


def test_family_member_cache_miss_translates_and_caches(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_main, "get_translation", lambda comm_id, lang: None)
    monkeypatch.setattr(_main, "translate_summary", lambda text, lang: ZH_TEXT)
    set_calls: list[tuple] = []
    monkeypatch.setattr(
        _main, "set_translation", lambda c, lg, t: set_calls.append((c, lg, t))
    )

    resp = client.get("/api/family/fid-1/member/mid-1?lang=zh")
    assert resp.status_code == 200
    assert resp.json()["ai_summary_text"] == ZH_TEXT
    assert set_calls == [("comm-001", "zh", ZH_TEXT)]


def test_family_member_translate_llm_error_returns_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_main, "get_translation", lambda comm_id, lang: None)
    monkeypatch.setattr(
        _main,
        "translate_summary",
        lambda t, _lang: (_ for _ in ()).throw(LLMError("upstream failed")),
    )

    resp = client.get("/api/family/fid-1/member/mid-1?lang=ms")
    assert resp.status_code == 502


def test_family_member_translate_config_error_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_main, "get_translation", lambda comm_id, lang: None)
    monkeypatch.setattr(
        _main,
        "translate_summary",
        lambda t, _lang: (_ for _ in ()).throw(LLMConfigError("key missing")),
    )

    resp = client.get("/api/family/fid-1/member/mid-1?lang=ta")
    assert resp.status_code == 503


# ── /api/communications/{id} (legacy endpoint) ───────────────────────────────


@pytest.fixture
def stub_get_communication(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_main, "get_communication", lambda comm_id: APPROVED_RECORD)


def test_legacy_endpoint_cache_miss_translates(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, stub_get_communication: None
) -> None:
    monkeypatch.setattr(_main, "get_translation", lambda comm_id, lang: None)
    monkeypatch.setattr(_main, "translate_summary", lambda text, lang: ZH_TEXT)
    set_calls: list[tuple] = []
    monkeypatch.setattr(
        _main, "set_translation", lambda c, lg, t: set_calls.append((c, lg, t))
    )

    resp = client.get("/api/communications/comm-001?lang=zh")
    assert resp.status_code == 200
    assert resp.json()["ai_summary_text"] == ZH_TEXT
    assert set_calls == [("comm-001", "zh", ZH_TEXT)]


def test_legacy_endpoint_invalid_lang_returns_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, stub_get_communication: None
) -> None:
    resp = client.get("/api/communications/comm-001?lang=jp")
    assert resp.status_code == 400
