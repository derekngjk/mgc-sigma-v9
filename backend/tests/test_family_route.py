import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from main import app

APPROVED_TEXT = "Think of the cancer cells like weeds taking over a garden."
FAMILY_ID = "fid-abc-123"
MEMBER_ID = "mid-xyz-456"
PATIENT_ID = "patient-uuid-789"


@pytest.fixture
def client(mock_supabase) -> TestClient:
    with TestClient(app) as c:
        yield c


def test_family_member_view_returns_200(client: TestClient, mock_supabase) -> None:
    # family_members: valid membership
    mock_supabase.table("family_members").select().eq().execute.return_value = MagicMock(
        data=[{"id": MEMBER_ID}]
    )
    # families: resolves to a patient
    mock_supabase.table("families").select().eq().execute.return_value = MagicMock(
        data=[{"patient_id": PATIENT_ID}]
    )
    # care_plan_translations: latest approved summary
    mock_supabase.table("care_plan_translations").select().eq().execute.return_value = MagicMock(
        data=[
            {
                "id": "comm-001",
                "status": "Approved",
                "ai_summary_text": APPROVED_TEXT,
                "approved_at": "2024-01-01T00:00:00Z",
                "condition_diff": {"added": [], "removed": [], "ongoing": ["Cancer"]},
                "patients": {
                    "patient_name": "Tan Mei Ling",
                    "epic_patient_id": "mock-oncology-123",
                },
            }
        ]
    )

    resp = client.get(f"/api/family/{FAMILY_ID}/member/{MEMBER_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ai_summary_text"] == APPROVED_TEXT
    assert body["patient_name"] == "Tan Mei Ling"


def test_family_member_view_invalid_pair_returns_404(
    client: TestClient, mock_supabase
) -> None:
    # family_members returns empty — mid does not belong to fid
    mock_supabase.table("family_members").select().eq().execute.return_value = MagicMock(
        data=[]
    )

    resp = client.get(f"/api/family/{FAMILY_ID}/member/wrong-member-id")
    assert resp.status_code == 404


def test_family_member_view_no_approved_summary_returns_404(
    client: TestClient, mock_supabase
) -> None:
    mock_supabase.table("family_members").select().eq().execute.return_value = MagicMock(
        data=[{"id": MEMBER_ID}]
    )
    mock_supabase.table("families").select().eq().execute.return_value = MagicMock(
        data=[{"patient_id": PATIENT_ID}]
    )
    # No approved summary yet
    mock_supabase.table("care_plan_translations").select().eq().execute.return_value = MagicMock(
        data=[]
    )

    resp = client.get(f"/api/family/{FAMILY_ID}/member/{MEMBER_ID}")
    assert resp.status_code == 404
