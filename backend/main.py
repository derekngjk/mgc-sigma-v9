import json
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import (
    create_communication,
    get_communication,
    get_family_summary,
    get_latest_approved_communication,
    get_or_create_family,
    get_or_create_primary_member,
    get_translation,
    init_db,
    set_translation,
    update_communication,
)
from fhir import FHIRError, PatientNotFoundError, fetch_patient_data
from auth import verify_clinician_token
from llm import LLMConfigError, LLMError, generate_summary, translate_summary

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Only try to init if we have a DB URL, otherwise it might be a test environment
    if SUPABASE_DB_URL:
        init_db(SUPABASE_DB_URL)
    yield


app = FastAPI(title="MGC PoC API", version="0.1.0", lifespan=lifespan)

# CORS configuration
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ConditionDiff(BaseModel):
    added: list[str]
    removed: list[str]
    ongoing: list[str]


class PatientResponse(BaseModel):
    comm_id: str
    patient_name: str
    dob: str
    gender: str
    conditions: list[str]
    fhir_source: str
    condition_diff: ConditionDiff


_VALID_LENGTHS = {"short", "medium", "long"}


class GenerateRequest(BaseModel):
    comm_id: str
    target_audience: str = "family"
    length: str = "medium"


class GenerateResponse(BaseModel):
    comm_id: str
    ai_summary_text: str
    target_audience: str


class ApproveRequest(BaseModel):
    ai_summary_text: str


class ApproveResponse(BaseModel):
    id: str
    approved_at: str
    family_link: str


class FamilyViewResponse(BaseModel):
    id: str
    patient_name: str
    ai_summary_text: str
    approved_at: str
    condition_diff: ConditionDiff


_VALID_LANGS = {"en", "zh", "ms", "ta"}


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok", service="mgc-backend", version="0.1.0")


@app.get("/")
def root():
    return {"message": "MGC PoC API. See /health and /docs."}


@app.get("/api/patient/{epic_patient_id}", response_model=PatientResponse)
def get_patient(
    epic_patient_id: str,
    _: dict = Depends(verify_clinician_token),
) -> PatientResponse:
    try:
        data = fetch_patient_data(epic_patient_id)
    except PatientNotFoundError:
        raise HTTPException(status_code=404, detail="Patient not found in FHIR sandbox")
    except FHIRError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

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

    diff_json = diff.model_dump_json()

    comm_id = create_communication(
        patient_name=data["patient_name"],
        raw_clinical_text=data["raw_fhir_json"],
        epic_patient_id=epic_patient_id,
        fhir_source=data["fhir_source"],
        target_audience="family",
        conditions_json=json.dumps(data["conditions"]),
        condition_diff=diff_json,
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


@app.post("/api/generate", response_model=GenerateResponse)
def generate(
    req: GenerateRequest,
    _: dict = Depends(verify_clinician_token),
) -> GenerateResponse:
    if req.length not in _VALID_LENGTHS:
        raise HTTPException(
            status_code=400, detail=f"length must be one of: {sorted(_VALID_LENGTHS)}"
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
        raise HTTPException(status_code=503, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
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


@app.get("/api/communications/{comm_id}", response_model=FamilyViewResponse)
def get_family_view(
    comm_id: str,
    lang: str = Query(default="en"),
) -> FamilyViewResponse:
    if lang not in _VALID_LANGS:
        raise HTTPException(
            status_code=400, detail=f"lang must be one of: {sorted(_VALID_LANGS)}"
        )
    record = get_communication(comm_id)
    if record is None or record["status"] != "Approved":
        raise HTTPException(
            status_code=404, detail="Summary not found or not yet approved"
        )
    diff_raw = (
        json.loads(record["condition_diff"])
        if record.get("condition_diff")
        else {"added": [], "removed": [], "ongoing": []}
    )
    summary_text = record["ai_summary_text"]
    if lang != "en":
        cached = get_translation(comm_id, lang)
        if cached is not None:
            summary_text = cached
        else:
            try:
                summary_text = translate_summary(record["ai_summary_text"], lang)
            except LLMConfigError as exc:
                raise HTTPException(status_code=503, detail=str(exc))
            except LLMError as exc:
                raise HTTPException(status_code=502, detail=str(exc))
            set_translation(comm_id, lang, summary_text)
    return FamilyViewResponse(
        id=comm_id,
        patient_name=record["patient_name"],
        ai_summary_text=summary_text,
        approved_at=record["approved_at"],
        condition_diff=ConditionDiff(**diff_raw),
    )


@app.post("/api/communications/{comm_id}/approve", response_model=ApproveResponse)
def approve_communication(
    comm_id: str,
    req: ApproveRequest,
    _: dict = Depends(verify_clinician_token),
) -> ApproveResponse:
    record = get_communication(comm_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Communication record not found")
    update_communication(
        comm_id,
        ai_summary_text=req.ai_summary_text,
        status="Approved",
    )
    updated = get_communication(comm_id)
    patient_id = updated.get("patient_id", "")
    fid = get_or_create_family(patient_id)
    mid = get_or_create_primary_member(fid, updated.get("patient_name", ""))
    return ApproveResponse(
        id=comm_id,
        approved_at=updated["approved_at"],
        family_link=f"{frontend_origin}/family/{fid}/member/{mid}",
    )


@app.get(
    "/api/family/{family_id}/member/{member_id}", response_model=FamilyViewResponse
)
def get_family_member_view(
    family_id: str,
    member_id: str,
    lang: str = Query(default="en"),
) -> FamilyViewResponse:
    if lang not in _VALID_LANGS:
        raise HTTPException(
            status_code=400, detail=f"lang must be one of: {sorted(_VALID_LANGS)}"
        )
    record = get_family_summary(family_id, member_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail="Summary not found or not yet approved"
        )
    diff_raw = (
        json.loads(record["condition_diff"])
        if record.get("condition_diff")
        else {"added": [], "removed": [], "ongoing": []}
    )
    summary_text = record["ai_summary_text"]
    if lang != "en":
        cached = get_translation(record["id"], lang)
        if cached is not None:
            summary_text = cached
        else:
            try:
                summary_text = translate_summary(record["ai_summary_text"], lang)
            except LLMConfigError as exc:
                raise HTTPException(status_code=503, detail=str(exc))
            except LLMError as exc:
                raise HTTPException(status_code=502, detail=str(exc))
            set_translation(record["id"], lang, summary_text)
    return FamilyViewResponse(
        id=record["id"],
        patient_name=record["patient_name"],
        ai_summary_text=summary_text,
        approved_at=record["approved_at"],
        condition_diff=ConditionDiff(**diff_raw),
    )
