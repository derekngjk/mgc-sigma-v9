"""CRUD for the care_plan_translations (communication) records."""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.db import client
from app.db._helpers import (
    get_json_column,
    latest_approved_for_patient,
    normalize_record,
    set_json_column,
)
from app.services.identity import identity_hash

_UPDATABLE_FIELDS = {
    "ai_summary_text",
    "status",
    "approved_at",
    "target_audience",
    "approved_by_user_id",
    "review_json",
}


def create_communication(
    patient_name: str,
    raw_clinical_text: str,
    epic_patient_id: str = "",
    fhir_source: str = "sandbox",
    target_audience: str = "family",
    conditions_json: str = "[]",
    condition_diff: str | None = None,
    nric: str = "",
) -> str:
    supabase = client.get_supabase()

    patient_row = {"epic_patient_id": epic_patient_id, "patient_name": patient_name}
    # The account login key is derived here so the account exists as soon as the
    # patient is fetched. Only set it when derivable, to avoid clobbering an existing
    # hash with '' for a record that arrives without an NRIC.
    login_hash = identity_hash(patient_name, nric)
    if login_hash:
        patient_row["identity_hash"] = login_hash

    patient_res = (
        supabase.table("patients")
        .upsert(patient_row, on_conflict="epic_patient_id")
        .execute()
    )
    patient_id = patient_res.data[0]["id"]

    comm_id = str(uuid.uuid4())
    supabase.table("care_plan_translations").insert(
        {
            "id": comm_id,
            "patient_id": patient_id,
            "fhir_source": fhir_source,
            "raw_clinical_text": raw_clinical_text,
            "target_audience": target_audience,
            "status": "Draft",
            "conditions_json": conditions_json,
            "condition_diff": condition_diff,
        }
    ).execute()

    return comm_id


def get_communication(comm_id: str) -> dict[str, Any] | None:
    supabase = client.get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select("*, patients(patient_name, epic_patient_id)")
        .eq("id", comm_id)
        .execute()
    )
    if not res.data:
        return None
    return normalize_record(res.data[0])


def get_latest_approved_communication(epic_patient_id: str) -> dict[str, Any] | None:
    supabase = client.get_supabase()
    patient_res = (
        supabase.table("patients")
        .select("id")
        .eq("epic_patient_id", epic_patient_id)
        .execute()
    )
    if not patient_res.data:
        return None
    return latest_approved_for_patient(patient_res.data[0]["id"])


def update_communication(comm_id: str, **kwargs: str) -> bool:
    fields = {k: v for k, v in kwargs.items() if k in _UPDATABLE_FIELDS}
    if not fields:
        return False

    if fields.get("status") == "Approved" and "approved_at" not in fields:
        fields["approved_at"] = datetime.now(UTC).isoformat()

    supabase = client.get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .update(fields)
        .eq("id", comm_id)
        .execute()
    )
    return len(res.data) > 0


def get_translation(comm_id: str, lang: str) -> str | None:
    return get_json_column(comm_id, "translations_json", lang)


def set_translation(comm_id: str, lang: str, text: str) -> None:
    set_json_column(comm_id, "translations_json", lang, text)
