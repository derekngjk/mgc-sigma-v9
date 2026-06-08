"""
Task 2.1 — FHIR Sandbox Fetcher (TDD).
Acceptance: GET /api/patient/{epic_patient_id} returns cleaned demographics +
active conditions, creates a Draft Communications record in SQLite.

Groups:
  A — Mock fallback path  (no HTTP mocking needed)
  B — Sandbox happy path  (monkeypatches fhir._fetch_from_sandbox)
  C — Error paths
  D — _parse_fhir_bundle unit tests (pure, no I/O)
"""
import json
import re

import pytest
from fastapi.testclient import TestClient

import db
from fhir import FHIRError, PatientNotFoundError, _parse_fhir_bundle
from main import app

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# ── shared fixture ────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    import main
    monkeypatch.setattr(main, "DB_PATH", db_path)
    db.init_db(db_path)
    with TestClient(app) as c:
        yield c


# ── minimal valid FHIR bundle for sandbox tests ───────────────────────────────

SANDBOX_BUNDLE = {
    "patient": {
        "resourceType": "Patient",
        "name": [{"text": "John Smith", "family": "Smith", "given": ["John"]}],
        "birthDate": "1975-03-22",
        "gender": "male",
    },
    "conditions": {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            {
                "resource": {
                    "resourceType": "Condition",
                    "clinicalStatus": {"coding": [{"code": "active"}]},
                    "code": {"coding": [{"display": "Type 2 diabetes mellitus"}]},
                }
            },
            {
                "resource": {
                    "resourceType": "Condition",
                    "clinicalStatus": {"coding": [{"code": "resolved"}]},
                    "code": {"coding": [{"display": "Appendicitis"}]},
                }
            },
        ],
    },
    "care_plans": {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [
            {
                "resource": {
                    "resourceType": "CarePlan",
                    "status": "active",
                    "title": "Diabetes Management Plan",
                    "description": "Monitor HbA1c quarterly.",
                }
            }
        ],
    },
}


# ── Group A: mock fallback path ───────────────────────────────────────────────

def test_mock_returns_200(client: TestClient) -> None:
    assert client.get("/api/patient/mock-oncology-123").status_code == 200


def test_mock_required_fields(client: TestClient) -> None:
    body = client.get("/api/patient/mock-oncology-123").json()
    for field in ("epic_patient_id", "patient_name", "dob", "gender", "conditions", "comm_id", "fhir_source"):
        assert field in body, f"missing field: {field}"


def test_mock_fhir_source_is_mock(client: TestClient) -> None:
    body = client.get("/api/patient/mock-oncology-123").json()
    assert body["fhir_source"] == "mock"


def test_mock_comm_id_is_uuid(client: TestClient) -> None:
    body = client.get("/api/patient/mock-oncology-123").json()
    assert UUID_RE.match(body["comm_id"]), f"not a UUID: {body['comm_id']}"


def test_mock_conditions_is_nonempty_list_of_strings(client: TestClient) -> None:
    body = client.get("/api/patient/mock-oncology-123").json()
    assert isinstance(body["conditions"], list)
    assert len(body["conditions"]) > 0
    assert all(isinstance(c, str) for c in body["conditions"])


def test_mock_resolved_conditions_excluded(client: TestClient) -> None:
    body = client.get("/api/patient/mock-oncology-123").json()
    assert "Iron deficiency anaemia" not in body["conditions"]


def test_mock_patient_name(client: TestClient) -> None:
    body = client.get("/api/patient/mock-oncology-123").json()
    assert body["patient_name"] == "Elena Vasquez"


def test_mock_creates_draft_db_record(client: TestClient) -> None:
    import main
    body = client.get("/api/patient/mock-oncology-123").json()
    record = db.get_communication(main.DB_PATH, body["comm_id"])
    assert record is not None
    assert record["status"] == "Draft"
    assert record["fhir_source"] == "mock"


# ── Group B: sandbox happy path (monkeypatched) ───────────────────────────────

def test_sandbox_returns_200(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fhir._fetch_from_sandbox", lambda _: SANDBOX_BUNDLE)
    assert client.get("/api/patient/eovIMNNn7tHBQwLGAXNRRw3").status_code == 200


def test_sandbox_demographics_extracted(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fhir._fetch_from_sandbox", lambda _: SANDBOX_BUNDLE)
    body = client.get("/api/patient/eovIMNNn7tHBQwLGAXNRRw3").json()
    assert body["patient_name"] == "John Smith"
    assert body["dob"] == "1975-03-22"
    assert body["gender"] == "male"


def test_sandbox_fhir_source_is_sandbox(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fhir._fetch_from_sandbox", lambda _: SANDBOX_BUNDLE)
    body = client.get("/api/patient/eovIMNNn7tHBQwLGAXNRRw3").json()
    assert body["fhir_source"] == "sandbox"


def test_sandbox_comm_id_created(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import main
    monkeypatch.setattr("fhir._fetch_from_sandbox", lambda _: SANDBOX_BUNDLE)
    body = client.get("/api/patient/eovIMNNn7tHBQwLGAXNRRw3").json()
    record = db.get_communication(main.DB_PATH, body["comm_id"])
    assert record is not None
    assert record["status"] == "Draft"


def test_sandbox_active_conditions_only(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fhir._fetch_from_sandbox", lambda _: SANDBOX_BUNDLE)
    body = client.get("/api/patient/eovIMNNn7tHBQwLGAXNRRw3").json()
    assert "Type 2 diabetes mellitus" in body["conditions"]
    assert "Appendicitis" not in body["conditions"]


def test_sandbox_raw_fhir_json_stored(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    import main
    monkeypatch.setattr("fhir._fetch_from_sandbox", lambda _: SANDBOX_BUNDLE)
    body = client.get("/api/patient/eovIMNNn7tHBQwLGAXNRRw3").json()
    record = db.get_communication(main.DB_PATH, body["comm_id"])
    raw = json.loads(record["raw_clinical_text"])
    assert "conditions" in raw
    assert "care_plans" in raw


# ── Group C: error paths ──────────────────────────────────────────────────────

def test_unknown_patient_returns_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fhir._fetch_from_sandbox", lambda _: (_ for _ in ()).throw(PatientNotFoundError("not found")))
    assert client.get("/api/patient/unknown-id").status_code == 404


def test_fhir_error_returns_502(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fhir._fetch_from_sandbox", lambda _: (_ for _ in ()).throw(FHIRError("upstream error")))
    assert client.get("/api/patient/some-id").status_code == 502


def test_error_body_has_detail_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("fhir._fetch_from_sandbox", lambda _: (_ for _ in ()).throw(PatientNotFoundError("not found")))
    body = client.get("/api/patient/unknown-id").json()
    assert "detail" in body


# ── Group D: _parse_fhir_bundle unit tests (pure) ────────────────────────────

def _bundle(patient: dict, conditions: list, care_plans: list | None = None) -> dict:
    return {
        "patient": patient,
        "conditions": {"resourceType": "Bundle", "type": "searchset", "entry": [{"resource": c} for c in conditions]},
        "care_plans": {"resourceType": "Bundle", "type": "searchset", "entry": care_plans or []},
    }


def test_parse_name_text_field() -> None:
    raw = _bundle({"name": [{"text": "Alice Brown"}]}, [])
    assert _parse_fhir_bundle(raw)["patient_name"] == "Alice Brown"


def test_parse_name_given_family_fallback() -> None:
    raw = _bundle({"name": [{"given": ["Alice"], "family": "Brown"}]}, [])
    assert _parse_fhir_bundle(raw)["patient_name"] == "Alice Brown"


def test_parse_missing_dob_returns_empty_string() -> None:
    raw = _bundle({"name": [{"text": "Alice Brown"}]}, [])
    assert _parse_fhir_bundle(raw)["dob"] == ""


def test_parse_active_conditions_only() -> None:
    conditions = [
        {"clinicalStatus": {"coding": [{"code": "active"}]}, "code": {"coding": [{"display": "Hypertension"}]}},
        {"clinicalStatus": {"coding": [{"code": "resolved"}]}, "code": {"coding": [{"display": "Flu"}]}},
    ]
    raw = _bundle({"name": [{"text": "Alice Brown"}]}, conditions)
    result = _parse_fhir_bundle(raw)["conditions"]
    assert result == ["Hypertension"]


def test_parse_condition_display_from_coding() -> None:
    conditions = [
        {"clinicalStatus": {"coding": [{"code": "active"}]}, "code": {"coding": [{"display": "Type 2 diabetes mellitus"}]}},
    ]
    raw = _bundle({"name": [{"text": "Alice Brown"}]}, conditions)
    assert _parse_fhir_bundle(raw)["conditions"] == ["Type 2 diabetes mellitus"]
