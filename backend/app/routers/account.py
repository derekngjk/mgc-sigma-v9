"""Portal-account endpoints: register, login, role-scoped report collection + view."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db import (
    create_portal_user,
    get_audio_url,
    get_patient_id_by_identity_hash,
    get_patient_name,
    get_portal_user,
    get_portal_user_by_email,
    get_read_comm_ids,
    get_role_report_for_user,
    list_role_reports,
    mark_report_read,
    set_audio_url,
    upload_audio,
)
from app.dependencies import verify_portal_token
from app.schemas import (
    VALID_LANGS,
    VALID_ROLES,
    AudioResponse,
    ConditionDiff,
    LoginRequest,
    PatientLoginResponse,
    RegisterRequest,
    ReportCard,
    ReportListResponse,
    ReportViewResponse,
)
from app.services.identity import (
    hash_password,
    identity_hash,
    issue_portal_token,
    verify_password,
)
from app.services.llm import LLMConfigError
from app.services.summaries import resolve_summary_text
from app.services.tts import generate_tts, split_sentences, strip_markdown

router = APIRouter()


def _validate_lang(lang: str) -> None:
    if lang not in VALID_LANGS:
        raise HTTPException(
            status_code=400, detail=f"lang must be one of: {sorted(VALID_LANGS)}"
        )


def _condition_diff(record: dict[str, Any]) -> ConditionDiff:
    diff_raw = (
        json.loads(record["condition_diff"])
        if record.get("condition_diff")
        else {"added": [], "removed": [], "ongoing": []}
    )
    return ConditionDiff(**diff_raw)


def _load_user(user_id: str) -> dict[str, Any]:
    """Resolve the portal user for a validated token, or 401 if it no longer exists."""
    user = get_portal_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    return user


@router.post("/api/account/register", response_model=PatientLoginResponse)
def register(req: RegisterRequest) -> PatientLoginResponse:
    if req.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400, detail=f"role must be one of: {sorted(VALID_ROLES)}"
        )
    email = req.email.strip().lower()
    if "@" not in email or len(req.password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Enter a valid email and a password of at least 6 characters",
        )

    patient_id = get_patient_id_by_identity_hash(
        identity_hash(req.patient_full_name, req.patient_nric)
    )
    if patient_id is None:
        raise HTTPException(
            status_code=404, detail="No patient found with those details"
        )
    if get_portal_user_by_email(email) is not None:
        raise HTTPException(status_code=409, detail="Email already registered")

    salt, pw_hash = hash_password(req.password)
    user_id = create_portal_user(email, pw_hash, salt, req.role, patient_id)
    return PatientLoginResponse(
        token=issue_portal_token(user_id),
        patient_name=get_patient_name(patient_id),
        role=req.role,
    )


@router.post("/api/account/login", response_model=PatientLoginResponse)
def login(req: LoginRequest) -> PatientLoginResponse:
    user = get_portal_user_by_email(req.email)
    if user is None or not verify_password(
        req.password, user["password_salt"], user["password_hash"]
    ):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return PatientLoginResponse(
        token=issue_portal_token(user["id"]),
        patient_name=get_patient_name(user["patient_id"]),
        role=user["role"],
    )


@router.get("/api/account/reports", response_model=ReportListResponse)
def list_reports(
    user_id: str = Depends(verify_portal_token),
) -> ReportListResponse:
    user = _load_user(user_id)
    cards = list_role_reports(user["patient_id"], user["role"])
    read_ids = get_read_comm_ids(user_id)
    reports = [ReportCard(**c, viewed=c["comm_id"] in read_ids) for c in cards]
    return ReportListResponse(
        patient_name=get_patient_name(user["patient_id"]),
        role=user["role"],
        unread=sum(1 for r in reports if not r.viewed),
        reports=reports,
    )


@router.get("/api/account/reports/{comm_id}", response_model=ReportViewResponse)
def view_report(
    comm_id: str,
    user_id: str = Depends(verify_portal_token),
    lang: str = Query(default="en"),
) -> ReportViewResponse:
    _validate_lang(lang)
    user = _load_user(user_id)
    record = get_role_report_for_user(comm_id, user["patient_id"], user["role"])
    if record is None:
        raise HTTPException(status_code=404, detail="Report not found")

    mark_report_read(user_id, comm_id)  # idempotent per (user, report)

    return ReportViewResponse(
        id=comm_id,
        patient_name=record["patient_name"],
        ai_summary_text=resolve_summary_text(comm_id, record["ai_summary_text"], lang),
        approved_at=record["approved_at"],
        condition_diff=_condition_diff(record),
        image_url=record.get("image_url"),
    )


@router.get("/api/account/reports/{comm_id}/audio", response_model=AudioResponse)
def report_audio(
    comm_id: str,
    user_id: str = Depends(verify_portal_token),
    lang: str = Query(default="en"),
) -> AudioResponse:
    _validate_lang(lang)
    user = _load_user(user_id)
    record = get_role_report_for_user(comm_id, user["patient_id"], user["role"])
    if record is None:
        raise HTTPException(status_code=404, detail="Report not found")

    summary_text = resolve_summary_text(comm_id, record["ai_summary_text"], lang)
    clean_text = strip_markdown(summary_text)
    sentences = split_sentences(clean_text)

    cached_url = get_audio_url(comm_id, lang)
    if cached_url:
        return AudioResponse(url=cached_url, sentences=sentences)

    try:
        audio_bytes = generate_tts(clean_text)
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"TTS generation failed: {exc}"
        ) from exc

    try:
        url = upload_audio(comm_id, lang, audio_bytes)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Audio upload failed: {exc}"
        ) from exc

    set_audio_url(comm_id, lang, url)
    return AudioResponse(url=url, sentences=sentences)
