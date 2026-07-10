"""Convert Synthea CSV rows (SyntheticPatientRecords/) into FHIR R4B resources.

The raw CSVs delivered by Synapxe are Windows-CRLF and heavily padded with
empty rows; only a handful of patients have joinable Patient+Condition+CarePlan
data (see memory/synthetic-patient-records.md). This module reads those CSVs and
emits FHIR R4B resources in the same ``{patient, conditions, care_plans}`` shape
that :func:`fhir._parse_fhir_bundle` consumes, so the seeded records flow through
the existing pipeline unchanged.

Clinical status is faithful to the source: a Condition/CarePlan is ``active``
only when its STOP column is empty, otherwise ``resolved`` / ``completed``.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from app.config import SYNTHEA_DIR

SNOMED_SYSTEM = "http://snomed.info/sct"
NRIC_SYSTEM = "https://www.moh.gov.sg/NRIC"
CLINICAL_STATUS_SYSTEM = "http://terminology.hl7.org/CodeSystem/condition-clinical"

# Patients with rich, joinable records (the only ones worth provisioning).
PATIENT_ALLOWLIST: dict[str, str] = {
    "1d604da9-9a81-4ba9-80c2-de3375d59b40": "Aaron Koh",
    "034e9e3b-2def-4559-bb2a-7850888ae060": "Aaron Lim",
    "10339b10-3cd1-4ac3-ac13-ec26728cb592": "Aaron Teo",
}


# ── low-level readers ─────────────────────────────────────────────────────────


def _read_rows(base_dir: Path, filename: str) -> list[dict[str, str]]:
    """Read a Synthea CSV, dropping padding rows (every value blank).

    ``utf-8-sig`` strips the BOM on patients.csv; ``csv`` handles the CRLF.
    """
    path = base_dir / filename
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows: list[dict[str, str]] = []
        for row in reader:
            values = [(v or "").strip() for v in row.values()]
            if not any(values):
                continue  # padding row
            rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})
        return rows


def _to_iso_date(dmy: str) -> str:
    """Convert Synthea ``D/M/YYYY`` to FHIR ``YYYY-MM-DD``; passthrough if unparseable."""
    dmy = (dmy or "").strip()
    if not dmy:
        return ""
    parts = dmy.split("/")
    if len(parts) != 3:
        return dmy
    day, month, year = parts
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


# ── resource builders ─────────────────────────────────────────────────────────


def _build_patient(row: dict[str, str]) -> dict[str, Any]:
    given = row.get("FIRST", "")
    family = row.get("LAST", "")
    patient: dict[str, Any] = {
        "resourceType": "Patient",
        "id": row["Id"],
        "name": [
            {
                "use": "official",
                "text": row.get("FULL NAME", "").strip() or f"{given} {family}".strip(),
                "family": family,
                "given": [given] if given else [],
            }
        ],
        "gender": "male" if row.get("GENDER", "").upper() == "M" else "female",
        "birthDate": _to_iso_date(row.get("BIRTHDATE", "")),
    }
    nric = row.get("NRIC", "").strip()
    if nric:
        patient["identifier"] = [{"system": NRIC_SYSTEM, "value": nric}]
    return patient


def _build_condition(patient_id: str, index: int, row: dict[str, str]) -> dict[str, Any]:
    resolved = bool(row.get("STOP", "").strip())
    condition: dict[str, Any] = {
        "resourceType": "Condition",
        "id": f"{patient_id}-cond-{index}",
        "subject": {"reference": f"Patient/{patient_id}"},
        "clinicalStatus": {
            "coding": [
                {
                    "system": CLINICAL_STATUS_SYSTEM,
                    "code": "resolved" if resolved else "active",
                    "display": "Resolved" if resolved else "Active",
                }
            ]
        },
        "code": {
            "coding": [
                {
                    "system": SNOMED_SYSTEM,
                    "code": row.get("CODE", ""),
                    "display": row.get("DESCRIPTION", ""),
                }
            ],
            "text": row.get("DESCRIPTION", ""),
        },
    }
    encounter = row.get("ENCOUNTER", "")
    if encounter:
        condition["encounter"] = {"reference": f"Encounter/{encounter}"}

    onset = _to_iso_date(row.get("START", ""))
    if onset:
        condition["onsetDateTime"] = onset
    abatement = _to_iso_date(row.get("STOP", ""))
    if abatement:
        condition["abatementDateTime"] = abatement
    return condition


def _build_careplan(patient_id: str, index: int, row: dict[str, str]) -> dict[str, Any]:
    active = not row.get("STOP", "").strip()
    reason = row.get("REASONDESCRIPTION", "").strip()
    description = row.get("DESCRIPTION", "")
    if reason:
        description = f"{description} — for {reason}"
    care_plan: dict[str, Any] = {
        "resourceType": "CarePlan",
        "id": f"{patient_id}-cp-{index}",
        "subject": {"reference": f"Patient/{patient_id}"},
        "status": "active" if active else "completed",
        "intent": "plan",
        "title": row.get("DESCRIPTION", ""),
        "description": description,
        "category": [
            {
                "coding": [
                    {
                        "system": SNOMED_SYSTEM,
                        "code": row.get("CODE", ""),
                        "display": row.get("DESCRIPTION", ""),
                    }
                ],
                "text": row.get("DESCRIPTION", ""),
            }
        ],
    }
    encounter = row.get("ENCOUNTER", "")
    if encounter:
        care_plan["encounter"] = {"reference": f"Encounter/{encounter}"}

    period: dict[str, str] = {}
    start = _to_iso_date(row.get("START", ""))
    end = _to_iso_date(row.get("STOP", ""))
    if start:
        period["start"] = start
    if end:
        period["end"] = end
    if period:
        care_plan["period"] = period
    return care_plan


def _build_observation(patient_id: str, index: int, row: dict[str, str]) -> dict[str, Any]:
    observation: dict[str, Any] = {
        "resourceType": "Observation",
        "id": f"{patient_id}-obs-{index}",
        "status": "final",
        "subject": {"reference": f"Patient/{patient_id}"},
        "code": {
            "coding": [
                {
                    "system": "http://loinc.org",
                    "code": row.get("CODE", ""),
                    "display": row.get("DESCRIPTION", ""),
                }
            ],
            "text": row.get("DESCRIPTION", ""),
        },
    }
    date = row.get("DATE", "")
    if date:
        observation["effectiveDateTime"] = date

    encounter = row.get("ENCOUNTER", "")
    if encounter:
        observation["encounter"] = {"reference": f"Encounter/{encounter}"}

    value = row.get("VALUE", "")
    units = row.get("UNITS", "")
    val_type = row.get("TYPE", "")
    
    if val_type == "numeric" and value:
        try:
            val_float = float(value)
            observation["valueQuantity"] = {
                "value": val_float,
                "unit": units,
                "system": "http://unitsofmeasure.org",
                "code": units
            }
        except ValueError:
            observation["valueString"] = value
    elif value:
        observation["valueString"] = value

    return observation


# ── public API ────────────────────────────────────────────────────────────────


def build_patient_bundle(patient_id: str, base_dir: Path = SYNTHEA_DIR) -> dict[str, Any]:
    """Build the ``{patient, conditions, care_plans}`` resource set for one patient.

    ``conditions`` / ``care_plans`` are FHIR searchset Bundles so the result is
    shaped exactly like a live three-call fetch. Raises KeyError if the patient
    is absent from patients.csv.
    """
    patient_rows = {r["Id"]: r for r in _read_rows(base_dir, "patients.csv")}
    if patient_id not in patient_rows:
        raise KeyError(f"patient {patient_id!r} not found in patients.csv")

    conditions = [
        _build_condition(patient_id, i, r)
        for i, r in enumerate(
            (r for r in _read_rows(base_dir, "conditions.csv") if r.get("PATIENT") == patient_id)
        )
    ]
    care_plans = [
        _build_careplan(patient_id, i, r)
        for i, r in enumerate(
            (r for r in _read_rows(base_dir, "careplans.csv") if r.get("PATIENT") == patient_id)
        )
    ]
    observations = [
        _build_observation(patient_id, i, r)
        for i, r in enumerate(
            (r for r in _read_rows(base_dir, "observations.csv") if r.get("PATIENT") == patient_id)
        )
    ]
    return {
        "patient": _build_patient(patient_rows[patient_id]),
        "conditions": {
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [{"resource": c} for c in conditions],
        },
        "care_plans": {
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [{"resource": c} for c in care_plans],
        },
        "observations": {
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": [{"resource": o} for o in observations],
        },
    }


def build_all_bundles(base_dir: Path = SYNTHEA_DIR) -> dict[str, dict[str, Any]]:
    """Build resource sets for every allow-listed patient, keyed by patient id."""
    return {pid: build_patient_bundle(pid, base_dir) for pid in PATIENT_ALLOWLIST}


if __name__ == "__main__":
    import json

    for pid, name in PATIENT_ALLOWLIST.items():
        bundle = build_patient_bundle(pid)
        n_cond = len(bundle["conditions"]["entry"])
        n_cp = len(bundle["care_plans"]["entry"])
        n_obs = len(bundle["observations"]["entry"])
        print(f"{name} ({pid}): {n_cond} conditions, {n_cp} care plans, {n_obs} observations")
        print(json.dumps(bundle, indent=2))
