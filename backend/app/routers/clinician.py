"""Clinician-facing endpoints: fetch patient, generate draft, approve."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.db import (
    create_communication,
    create_family_member,
    get_communication,
    get_latest_approved_communication,
    get_or_create_family,
    get_or_create_primary_member,
    set_image_url,
    update_communication,
    upload_image,
)
from app.dependencies import verify_clinician_token
from app.schemas import (
    VALID_LENGTHS,
    ApproveRequest,
    ApproveResponse,
    ConditionDiff,
    GenerateRequest,
    GenerateResponse,
    PatientResponse,
)
from app.services.fhir import FHIRError, PatientNotFoundError, fetch_patient_data
from app.services.images import ImageConfigError, ImageError, generate_visual
from app.services.llm import LLMConfigError, LLMError
from app.services.summaries import VALID_AUDIENCES, generate_summary

logger = logging.getLogger(__name__)

router = APIRouter()

_AUDIENCE_MEMBER_NAMES = {
    "spouse": "Spouse / Partner",
    "child": "Adult Child",
    "caregiver": "Caregiver",
}


def _generate_and_cache_image(
    comm_id: str, conditions: list[str], summary_text: str = ""
) -> None:
    """Generate a visual aid and cache its URL. Failures are logged, not raised."""
    logger.info("generating image for %s, conditions=%s", comm_id, conditions)
    try:
        image_bytes = generate_visual(conditions, summary_text)
        url = upload_image(comm_id, image_bytes)
        set_image_url(comm_id, url)
        logger.info("image ready for %s: %s", comm_id, url)
    except (ImageConfigError, ImageError) as exc:
        logger.warning("image generation failed for %s: %s", comm_id, exc)
    except Exception as exc:
        logger.error("image unexpected error for %s: %s", comm_id, exc)


@router.get("/api/patient/{epic_patient_id}", response_model=PatientResponse)
def get_patient(
    epic_patient_id: str,
    _: dict[str, Any] = Depends(verify_clinician_token),
) -> PatientResponse:
    try:
        data = fetch_patient_data(epic_patient_id)
    except PatientNotFoundError:
        raise HTTPException(
            status_code=404, detail="Patient not found in FHIR sandbox"
        ) from None
    except FHIRError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    new_conditions = set(data["conditions"])
    prev = get_latest_approved_communication(epic_patient_id)
    if prev:
        old_conditions = set(json.loads(prev["conditions_json"]))
        diff = ConditionDiff(
            added=sorted(new_conditions - old_conditions),
            removed=sorted(old_conditions - new_conditions),
            ongoing=sorted(new_conditions & old_conditions),
        )
    else:
        diff = ConditionDiff(added=[], removed=[], ongoing=sorted(new_conditions))

    comm_id = create_communication(
        patient_name=data["patient_name"],
        raw_clinical_text=data["raw_fhir_json"],
        epic_patient_id=epic_patient_id,
        fhir_source=data["fhir_source"],
        target_audience="family",
        conditions_json=json.dumps(data["conditions"]),
        condition_diff=diff.model_dump_json(),
    )

    return PatientResponse(
        comm_id=comm_id,
        patient_name=data["patient_name"],
        dob=data["dob"],
        gender=data["gender"],
        conditions=data["conditions"],
        fhir_source=data["fhir_source"],
        condition_diff=diff,
    )


@router.post("/api/generate", response_model=GenerateResponse)
def generate(
    req: GenerateRequest,
    _: dict[str, Any] = Depends(verify_clinician_token),
) -> GenerateResponse:
    if req.length not in VALID_LENGTHS:
        raise HTTPException(
            status_code=400, detail=f"length must be one of: {sorted(VALID_LENGTHS)}"
        )
    if req.target_audience not in VALID_AUDIENCES:
        raise HTTPException(
            status_code=400,
            detail=f"target_audience must be one of: {sorted(VALID_AUDIENCES)}",
        )
    record = get_communication(req.comm_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Communication record not found")
    condition_diff = (
        json.loads(record["condition_diff"]) if record.get("condition_diff") else None
    )
    try:
        summary = generate_summary(
            record["raw_clinical_text"], req.target_audience, condition_diff, req.length
        )
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    update_communication(
        req.comm_id,
        ai_summary_text=summary,
        target_audience=req.target_audience,
    )
    return GenerateResponse(
        comm_id=req.comm_id,
        ai_summary_text=summary,
        target_audience=req.target_audience,
    )


@router.post("/api/communications/{comm_id}/approve", response_model=ApproveResponse)
def approve_communication(
    comm_id: str,
    req: ApproveRequest,
    user: dict[str, Any] = Depends(verify_clinician_token),
) -> ApproveResponse:
    record = get_communication(comm_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Communication record not found")
    update_communication(
        comm_id,
        ai_summary_text=req.ai_summary_text,
        status="Approved",
        approved_by_user_id=user.get("id", ""),
    )
    updated = get_communication(comm_id)
    fid = get_or_create_family(updated.get("patient_id", ""))

    audience = updated.get("target_audience", "patient")
    if audience == "patient":
        mid = get_or_create_primary_member(fid, updated.get("patient_name", ""))
    else:
        mid = create_family_member(
            fid, _AUDIENCE_MEMBER_NAMES.get(audience, audience), audience
        )

    if req.generate_image:
        conditions = json.loads(updated.get("conditions_json") or "[]")
        summary_text = updated.get("ai_summary_text") or ""
        _generate_and_cache_image(comm_id, conditions, summary_text)

    return ApproveResponse(
        id=comm_id,
        approved_at=updated["approved_at"],
        family_link=f"{settings.frontend_origin}/family/{fid}/member/{mid}",
    )
