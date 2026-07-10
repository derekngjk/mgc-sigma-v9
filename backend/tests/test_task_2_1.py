import re
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import db
from fhir import PatientNotFoundError
from main import app

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


@pytest.fixture
def client(mock_supabase) -> TestClient:
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
            }
        ],
    },
    "care_plans": {"resourceType": "Bundle", "type": "searchset", "entry": []},
}


def test_mock_returns_200(client: TestClient, mock_supabase) -> None:
    # patients table: 1. select (get_latest), 2. upsert (create)
    mock_supabase.table("patients").execute.side_effect = [
        MagicMock(data=[]),  # get_latest
        MagicMock(data=[{"id": "p1"}]),  # create (upsert)
    ]
    mock_supabase.table("care_plan_translations").execute.return_value = MagicMock(
        data=[{"id": "c1"}]
    )

    assert client.get("/api/patient/mock-oncology-123").status_code == 200


def test_mock_creates_draft_db_record(client: TestClient, mock_supabase) -> None:
    # patients table: 1. select (get_latest), 2. upsert (create)
    mock_supabase.table("patients").execute.side_effect = [
        MagicMock(data=[]),  # get_latest
        MagicMock(data=[{"id": "p1"}]),  # create (upsert)
    ]

    # care_plan_translations table: 1. insert (create), 2. select (get_comm by test)
    mock_supabase.table("care_plan_translations").execute.side_effect = [
        MagicMock(data=[{"id": "c1"}]),  # create (insert)
        MagicMock(
            data=[
                {  # get_communication
                    "id": "comm-123",
                    "status": "Draft",
                    "fhir_source": "mock",
                    "conditions_json": "[]",
                    "condition_diff": "{}",
                    "raw_clinical_text": "{}",
                    "patients": {
                        "patient_name": "Elena Vasquez",
                        "epic_patient_id": "mock-oncology-123",
                    },
                }
            ]
        ),
    ]

    body = client.get("/api/patient/mock-oncology-123").json()
    record = db.get_communication(body["comm_id"])
    assert record is not None
    assert record["status"] == "Draft"
    assert record["fhir_source"] == "mock"


def test_sandbox_returns_200(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, mock_supabase
) -> None:
    monkeypatch.setattr("fhir._fetch_from_sandbox", lambda _: SANDBOX_BUNDLE)
    # patients table: 1. select (get_latest), 2. upsert (create)
    mock_supabase.table("patients").execute.side_effect = [
        MagicMock(data=[]),  # get_latest
        MagicMock(data=[{"id": "p1"}]),  # create (upsert)
    ]
    mock_supabase.table("care_plan_translations").execute.return_value = MagicMock(
        data=[{"id": "c1"}]
    )

    assert client.get("/api/patient/eovIMNNn7tHBQwLGAXNRRw3").status_code == 200


def test_unknown_patient_returns_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def raise_not_found(_):
        raise PatientNotFoundError("not found")

    monkeypatch.setattr("fhir._fetch_from_sandbox", raise_not_found)
    assert client.get("/api/patient/unknown-id").status_code == 404
