import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import create_communication, get_communication, init_db, update_communication
from fhir import FHIRError, PatientNotFoundError, fetch_patient_data
from llm import LLMConfigError, LLMError, generate_summary

DB_PATH = os.getenv("DB_PATH", "mgc.db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(DB_PATH)
    yield


app = FastAPI(title="MGC PoC API", version="0.1.0", lifespan=lifespan)

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin, "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── request / response models ─────────────────────────────────────────────────

class PatientResponse(BaseModel):
    epic_patient_id: str
    patient_name: str
    dob: str
    gender: str
    conditions: list[str]
    comm_id: str
    fhir_source: str


class GenerateRequest(BaseModel):
    comm_id: str
    target_audience: str = "family"


class GenerateResponse(BaseModel):
    comm_id: str
    ai_summary_text: str
    target_audience: str


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "mgc-backend", "version": "0.1.0"}


@app.get("/")
def root():
    return {"message": "MGC PoC API. See /health and /docs."}


@app.get("/api/patient/{epic_patient_id}", response_model=PatientResponse)
def get_patient(epic_patient_id: str) -> PatientResponse:
    try:
        data = fetch_patient_data(epic_patient_id)
    except PatientNotFoundError:
        raise HTTPException(status_code=404, detail="Patient not found in FHIR sandbox")
    except FHIRError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    comm_id = create_communication(
        DB_PATH,
        patient_name=data["patient_name"],
        raw_clinical_text=data["raw_fhir_json"],
        epic_patient_id=epic_patient_id,
        fhir_source=data["fhir_source"],
        target_audience="family",
    )
    return PatientResponse(
        epic_patient_id=epic_patient_id,
        patient_name=data["patient_name"],
        dob=data["dob"],
        gender=data["gender"],
        conditions=data["conditions"],
        comm_id=comm_id,
        fhir_source=data["fhir_source"],
    )


@app.post("/api/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    record = get_communication(DB_PATH, req.comm_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Communication record not found")
    try:
        summary = generate_summary(record["raw_clinical_text"], req.target_audience)
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    update_communication(
        DB_PATH, req.comm_id,
        ai_summary_text=summary,
        target_audience=req.target_audience,
    )
    return GenerateResponse(
        comm_id=req.comm_id,
        ai_summary_text=summary,
        target_audience=req.target_audience,
    )
