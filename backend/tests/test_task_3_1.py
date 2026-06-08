"""
Task 3.1 — LLM Translation (TDD).
Acceptance: POST /api/generate accepts comm_id + target_audience,
returns AI-generated simplified summary, stores result in SQLite.

Groups:
  A — Happy path  (monkeypatches llm._call_llm)
  B — target_audience handling
  C — Error paths  (comm not found, LLM errors)
  D — generate_summary unit tests  (monkeypatches llm._call_llm, pure-ish)
"""

import pytest
from fastapi.testclient import TestClient

import db
from llm import LLMConfigError, LLMError, generate_summary
from main import app

MOCK_SUMMARY = "Think of the cancer cells like weeds taking over a garden..."


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    import main
    monkeypatch.setattr(main, "DB_PATH", db_path)
    db.init_db(db_path)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded_comm_id(client: TestClient) -> str:
    import main
    return db.create_communication(
        main.DB_PATH,
        patient_name="Elena Vasquez",
        raw_clinical_text='{"conditions": ["Invasive ductal carcinoma"], "care_plans": ["Neoadjuvant treatment"]}',
        epic_patient_id="mock-oncology-123",
        fhir_source="mock",
    )


# ── Group A: happy path ───────────────────────────────────────────────────────

def test_generate_returns_200(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seeded_comm_id: str
) -> None:
    monkeypatch.setattr("llm._call_llm", lambda prompt: MOCK_SUMMARY)
    resp = client.post("/api/generate", json={"comm_id": seeded_comm_id})
    assert resp.status_code == 200


def test_generate_response_has_required_fields(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seeded_comm_id: str
) -> None:
    monkeypatch.setattr("llm._call_llm", lambda prompt: MOCK_SUMMARY)
    body = client.post("/api/generate", json={"comm_id": seeded_comm_id}).json()
    for field in ("comm_id", "ai_summary_text", "target_audience"):
        assert field in body, f"missing field: {field}"


def test_generate_stores_summary_in_db(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seeded_comm_id: str
) -> None:
    import main
    monkeypatch.setattr("llm._call_llm", lambda prompt: MOCK_SUMMARY)
    client.post("/api/generate", json={"comm_id": seeded_comm_id})
    record = db.get_communication(main.DB_PATH, seeded_comm_id)
    assert record is not None
    assert record["ai_summary_text"] == MOCK_SUMMARY


def test_generate_default_target_audience_is_family(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seeded_comm_id: str
) -> None:
    monkeypatch.setattr("llm._call_llm", lambda prompt: MOCK_SUMMARY)
    body = client.post("/api/generate", json={"comm_id": seeded_comm_id}).json()
    assert body["target_audience"] == "family"


# ── Group B: target_audience handling ────────────────────────────────────────

def test_generate_patient_audience_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seeded_comm_id: str
) -> None:
    monkeypatch.setattr("llm._call_llm", lambda prompt: MOCK_SUMMARY)
    resp = client.post("/api/generate", json={"comm_id": seeded_comm_id, "target_audience": "patient"})
    assert resp.status_code == 200


def test_generate_family_audience_accepted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seeded_comm_id: str
) -> None:
    monkeypatch.setattr("llm._call_llm", lambda prompt: MOCK_SUMMARY)
    resp = client.post("/api/generate", json={"comm_id": seeded_comm_id, "target_audience": "family"})
    assert resp.status_code == 200


def test_generate_target_audience_stored_in_db(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seeded_comm_id: str
) -> None:
    import main
    monkeypatch.setattr("llm._call_llm", lambda prompt: MOCK_SUMMARY)
    client.post("/api/generate", json={"comm_id": seeded_comm_id, "target_audience": "patient"})
    record = db.get_communication(main.DB_PATH, seeded_comm_id)
    assert record is not None
    assert record["target_audience"] == "patient"


# ── Group C: error paths ──────────────────────────────────────────────────────

def test_generate_unknown_comm_returns_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("llm._call_llm", lambda prompt: MOCK_SUMMARY)
    resp = client.post("/api/generate", json={"comm_id": "00000000-0000-0000-0000-000000000000"})
    assert resp.status_code == 404


def test_generate_llm_error_returns_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seeded_comm_id: str
) -> None:
    monkeypatch.setattr("llm._call_llm", lambda _: (_ for _ in ()).throw(LLMError("api error")))
    resp = client.post("/api/generate", json={"comm_id": seeded_comm_id})
    assert resp.status_code == 502


def test_generate_llm_config_error_returns_503(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seeded_comm_id: str
) -> None:
    monkeypatch.setattr("llm._call_llm", lambda _: (_ for _ in ()).throw(LLMConfigError("key not set")))
    resp = client.post("/api/generate", json={"comm_id": seeded_comm_id})
    assert resp.status_code == 503


def test_error_body_has_detail_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("llm._call_llm", lambda prompt: MOCK_SUMMARY)
    body = client.post("/api/generate", json={"comm_id": "00000000-0000-0000-0000-000000000000"}).json()
    assert "detail" in body


# ── Group D: generate_summary unit tests (pure-ish) ──────────────────────────

def test_generate_summary_returns_llm_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("llm._call_llm", lambda prompt: MOCK_SUMMARY)
    result = generate_summary('{"conditions": []}', "family")
    assert result == MOCK_SUMMARY


def test_generate_summary_passes_raw_text_in_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr("llm._call_llm", lambda prompt: captured.append(prompt) or MOCK_SUMMARY)
    raw = '{"conditions": ["Invasive ductal carcinoma"]}'
    generate_summary(raw, "family")
    assert raw in captured[0]


def test_generate_summary_passes_audience_in_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []
    monkeypatch.setattr("llm._call_llm", lambda prompt: captured.append(prompt) or MOCK_SUMMARY)
    generate_summary('{"conditions": []}', "patient")
    assert "patient" in captured[0]
