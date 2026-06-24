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
    # Entry 1: consumed by first get_communication (pre-update existence check)
    # Entry 2: consumed by update_communication's .update().eq().execute() — same table mock
    # Entry 3: consumed by second get_communication (post-update read for approved_at + patient_id)
    mock_supabase.table("care_plan_translations").select().eq().execute.side_effect = [
        MagicMock(data=[{"id": seeded_comm_id, "status": "Draft", "patients": {}}]),
        MagicMock(data=[{"id": seeded_comm_id}]),
        MagicMock(
            data=[
                {
                    "id": seeded_comm_id,
                    "patient_id": "patient-uuid-1",
                    "status": "Approved",
                    "approved_at": "2023-01-01T00:00:00Z",
                    "patients": {
                        "patient_name": "Tan Mei Ling",
                        "epic_patient_id": "mock-oncology-123",
                    },
                }
            ]
        ),
    ]

    resp = client.post(
        f"/api/communications/{seeded_comm_id}/approve",
        json={"ai_summary_text": APPROVED_TEXT},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == seeded_comm_id
    assert "/family/" in body["family_link"]
    assert "/member/" in body["family_link"]
