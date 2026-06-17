import re
from unittest.mock import MagicMock, ANY
from db import create_communication, get_communication, update_communication

ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+\d{2}:\d{2}$")


def test_create_returns_uuid(mock_supabase) -> None:
    # Mock upsert to return a patient id
    mock_supabase.table("patients").upsert().execute.return_value = MagicMock(
        data=[{"id": "p1"}]
    )
    mock_supabase.table(
        "care_plan_translations"
    ).insert().execute.return_value = MagicMock(data=[{"id": "c1"}])

    comm_id = create_communication(
        patient_name="Jane Doe", raw_clinical_text="Dx: Hypertension"
    )
    assert comm_id is not None
    assert len(comm_id) == 36


def test_create_calls_supabase(mock_supabase) -> None:
    mock_supabase.table("patients").upsert().execute.return_value = MagicMock(
        data=[{"id": "p1"}]
    )
    mock_supabase.table(
        "care_plan_translations"
    ).insert().execute.return_value = MagicMock(data=[{"id": "c1"}])

    create_communication(patient_name="Jane Doe", raw_clinical_text="Dx: Hypertension")

    # Verify patient upsert
    mock_supabase.table.assert_any_call("patients")
    # Verify translation insert
    mock_supabase.table.assert_any_call("care_plan_translations")


def test_get_communication_flattens_data(mock_supabase) -> None:
    # Mock return from joined select
    mock_data = [
        {
            "id": "comm-123",
            "status": "Draft",
            "ai_summary_text": None,
            "patients": {"patient_name": "Jane Doe", "epic_patient_id": "epi-123"},
        }
    ]
    mock_supabase.table(
        "care_plan_translations"
    ).select().eq().execute.return_value = MagicMock(data=mock_data)

    record = get_communication("comm-123")
    assert record is not None
    assert record["patient_name"] == "Jane Doe"
    assert record["epic_patient_id"] == "epi-123"
    assert "patients" not in record


def test_update_communication_calls_update(mock_supabase) -> None:
    mock_supabase.table(
        "care_plan_translations"
    ).update().eq().execute.return_value = MagicMock(data=[{"id": "comm-123"}])

    result = update_communication("comm-123", status="Approved")
    assert result is True
    # In db.py, update is called with the fields dict
    mock_supabase.table("care_plan_translations").update.assert_called_with(
        {"status": "Approved", "approved_at": ANY}
    )


def test_update_unknown_id_returns_false(mock_supabase) -> None:
    mock_supabase.table(
        "care_plan_translations"
    ).update().eq().execute.return_value = MagicMock(data=[])

    result = update_communication("unknown", status="Approved")
    assert result is False
