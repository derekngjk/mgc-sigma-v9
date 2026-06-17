import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import db
from main import app

APPROVED_TEXT = "Think of the cancer cells like weeds taking over a garden."


@pytest.fixture
def client(mock_supabase) -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded_comm_id(mock_supabase) -> str:
    mock_supabase.table("patients").upsert().execute.return_value = MagicMock(
        data=[{"id": "p1"}]
    )
    mock_supabase.table(
        "care_plan_translations"
    ).insert().execute.return_value = MagicMock(data=[{"id": "c1"}])
    return db.create_communication(
        patient_name="Elena Vasquez",
        raw_clinical_text='{"conditions": [], "care_plans": []}',
        epic_patient_id="mock-oncology-123",
        fhir_source="mock",
    )


def test_approve_returns_200(
    client: TestClient, seeded_comm_id: str, mock_supabase
) -> None:
    # side_effect on care_plan_translations table
    mock_supabase.table("care_plan_translations").select().eq().execute.side_effect = [
        MagicMock(data=[{"id": seeded_comm_id, "status": "Draft", "patients": {}}]),
        MagicMock(
            data=[
                {
                    "id": seeded_comm_id,
                    "status": "Approved",
                    "approved_at": "2023-01-01T00:00:00Z",
                    "patients": {},
                }
            ]
        ),
        MagicMock(
            data=[
                {
                    "id": seeded_comm_id,
                    "status": "Approved",
                    "approved_at": "2023-01-01T00:00:00Z",
                    "patients": {},
                }
            ]
        ),
    ]
    mock_supabase.table(
        "care_plan_translations"
    ).update().eq().execute.return_value = MagicMock(data=[{"id": seeded_comm_id}])

    resp = client.post(
        f"/api/communications/{seeded_comm_id}/approve",
        json={"ai_summary_text": APPROVED_TEXT},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == seeded_comm_id
