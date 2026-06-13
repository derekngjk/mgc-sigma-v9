import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import db
from main import app

MOCK_SUMMARY = "Think of the cancer cells like weeds taking over a garden..."


@pytest.fixture
def client(mock_supabase) -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded_comm_id(mock_supabase) -> str:
    mock_supabase.table("patients").execute.return_value = MagicMock(
        data=[{"id": "p1"}]
    )
    mock_supabase.table("care_plan_translations").execute.return_value = MagicMock(
        data=[{"id": "c1"}]
    )
    return db.create_communication(
        patient_name="Elena Vasquez",
        raw_clinical_text='{"conditions": ["Invasive ductal carcinoma"]}',
        epic_patient_id="mock-oncology-123",
        fhir_source="mock",
    )


def test_generate_returns_200(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_comm_id: str,
    mock_supabase,
) -> None:
    monkeypatch.setattr("llm._call_llm", lambda prompt: MOCK_SUMMARY)

    mock_supabase.table("care_plan_translations").execute.side_effect = [
        MagicMock(
            data=[
                {
                    "id": seeded_comm_id,
                    "raw_clinical_text": '{"conditions": []}',
                    "condition_diff": '{"added": [], "removed": [], "ongoing": []}',
                    "patients": {"patient_name": "Elena", "epic_patient_id": "epi"},
                }
            ]
        ),
        MagicMock(data=[{"id": seeded_comm_id}]),  # for update
    ]

    resp = client.post("/api/generate", json={"comm_id": seeded_comm_id})
    assert resp.status_code == 200


def test_generate_stores_summary_in_db(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    seeded_comm_id: str,
    mock_supabase,
) -> None:
    monkeypatch.setattr("llm._call_llm", lambda prompt: MOCK_SUMMARY)

    mock_supabase.table("care_plan_translations").execute.side_effect = [
        MagicMock(
            data=[
                {
                    "id": seeded_comm_id,
                    "raw_clinical_text": '{"conditions": []}',
                    "condition_diff": '{"added": [], "removed": [], "ongoing": []}',
                    "patients": {"patient_name": "Elena", "epic_patient_id": "epi"},
                }
            ]
        ),
        MagicMock(data=[{"id": seeded_comm_id}]),  # for update
    ]

    client.post("/api/generate", json={"comm_id": seeded_comm_id})

    # Check that update was called. Since we used side_effect, we can check calls.
    # The second call to execute on care_plan_translations should be the update.
    assert mock_supabase.table("care_plan_translations").update.called
