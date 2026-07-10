from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

APPROVED_TEXT = "Think of the cancer cells like weeds taking over a garden."


@pytest.fixture
def client(mock_supabase) -> TestClient:
    with TestClient(app) as c:
        yield c


def test_family_view_returns_200(client: TestClient, mock_supabase) -> None:
    comm_id = "comm-123"
    # Mock get_communication return
    mock_supabase.table(
        "care_plan_translations"
    ).select().eq().execute.return_value = MagicMock(
        data=[
            {
                "id": comm_id,
                "status": "Approved",
                "patient_name": "Elena Vasquez",
                "ai_summary_text": APPROVED_TEXT,
                "approved_at": "2023-01-01T00:00:00Z",
                "condition_diff": {"added": [], "removed": [], "ongoing": ["Cancer"]},
                "patients": {
                    "patient_name": "Elena Vasquez",
                    "epic_patient_id": "mock-oncology-123",
                },
            }
        ]
    )

    resp = client.get(f"/api/communications/{comm_id}")
    assert resp.status_code == 200
    assert resp.json()["ai_summary_text"] == APPROVED_TEXT


def test_family_view_draft_returns_404(client: TestClient, mock_supabase) -> None:
    comm_id = "comm-123"
    # Mock get_communication return a Draft record
    mock_supabase.table(
        "care_plan_translations"
    ).select().eq().execute.return_value = MagicMock(
        data=[
            {
                "id": comm_id,
                "status": "Draft",
                "patients": {"patient_name": "Elena", "epic_patient_id": "epi"},
            }
        ]
    )

    resp = client.get(f"/api/communications/{comm_id}")
    assert resp.status_code == 404
