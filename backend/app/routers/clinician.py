"""Clinician-facing endpoints: fetch patient, generate draft, approve."""

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.db import (
    create_communication,
    get_communication,
    get_latest_approved_communication,
    patient_has_identity,
    set_delivered,
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
    ReviewVerdict,
)
from app.services.fhir import FHIRError, PatientNotFoundError, fetch_patient_data
from app.services.image_brief import generate_image_brief, minimal_brief
from app.services.images import ImageConfigError, ImageError, generate_visual
from app.services.llm import LLMConfigError, LLMError
from app.services.reviews import verify_summary
from app.services.summaries import VALID_AUDIENCES, generate_summary

logger = logging.getLogger(__name__)

router = APIRouter()


def _generate_and_cache_image(
    comm_id: str,
    conditions: list[str],
    summary_text: str = "",
    raw_clinical_text: str = "",
    target_audience: str = "patient",
) -> None:
    """Generate a visual aid and cache its URL. Failures are logged, not raised."""
    logger.info("generating image for %s, conditions=%s", comm_id, conditions)
    try:
        try:
            brief = generate_image_brief(
                conditions, target_audience, summary_text, raw_clinical_text
            )
        except LLMError as exc:
            logger.warning(
                "image brief failed for %s, using minimal brief: %s", comm_id, exc
            )
            brief = minimal_brief(conditions, target_audience)
        image_bytes = generate_visual(brief)
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
        nric=data["nric"],
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

    # Optional independent review. verify_summary never raises
    # If failed to call reviewer, set to review unavailable
    review: ReviewVerdict | None = None
    update_fields: dict[str, str] = {
        "ai_summary_text": summary,
        "target_audience": req.target_audience,
    }
    if req.review:
        conditions = json.loads(record.get("conditions_json") or "[]")
        review = ReviewVerdict(
            **verify_summary(record["raw_clinical_text"], conditions, summary)
        )
        update_fields["review_json"] = review.model_dump_json()

    update_communication(req.comm_id, **update_fields)

    return GenerateResponse(
        comm_id=req.comm_id,
        ai_summary_text=summary,
        target_audience=req.target_audience,
        review=review,
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

    # Auto-deliver to the patient's account. `delivered` reflects whether an account
    # actually exists to receive it (a patient with no NRIC on file has none).
    delivered = patient_has_identity(updated.get("patient_id", ""))
    set_delivered(comm_id)

    if req.generate_image:
        conditions = json.loads(updated.get("conditions_json") or "[]")
        summary_text = updated.get("ai_summary_text") or ""
        raw_clinical_text = updated.get("raw_clinical_text") or ""
        target_audience = updated.get("target_audience", "patient")
        _generate_and_cache_image(
            comm_id, conditions, summary_text, raw_clinical_text, target_audience
        )

    return ApproveResponse(
        id=comm_id,
        approved_at=updated["approved_at"],
        patient_name=updated.get("patient_name", ""),
        delivered=delivered,
    )
