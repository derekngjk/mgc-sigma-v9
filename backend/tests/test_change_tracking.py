import json
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app


@pytest.fixture
def client(mock_supabase) -> TestClient:
    with TestClient(app) as c:
        yield c


def _make_mock_fhir(conditions: list[str]) -> dict:
    return {
        "patient_name": "Elena Vasquez",
        "dob": "1980-01-01",
        "gender": "female",
        "nric": "S1234567A",
        "conditions": conditions,
        "raw_fhir_json": json.dumps({"conditions": conditions}),
        "fhir_source": "mock",
    }


def test_get_latest_approved_returns_none_when_no_records(mock_supabase) -> None:
    mock_supabase.table("patients").execute.return_value = MagicMock(data=[])
    result = db.get_latest_approved_communication("patient-xyz")
    assert result is None


def test_get_latest_approved_returns_approved_record(mock_supabase) -> None:
    mock_supabase.table("patients").execute.return_value = MagicMock(
        data=[{"id": "p1"}]
    )
    mock_supabase.table("care_plan_translations").execute.return_value = MagicMock(
        data=[
            {
                "id": "comm-123",
                "status": "Approved",
                "patients": {"patient_name": "Elena", "epic_patient_id": "epi"},
            }
        ]
    )
    result = db.get_latest_approved_communication("patient-xyz")
    assert result is not None
    assert result["id"] == "comm-123"


def test_first_fetch_all_conditions_are_ongoing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, mock_supabase
) -> None:
    from app.routers import clinician

    monkeypatch.setattr(
        clinician, "fetch_patient_data", lambda _: _make_mock_fhir(["C1"])
    )

    # 1. get_latest_approved_communication -> find patient
    mock_supabase.table("patients").execute.side_effect = [
        MagicMock(data=[]),  # get_latest
        MagicMock(data=[{"id": "p1"}]),  # create (upsert)
    ]
    # 2. create_communication -> insert translation
    mock_supabase.table("care_plan_translations").execute.return_value = MagicMock(
        data=[{"id": "c1"}]
    )

    resp = client.get("/api/patient/test-patient-001")
    assert resp.status_code == 200
    diff = resp.json()["condition_diff"]
    assert "C1" in diff["ongoing"]


def test_diff_against_prior_approved_record(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, mock_supabase
) -> None:
    """A prior Approved snapshot of [C1, C2] vs. a fetch of [C2, C3] is the real
    change-detection path: C3 is new, C1 resolved, C2 ongoing."""
    from app.routers import clinician

    monkeypatch.setattr(
        clinician, "fetch_patient_data", lambda _: _make_mock_fhir(["C2", "C3"])
    )

    mock_supabase.table("patients").execute.side_effect = [
        MagicMock(data=[{"id": "p1"}]),  # get_latest -> patient found
        MagicMock(data=[{"id": "p1"}]),  # create_communication (upsert)
    ]
    mock_supabase.table("care_plan_translations").execute.side_effect = [
        MagicMock(  # the prior Approved record
            data=[
                {
                    "id": "comm-prev",
                    "status": "Approved",
                    "conditions_json": json.dumps(["C1", "C2"]),
                    "patients": {"patient_name": "Elena", "epic_patient_id": "epi"},
                }
            ]
        ),
        MagicMock(data=[{"id": "c2"}]),  # create_communication insert
    ]

    resp = client.get("/api/patient/test-patient-001")

    assert resp.status_code == 200
    diff = resp.json()["condition_diff"]
    assert diff["added"] == ["C3"]
    assert diff["removed"] == ["C1"]
    assert diff["ongoing"] == ["C2"]
