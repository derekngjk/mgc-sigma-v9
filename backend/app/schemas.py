"""Pydantic request/response models and request-validation constants."""

from pydantic import BaseModel

VALID_LENGTHS = {"short", "medium", "long"}
VALID_LANGS = {"en", "zh", "ms", "ta"}


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


class GenerateRequest(BaseModel):
    comm_id: str
    target_audience: str = "patient"
    length: str = "medium"
    # Optional: use second LLM instance to review the generated summary
    review: bool = False


class ReviewVerdict(BaseModel):
    verdict: str  # "ok" | "warnings" | "unavailable"
    unsupported_claims: list[str]
    omissions: list[str]
    risky_simplifications: list[str]
    note: str = ""


class GenerateResponse(BaseModel):
    comm_id: str
    ai_summary_text: str
    target_audience: str
    review: ReviewVerdict | None = None


class ApproveRequest(BaseModel):
    ai_summary_text: str
    generate_image: bool = False


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
    image_url: str | None = None


class AudioResponse(BaseModel):
    url: str
    sentences: list[str]
