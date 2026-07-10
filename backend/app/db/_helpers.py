"""Internal query helpers shared across the db submodules."""

import json
from typing import Any

from app.db import client


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten the joined patients row and JSON-encode JSONB columns to strings."""
    patient = record.pop("patients", {})
    record["patient_name"] = patient.get("patient_name", "")
    record["epic_patient_id"] = patient.get("epic_patient_id", "")
    for column in ("conditions_json", "condition_diff"):
        if isinstance(record.get(column), (list, dict)):
            record[column] = json.dumps(record[column])
    return record


def latest_approved_for_patient(patient_id: str) -> dict[str, Any] | None:
    """Return the most recently approved translation for a patient, or None."""
    supabase = client.get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select("*, patients(patient_name, epic_patient_id)")
        .eq("patient_id", patient_id)
        .eq("status", "Approved")
        .order("approved_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return normalize_record(res.data[0])


def get_json_column(comm_id: str, column: str, key: str) -> str | None:
    """Read one key out of a JSONB dict column, or None on record/key miss."""
    supabase = client.get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select(column)
        .eq("id", comm_id)
        .execute()
    )
    if not res.data:
        return None
    raw = res.data[0].get(column) or {}
    values: dict = json.loads(raw) if isinstance(raw, str) else raw
    return values.get(key)


def set_json_column(comm_id: str, column: str, key: str, value: str) -> None:
    """Write one key into a JSONB dict column, preserving other keys."""
    supabase = client.get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select(column)
        .eq("id", comm_id)
        .execute()
    )
    if not res.data:
        return
    raw = res.data[0].get(column) or {}
    current: dict = json.loads(raw) if isinstance(raw, str) else raw
    current[key] = value
    (
        supabase.table("care_plan_translations")
        .update({column: current})
        .eq("id", comm_id)
        .execute()
    )
