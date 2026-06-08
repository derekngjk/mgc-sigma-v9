"""
Task 1.2 — SQLite state store (TDD).
Acceptance: backend can create, read, and update Communications records.

Schema reflects FHIR R4 data model:
  - epic_patient_id  maps to Patient.identifier from Epic Sandbox
  - fhir_source      distinguishes live Sandbox vs hardcoded mock fallback
  - target_audience  maps to the LLM prompt parameter (patient | family)
  - approved_at      audit timestamp for the HITL approval step
"""
import re
from datetime import datetime, timezone

import pytest

from db import create_communication, get_communication, init_db, update_communication

ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+\d{2}:\d{2}$")


@pytest.fixture
def db(tmp_path: pytest.TempPathFactory) -> str:
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


# --- create ---

def test_create_returns_uuid(db: str) -> None:
    comm_id = create_communication(db, patient_name="Jane Doe", raw_clinical_text="Dx: Hypertension")
    assert comm_id is not None
    assert len(comm_id) == 36  # xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx


def test_create_sets_draft_status(db: str) -> None:
    comm_id = create_communication(db, patient_name="Jane Doe", raw_clinical_text="Dx: Hypertension")
    record = get_communication(db, comm_id)
    assert record is not None
    assert record["status"] == "Draft"


def test_create_stores_core_fields(db: str) -> None:
    comm_id = create_communication(db, patient_name="Jane Doe", raw_clinical_text="Dx: Hypertension")
    record = get_communication(db, comm_id)
    assert record["patient_name"] == "Jane Doe"
    assert record["raw_clinical_text"] == "Dx: Hypertension"
    assert record["ai_summary_text"] is None
    assert record["approved_at"] is None


def test_created_at_is_iso8601(db: str) -> None:
    comm_id = create_communication(db, patient_name="Jane Doe", raw_clinical_text="Dx: Hypertension")
    record = get_communication(db, comm_id)
    assert ISO8601_RE.match(record["created_at"]), f"created_at not ISO-8601: {record['created_at']}"


def test_create_default_fhir_source_is_sandbox(db: str) -> None:
    comm_id = create_communication(db, patient_name="Jane Doe", raw_clinical_text="Dx: Hypertension")
    record = get_communication(db, comm_id)
    assert record["fhir_source"] == "sandbox"


def test_create_default_target_audience_is_family(db: str) -> None:
    comm_id = create_communication(db, patient_name="Jane Doe", raw_clinical_text="Dx: Hypertension")
    record = get_communication(db, comm_id)
    assert record["target_audience"] == "family"


def test_create_stores_fhir_fields(db: str) -> None:
    # Epic Sandbox patient IDs are Base64-encoded strings; test with a realistic format
    comm_id = create_communication(
        db,
        patient_name="Jane Doe",
        raw_clinical_text="Dx: Hypertension",
        epic_patient_id="eovIMNNn7tHBQwLGAXNRRw3",
        fhir_source="sandbox",
        target_audience="family",
    )
    record = get_communication(db, comm_id)
    assert record["epic_patient_id"] == "eovIMNNn7tHBQwLGAXNRRw3"
    assert record["fhir_source"] == "sandbox"
    assert record["target_audience"] == "family"


def test_create_mock_fhir_source(db: str) -> None:
    # mock-oncology-123 is the reserved test ID that bypasses the Epic Sandbox
    comm_id = create_communication(
        db,
        patient_name="Test Patient",
        raw_clinical_text="Oncology mock data",
        epic_patient_id="mock-oncology-123",
        fhir_source="mock",
    )
    record = get_communication(db, comm_id)
    assert record["fhir_source"] == "mock"
    assert record["epic_patient_id"] == "mock-oncology-123"


# --- read ---

def test_get_unknown_id_returns_none(db: str) -> None:
    result = get_communication(db, "00000000-0000-0000-0000-000000000000")
    assert result is None


# --- update ---

def test_update_sets_approved_status(db: str) -> None:
    comm_id = create_communication(db, patient_name="Jane Doe", raw_clinical_text="Dx: Hypertension")
    update_communication(db, comm_id, ai_summary_text="Your blood pressure is high.", status="Approved")
    record = get_communication(db, comm_id)
    assert record["status"] == "Approved"
    assert record["ai_summary_text"] == "Your blood pressure is high."


def test_update_approved_sets_approved_at(db: str) -> None:
    comm_id = create_communication(db, patient_name="Jane Doe", raw_clinical_text="Dx: Hypertension")
    update_communication(db, comm_id, status="Approved")
    record = get_communication(db, comm_id)
    assert record["approved_at"] is not None


def test_approved_at_is_iso8601(db: str) -> None:
    comm_id = create_communication(db, patient_name="Jane Doe", raw_clinical_text="Dx: Hypertension")
    update_communication(db, comm_id, status="Approved")
    record = get_communication(db, comm_id)
    assert ISO8601_RE.match(record["approved_at"]), f"approved_at not ISO-8601: {record['approved_at']}"


def test_update_ai_summary_does_not_set_approved_at(db: str) -> None:
    # Saving an AI draft should not trigger the approval timestamp
    comm_id = create_communication(db, patient_name="Jane Doe", raw_clinical_text="Dx: Hypertension")
    update_communication(db, comm_id, ai_summary_text="Draft summary text.")
    record = get_communication(db, comm_id)
    assert record["approved_at"] is None
    assert record["status"] == "Draft"


def test_update_unknown_id_returns_false(db: str) -> None:
    result = update_communication(
        db, "00000000-0000-0000-0000-000000000000", status="Approved"
    )
    assert result is False
