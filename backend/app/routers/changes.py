"""
Change-detection endpoints: the scheduler-triggered scan and the clinician inbox.
"""

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.config import settings
from app.db import list_detected_drafts
from app.dependencies import verify_clinician_token
from app.schemas import (
    ChangeInboxItem,
    ChangeInboxResponse,
    ConditionDiff,
    ScanResult,
)
from app.services.change_detection import scan_for_changes

router = APIRouter()


def require_scan_token(x_scan_token: str = Header(default="")) -> None:
    """
    Authorize the scheduler by shared secret (SCAN_TOKEN in .env.example)
    """
    if not settings.scan_token:
        raise HTTPException(
            status_code=503, detail="Change detection disabled (SCAN_TOKEN not set)"
        )
    if x_scan_token != settings.scan_token:
        raise HTTPException(status_code=401, detail="Invalid scan token")


@router.post("/api/changes/scan", response_model=ScanResult)
def scan(_: None = Depends(require_scan_token)) -> ScanResult:
    """
    Re-check every watched patient against Epic; auto-draft any detected changes.
    """
    return ScanResult(**scan_for_changes())


@router.get("/api/changes", response_model=ChangeInboxResponse)
def list_changes(
    _: dict[str, Any] = Depends(verify_clinician_token),
) -> ChangeInboxResponse:
    """
    The clinician inbox showing un-approved, change-detected drafts awaiting review.
    """
    items: list[ChangeInboxItem] = []
    for row in list_detected_drafts():
        diff_raw = (
            json.loads(row["condition_diff"])
            if row.get("condition_diff")
            else {"added": [], "removed": [], "ongoing": []}
        )
        conditions = (
            json.loads(row["conditions_json"]) if row.get("conditions_json") else []
        )
        items.append(
            ChangeInboxItem(
                comm_id=row["id"],
                patient_name=row.get("patient_name", ""),
                epic_patient_id=row.get("epic_patient_id", ""),
                target_audience=row.get("target_audience", "patient"),
                conditions=conditions,
                condition_diff=ConditionDiff(**diff_raw),
                ai_summary_text=row.get("ai_summary_text") or "",
                fhir_source=row.get("fhir_source", "sandbox"),
                detected_at=row.get("detected_at"),
            )
        )
    return ChangeInboxResponse(items=items)
