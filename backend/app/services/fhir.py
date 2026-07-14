"""FHIR R4B fetch + parse against the Synapxe HealthX sandbox, with a mock fallback."""

import json
from typing import Any

import httpx

from app.config import MOCK_DATA_DIR, settings

FHIR_BASE_URL: str = settings.fhir_base_url
HEALTHX_API_KEY: str = settings.healthx_api_key


class FHIRError(Exception):
    """Raised when an upstream FHIR call fails or returns unexpected data."""


class PatientNotFoundError(FHIRError):
    """Raised when the FHIR sandbox returns 404 for the requested patient ID."""


def fetch_patient_data(epic_patient_id: str) -> dict[str, Any]:
    """Return a normalised patient dict from the mock loader or the live sandbox.

    Keys: patient_name, dob, gender, conditions, raw_fhir_json, fhir_source.
    """
    mock_path = MOCK_DATA_DIR / f"{epic_patient_id}.json"
    if mock_path.exists():
        return load_mock_patient(epic_patient_id)
    raw = _fetch_from_sandbox(epic_patient_id)
    return {
        **_parse_fhir_bundle(raw),
        "raw_fhir_json": _serialise_clinical_json(raw),
        "fhir_source": "sandbox",
    }


def load_mock_patient(patient_id: str = "mock-oncology-123") -> dict[str, Any]:
    """Load and parse a mock patient JSON fixture from mock_data/."""
    path = MOCK_DATA_DIR / f"{patient_id}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise FHIRError(f"Failed to load mock data: {exc}") from exc
    return {
        **_parse_fhir_bundle(raw),
        "raw_fhir_json": _serialise_clinical_json(raw),
        "fhir_source": "mock",
    }


def _serialise_clinical_json(raw: dict[str, Any]) -> str:
    return json.dumps(
        {
            "gender": raw.get("patient", {}).get("gender"),
            "conditions": raw.get("conditions"),
            "care_plans": raw.get("care_plans"),
            "observations": raw.get("observations"),
        },
        separators=(",", ":"),
    )


def _fetch_from_sandbox(patient_id: str) -> dict[str, Any]:
    """Make four synchronous FHIR R4B calls against the Synapxe HealthX sandbox."""
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

            observation_resp = client.get(
                f"{base}/Observation",
                params={"patient": patient_id},
            )
            if observation_resp.status_code != 200:
                raise FHIRError(
                    f"Observation.Search returned {observation_resp.status_code}"
                )

    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise FHIRError(f"FHIR sandbox unreachable: {exc}") from exc

    return {
        "patient": patient_resp.json(),
        "conditions": condition_resp.json(),
        "care_plans": care_plan_resp.json(),
        "observations": observation_resp.json(),
    }


def _extract_nric(patient: dict[str, Any]) -> str:
    """Return the patient's NRIC/FIN from Patient.identifier, or '' if absent.

    Matches on the identifier type code (NRIC) or an NRIC system URI, so it works
    for both the mock fixtures and Synapxe-seeded records.
    """
    for identifier in patient.get("identifier", []) or []:
        codings = (identifier.get("type") or {}).get("coding", []) or []
        type_codes = {(c.get("code") or "").upper() for c in codings}
        system = (identifier.get("system") or "").upper()
        if "NRIC" in type_codes or "FIN" in type_codes or "NRIC" in system:
            value = (identifier.get("value") or "").strip()
            if value:
                return value
    return ""


def _parse_fhir_bundle(raw: dict[str, Any]) -> dict[str, Any]:
    """Extract patient_name, dob, gender, nric, and active conditions from a FHIR bundle.

    Missing optional fields return empty string / empty list rather than raising.
    """
    patient = raw.get("patient", {})

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
    nric: str = _extract_nric(patient)

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
        "nric": nric,
        "conditions": conditions,
    }
