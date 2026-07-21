"""Pydantic request/response models and request-validation constants."""

from pydantic import BaseModel

VALID_LENGTHS = {"short", "medium", "long"}
VALID_LANGS = {"en", "zh", "ms", "ta"}
# Portal roles are exactly the report target_audience values.
VALID_ROLES = {"patient", "spouse", "child", "caregiver"}


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
    patient_name: str
    delivered: bool


class ReportViewResponse(BaseModel):
    id: str
    patient_name: str
    ai_summary_text: str
    approved_at: str
    condition_diff: ConditionDiff
    image_url: str | None = None


class AudioResponse(BaseModel):
    url: str
    sentences: list[str]


class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str
    patient_full_name: str
    patient_nric: str


class LoginRequest(BaseModel):
    email: str
    password: str


class PortalSession(BaseModel):
    token: str
    patient_name: str
    role: str


class ReportCard(BaseModel):
    comm_id: str
    target_audience: str
    approved_at: str | None = None
    delivered_at: str | None = None
    viewed: bool
    has_image: bool


class ReportListResponse(BaseModel):
    patient_name: str
    role: str
    unread: int
    reports: list[ReportCard]


# automated change detection


class DetectedDraft(BaseModel):
    comm_id: str
    target_audience: str
    generated: bool  # False if the summary auto-generation failed (draft still created)


class DetectedChange(BaseModel):
    patient_name: str
    epic_patient_id: str
    added: list[str]
    removed: list[str]
    drafts: list[DetectedDraft]


class ScanResult(BaseModel):
    patients_scanned: int
    patients_changed: int
    drafts_created: int
    changes: list[DetectedChange]
    errors: list[str]


class ChangeInboxItem(BaseModel):
    comm_id: str
    patient_name: str
    epic_patient_id: str
    target_audience: str
    conditions: list[str]
    condition_diff: ConditionDiff
    ai_summary_text: str
    fhir_source: str
    detected_at: str | None = None


class ChangeInboxResponse(BaseModel):
    items: list[ChangeInboxItem]
