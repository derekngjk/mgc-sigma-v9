"""
Queries backing automated change detection: watch list, dedup, detected drafts.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.db import client
from app.db._helpers import normalize_record


def _condition_set(conditions_json: Any) -> frozenset[str]:
    """
    Parse a conditions_json value (str or list) into a comparable set.
    """
    if isinstance(conditions_json, str):
        try:
            conditions_json = json.loads(conditions_json)
        except json.JSONDecodeError:
            return frozenset()
    if isinstance(conditions_json, list):
        return frozenset(str(c) for c in conditions_json)
    return frozenset()


def list_watched_patients() -> list[dict[str, str]]:
    """
    A patient is only "watched" once a report has been delivered about them; before
    that there is no baseline to diff against and no recipient to update.
    """
    supabase = client.get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select("patient_id, patients(epic_patient_id, patient_name)")
        .eq("status", "Approved")
        .execute()
    )
    seen: dict[str, dict[str, str]] = {}
    for row in res.data or []:
        pid = row.get("patient_id")
        if not pid or pid in seen:
            continue
        patient = row.get("patients") or {}
        epic_id = patient.get("epic_patient_id", "")
        if not epic_id:
            continue
        seen[pid] = {
            "patient_id": pid,
            "epic_patient_id": epic_id,
            "patient_name": patient.get("patient_name", ""),
        }
    return list(seen.values())


def delivered_audiences(patient_id: str) -> list[str]:
    """
    Distinct target_audiences already delivered for a patient (who to re-notify).
    """
    supabase = client.get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select("target_audience, delivered_to_patient_at")
        .eq("patient_id", patient_id)
        .eq("status", "Approved")
        .execute()
    )
    out: list[str] = []
    for row in res.data or []:
        audience = row.get("target_audience")
        if row.get("delivered_to_patient_at") and audience and audience not in out:
            out.append(audience)
    return out


def has_open_detected_draft(
    patient_id: str, target_audience: str, conditions: frozenset[str]
) -> bool:
    """
    True if an un-approved detected draft already exists for the same change.

    The dedup guard that stops a repeating scan from creating a new draft every run.
    Matches on patient + audience + the exact active-condition set.
    """
    supabase = client.get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select("id, conditions_json, detected_at")
        .eq("patient_id", patient_id)
        .eq("target_audience", target_audience)
        .eq("status", "Draft")
        .execute()
    )
    for row in res.data or []:
        if (
            row.get("detected_at")
            and _condition_set(row.get("conditions_json")) == conditions
        ):
            return True
    return False


def insert_detected_draft(
    patient_id: str,
    raw_clinical_text: str,
    fhir_source: str,
    target_audience: str,
    conditions_json: str,
    condition_diff: str,
) -> str:
    """
    Insert a Draft flagged as change-detected (the patient already exists).
    """
    supabase = client.get_supabase()
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
            "detected_at": datetime.now(UTC).isoformat(),
        }
    ).execute()
    return comm_id


def list_detected_drafts() -> list[dict[str, Any]]:
    """
    Un-approved change-detected drafts for the clinician inbox, newest first.
    """
    supabase = client.get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select("*, patients(patient_name, epic_patient_id)")
        .eq("status", "Draft")
        .not_.is_("detected_at", "null")
        .order("detected_at", desc=True)
        .execute()
    )
    return [normalize_record(row) for row in res.data or []]
