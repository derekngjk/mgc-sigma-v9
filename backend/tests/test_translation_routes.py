"""Tests for the ?lang= query param on GET /api/account/reports/{comm_id}."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import account
from app.services import summaries
from app.services.llm import LLMConfigError, LLMError

ENGLISH_TEXT = "Cancer treatment is underway. The care team is here for you."
ZH_TEXT = "癌症治疗正在进行中。护理团队随时为您服务。"

APPROVED_RECORD = {
    "id": "comm-001",
    "status": "Approved",
    "patient_name": "Tan Mei Ling",
    "ai_summary_text": ENGLISH_TEXT,
    "approved_at": "2024-01-01T00:00:00+00:00",
    "condition_diff": '{"added": [], "removed": [], "ongoing": ["Breast cancer"]}',
    "image_url": None,
}


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
    monkeypatch.setattr(account, "mark_report_read", lambda uid, comm_id: None)


def test_default_lang_returns_english(client: TestClient) -> None:
    resp = client.get("/api/account/reports/comm-001")
    assert resp.status_code == 200
    assert resp.json()["ai_summary_text"] == ENGLISH_TEXT


def test_lang_en_returns_english(client: TestClient) -> None:
    resp = client.get("/api/account/reports/comm-001?lang=en")
    assert resp.status_code == 200
    assert resp.json()["ai_summary_text"] == ENGLISH_TEXT


def test_invalid_lang_returns_400(client: TestClient) -> None:
    resp = client.get("/api/account/reports/comm-001?lang=fr")
    assert resp.status_code == 400


def test_cache_hit_returns_cached_text(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(summaries, "get_translation", lambda comm_id, lang: ZH_TEXT)
    translate_called: list[int] = []
    monkeypatch.setattr(
        summaries, "translate_summary", lambda t, _lang: translate_called.append(1) or ""
    )

    resp = client.get("/api/account/reports/comm-001?lang=zh")
    assert resp.status_code == 200
    assert resp.json()["ai_summary_text"] == ZH_TEXT
    assert not translate_called


def test_cache_miss_translates_and_caches(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(summaries, "get_translation", lambda comm_id, lang: None)
    monkeypatch.setattr(summaries, "translate_summary", lambda text, lang: ZH_TEXT)
    set_calls: list[tuple] = []
    monkeypatch.setattr(
        summaries, "set_translation", lambda c, lg, t: set_calls.append((c, lg, t))
    )

    resp = client.get("/api/account/reports/comm-001?lang=zh")
    assert resp.status_code == 200
    assert resp.json()["ai_summary_text"] == ZH_TEXT
    assert set_calls == [("comm-001", "zh", ZH_TEXT)]


def test_translate_llm_error_returns_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(summaries, "get_translation", lambda comm_id, lang: None)
    monkeypatch.setattr(
        summaries,
        "translate_summary",
        lambda t, _lang: (_ for _ in ()).throw(LLMError("upstream failed")),
    )

    resp = client.get("/api/account/reports/comm-001?lang=ms")
    assert resp.status_code == 502


def test_translate_config_error_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(summaries, "get_translation", lambda comm_id, lang: None)
    monkeypatch.setattr(
        summaries,
        "translate_summary",
        lambda t, _lang: (_ for _ in ()).throw(LLMConfigError("key missing")),
    )

    resp = client.get("/api/account/reports/comm-001?lang=ta")
    assert resp.status_code == 503
