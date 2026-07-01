import json
import os
from pathlib import Path
from typing import Any

import httpx

# Synapxe HealthX Innovation Sandbox (HX-IS) — FHIR R4B endpoint.
# The tenant ID is embedded in the URL path; obtain both the URL and the API
# key from your HX-IS API Portal application (https://innovation.healthx.sg/).
FHIR_BASE_URL: str = os.getenv(
    "FHIR_BASE_URL",
    "https://api.healthx.sg/fhir/r4b/your-tenant-id",
)
# Per-tenant API key issued by the HealthX API Portal, sent as the `x-api-key`
# header. Leave empty to make unauthenticated requests (only the mock fallback
# path works without a key).
HEALTHX_API_KEY: str = os.getenv("HEALTHX_API_KEY", "")
MOCK_DATA_DIR: Path = Path(__file__).parent / "mock_data"


# ── exceptions ────────────────────────────────────────────────────────────────


class FHIRError(Exception):
    """Raised when an upstream FHIR call fails or returns unexpected data."""


class PatientNotFoundError(FHIRError):
    """Raised when the FHIR sandbox returns 404 for the requested patient ID."""


# ── public API ────────────────────────────────────────────────────────────────


def fetch_patient_data(epic_patient_id: str) -> dict[str, Any]:
    """Entry point for the route handler.

    Dispatches to the mock loader or the live sandbox, then returns a
    normalised dict with keys:
        patient_name, dob, gender, conditions, raw_fhir_json, fhir_source
    """
    mock_path = MOCK_DATA_DIR / f"{epic_patient_id}.json"
    if mock_path.exists():
        return load_mock_patient(epic_patient_id)
    raw = _fetch_from_sandbox(epic_patient_id)
    parsed = _parse_fhir_bundle(raw)
    return {
        **parsed,
        "raw_fhir_json": json.dumps(
            {"conditions": raw["conditions"], "care_plans": raw["care_plans"]},
            separators=(",", ":"),
        ),
        "fhir_source": "sandbox",
    }


def load_mock_patient(patient_id: str = "mock-oncology-123") -> dict[str, Any]:
    """Load and parse a mock patient JSON fixture from mock_data/."""
    path = MOCK_DATA_DIR / f"{patient_id}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise FHIRError(f"Failed to load mock data: {exc}") from exc
    parsed = _parse_fhir_bundle(raw)
    return {
        **parsed,
        "raw_fhir_json": json.dumps(
            {"conditions": raw["conditions"], "care_plans": raw["care_plans"]},
            separators=(",", ":"),
        ),
        "fhir_source": "mock",
    }


# ── internal helpers ──────────────────────────────────────────────────────────


def _fetch_from_sandbox(patient_id: str) -> dict[str, Any]:
    """Make three synchronous FHIR R4B calls against the Synapxe HealthX sandbox."""
    base = FHIR_BASE_URL.rstrip("/")
    timeout = 10.0
    headers: dict[str, str] = {}
    if HEALTHX_API_KEY:
        headers["x-api-key"] = HEALTHX_API_KEY
    try:
        with httpx.Client(timeout=timeout, headers=headers) as client:
            patient_resp = client.get(f"{base}/Patient/{patient_id}")
            if patient_resp.status_code == 404:
                raise PatientNotFoundError(
                    f"Patient {patient_id!r} not found in FHIR sandbox"
                )
            if patient_resp.status_code != 200:
                raise FHIRError(f"Patient.Read returned {patient_resp.status_code}")

            condition_resp = client.get(
                f"{base}/Condition",
                params={"patient": patient_id, "clinical-status": "active"},
            )
            if condition_resp.status_code != 200:
                raise FHIRError(
                    f"Condition.Search returned {condition_resp.status_code}"
                )

            care_plan_resp = client.get(
                f"{base}/CarePlan",
                params={"patient": patient_id, "status": "active"},
            )
            if care_plan_resp.status_code != 200:
                raise FHIRError(
                    f"CarePlan.Search returned {care_plan_resp.status_code}"
                )

    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise FHIRError(f"FHIR sandbox unreachable: {exc}") from exc

    return {
        "patient": patient_resp.json(),
        "conditions": condition_resp.json(),
        "care_plans": care_plan_resp.json(),
    }


def _parse_fhir_bundle(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract structured fields from a raw FHIR bundle dict.

    Returns: patient_name, dob, gender, conditions (active only).
    Missing optional fields return empty string / empty list rather than raising.
    """
    patient = raw.get("patient", {})

    # Patient name: prefer name[0].text, fall back to given[0] + family
    patient_name = ""
    names = patient.get("name", [])
    if names:
        first = names[0]
        patient_name = first.get("text", "").strip()
        if not patient_name:
            given = (first.get("given") or [""])[0]
            family = first.get("family", "")
            patient_name = f"{given} {family}".strip()

    dob: str = patient.get("birthDate", "")
    gender: str = patient.get("gender", "")

    # Active conditions: code.coding[0].display
    conditions: list[str] = []
    for entry in raw.get("conditions", {}).get("entry", []):
        resource = entry.get("resource", {})
        status_codings = resource.get("clinicalStatus", {}).get("coding", [])
        if not status_codings or status_codings[0].get("code") != "active":
            continue
        codings = resource.get("code", {}).get("coding", [])
        display = codings[0].get("display", "") if codings else ""
        if display:
            conditions.append(display)

    return {
        "patient_name": patient_name,
        "dob": dob,
        "gender": gender,
        "conditions": conditions,
    }
