"""
Automated Epic change detection.

For every watched patient (one who already has a delivered report), re-fetch the live
FHIR record and diff its active conditions against the last approved snapshot. When they
differ, auto-create a Draft carrying the diff, for each audience previously delivered to,
and auto-generate the updated summary so it is ready for clinician review.
"""

import json
import logging
from typing import Any

from app.db import (
    delivered_audiences,
    has_open_detected_draft,
    insert_detected_draft,
    update_communication,
)
from app.db import list_watched_patients as _list_watched_patients
from app.db._helpers import latest_approved_for_patient
from app.services.fhir import FHIRError, fetch_patient_data
from app.services.llm import LLMError
from app.services.summaries import generate_summary

logger = logging.getLogger(__name__)


def _diff(new: set[str], old: set[str]) -> dict[str, list[str]]:
    return {
        "added": sorted(new - old),
        "removed": sorted(old - new),
        "ongoing": sorted(new & old),
    }


def _detect_for_patient(patient: dict[str, str]) -> dict[str, Any] | None:
    """
    Detect a change for one patient and auto-create/generate drafts. None if unchanged.
    """
    epic_id = patient["epic_patient_id"]
    patient_id = patient["patient_id"]

    data = fetch_patient_data(
        epic_id
    )  # live FHIR (raises FHIRError, handled by caller)
    new_conditions = set(data["conditions"])

    baseline = latest_approved_for_patient(patient_id)
    old_conditions = set(json.loads(baseline["conditions_json"])) if baseline else set()
    if new_conditions == old_conditions:
        return None  # no change since the last approved report

    diff = _diff(new_conditions, old_conditions)
    conditions_frozen = frozenset(new_conditions)
    conditions_json = json.dumps(sorted(new_conditions))
    diff_json = json.dumps(diff)

    audiences = delivered_audiences(patient_id) or ["patient"]
    drafts: list[dict[str, Any]] = []
    for audience in audiences:
        if has_open_detected_draft(patient_id, audience, conditions_frozen):
            continue  # a pending draft for this exact change already exists
        comm_id = insert_detected_draft(
            patient_id=patient_id,
            raw_clinical_text=data["raw_fhir_json"],
            fhir_source=data["fhir_source"],
            target_audience=audience,
            conditions_json=conditions_json,
            condition_diff=diff_json,
        )
        generated = _try_generate(comm_id, data["raw_fhir_json"], audience, diff)
        drafts.append(
            {"comm_id": comm_id, "target_audience": audience, "generated": generated}
        )

    if not drafts:
        return None  # change exists but every audience was already drafted (dedup)

    return {
        "patient_name": patient.get("patient_name", ""),
        "epic_patient_id": epic_id,
        "added": diff["added"],
        "removed": diff["removed"],
        "drafts": drafts,
    }


def _try_generate(
    comm_id: str, raw_clinical_text: str, audience: str, diff: dict[str, list[str]]
) -> bool:
    """Generate and store the updated summary. Returns False (draft kept) on LLM failure."""
    try:
        summary = generate_summary(raw_clinical_text, audience, diff, "medium")
    except LLMError as exc:
        logger.warning("auto-generate failed for %s: %s", comm_id, exc)
        return False
    update_communication(comm_id, ai_summary_text=summary)
    return True


def scan_for_changes() -> dict[str, Any]:
    """
    Re-check every watched patient against Epic and draft updates for any changes.
    """
    watched = _list_watched_patients()
    changes: list[dict[str, Any]] = []
    errors: list[str] = []

    for patient in watched:
        try:
            result = _detect_for_patient(patient)
        except FHIRError as exc:
            msg = f"{patient.get('epic_patient_id', '?')}: {exc}"
            logger.warning("change scan failed for %s", msg)
            errors.append(msg)
            continue
        if result is not None:
            changes.append(result)

    drafts_created = sum(len(c["drafts"]) for c in changes)
    logger.info(
        "change scan: %d watched, %d changed, %d drafts",
        len(watched),
        len(changes),
        drafts_created,
    )
    return {
        "patients_scanned": len(watched),
        "patients_changed": len(changes),
        "drafts_created": drafts_created,
        "changes": changes,
        "errors": errors,
    }
