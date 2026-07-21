"""
Simulate a clinician updating a patient's record in Epic. This writes to the live FHIR

Usage (config from backend/.env — FHIR_BASE_URL, HEALTHX_API_KEY):
    uv run python -m scripts.update_condition --patient hx-oncology-001 --list
    uv run python -m scripts.update_condition --patient hx-smoketest-001 \
        --create-patient --name "Smoke Test" --nric S9999999Z
    uv run python -m scripts.update_condition --patient hx-oncology-001 \
        --add "Febrile neutropenia" --code 409089005
    uv run python -m scripts.update_condition --patient hx-oncology-001 \
        --resolve "Febrile neutropenia"

Add → a new active Condition appears (change detection reports it as "added").
Resolve → an existing Condition flips to resolved, dropping out of the active search
(reported as "removed"). Only live (hx-*/UUID) patients are writable; the mock-* ids
are served from local files and cannot be changed this way.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from typing import Any

import httpx

# Importing settings loads backend/.env (app.config calls load_dotenv on import), so the
# script reads the same FHIR config as the app
from app.config import settings

_SNOMED = "http://snomed.info/sct"
_CLINICAL = "http://terminology.hl7.org/CodeSystem/condition-clinical"
_NRIC_TYPE = "http://terminology.hl7.org/CodeSystem/v2-0203"


def _client() -> tuple[httpx.Client, str]:
    base = settings.fhir_base_url.rstrip("/")
    api_key = settings.healthx_api_key
    if not base or "your-tenant-id" in base or not api_key:
        print("ERROR: set FHIR_BASE_URL and HEALTHX_API_KEY in backend/.env first.")
        raise SystemExit(1)
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/fhir+json",
        "Accept": "application/fhir+json",
    }
    return httpx.Client(timeout=30.0, headers=headers), base


def _search_conditions(
    client: httpx.Client, base: str, patient: str
) -> list[dict[str, Any]]:
    """
    Return all Condition resources for a patient (any clinical status).
    """
    resp = client.get(f"{base}/Condition", params={"patient": patient})
    resp.raise_for_status()
    bundle = resp.json()
    return [e["resource"] for e in bundle.get("entry", []) if e.get("resource")]


def _display(resource: dict[str, Any]) -> str:
    codings = resource.get("code", {}).get("coding", [])
    return (
        codings[0].get("display", "")
        if codings
        else resource.get("code", {}).get("text", "")
    )


def _status(resource: dict[str, Any]) -> str:
    codings = resource.get("clinicalStatus", {}).get("coding", [])
    return codings[0].get("code", "") if codings else ""


def cmd_create_patient(
    client: httpx.Client, base: str, patient: str, name: str, nric: str
) -> int:
    """
    PUT a throwaway Patient (idempotent on id) so conditions can be attached to it.

    An NRIC identifier is included when given, so the app's account-linking flow works
    for the test patient the same way it does for a seeded one.
    """
    identifier: list[dict[str, Any]] = []
    if nric:
        identifier.append(
            {
                "type": {"coding": [{"system": _NRIC_TYPE, "code": "NRIC"}]},
                "value": nric,
            }
        )
    resource = {
        "resourceType": "Patient",
        "id": patient,
        "identifier": identifier,
        "name": [{"text": name}],
        "gender": "unknown",
    }
    url = f"{base}/Patient/{patient}"
    resp = client.put(url, content=json.dumps(resource))
    if resp.status_code not in (200, 201):
        print(f"[FAIL] PUT {url} -> {resp.status_code}\n{resp.text[:300]}")
        return 2
    print(f"[ok] created patient {patient} ({name!r}) ({resp.status_code})")
    return 0


def cmd_list(client: httpx.Client, base: str, patient: str) -> int:
    conditions = _search_conditions(client, base, patient)
    if not conditions:
        print(f"No conditions found for {patient}.")
        return 0
    print(f"Conditions for {patient}:")
    for c in conditions:
        print(f"  [{_status(c) or '?':8}] {_display(c)}")
    return 0


def cmd_add(
    client: httpx.Client, base: str, patient: str, display: str, code: str
) -> int:
    coding: dict[str, str] = {"system": _SNOMED, "display": display}
    if code:
        coding["code"] = code
    resource = {
        "resourceType": "Condition",
        "id": f"{patient}-cond-{uuid.uuid4().hex[:8]}",
        "subject": {"reference": f"Patient/{patient}"},
        "clinicalStatus": {
            "coding": [{"system": _CLINICAL, "code": "active", "display": "Active"}]
        },
        "code": {"coding": [coding], "text": display},
    }
    url = f"{base}/Condition/{resource['id']}"
    resp = client.put(url, content=json.dumps(resource))
    if resp.status_code not in (200, 201):
        print(f"[FAIL] PUT {url} -> {resp.status_code}\n{resp.text[:300]}")
        return 2
    print(f"[ok] added active condition {display!r} to {patient} ({resp.status_code})")
    return 0


def cmd_resolve(client: httpx.Client, base: str, patient: str, display: str) -> int:
    target = next(
        (
            c
            for c in _search_conditions(client, base, patient)
            if _display(c).lower() == display.lower() and _status(c) == "active"
        ),
        None,
    )
    if target is None:
        print(f"[FAIL] no active condition matching {display!r} for {patient}.")
        return 2
    target["clinicalStatus"] = {
        "coding": [{"system": _CLINICAL, "code": "resolved", "display": "Resolved"}]
    }
    url = f"{base}/Condition/{target['id']}"
    resp = client.put(url, content=json.dumps(target))
    if resp.status_code not in (200, 201):
        print(f"[FAIL] PUT {url} -> {resp.status_code}\n{resp.text[:300]}")
        return 2
    print(f"[ok] resolved condition {display!r} for {patient} ({resp.status_code})")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Simulate an Epic condition change.")
    parser.add_argument(
        "--patient", required=True, help="epic_patient_id (live, e.g. hx-oncology-001)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list current conditions")
    group.add_argument(
        "--create-patient",
        action="store_true",
        help="create/replace a throwaway Patient (needs --name; --nric optional)",
    )
    group.add_argument("--add", metavar="DISPLAY", help="add a new active condition")
    group.add_argument(
        "--resolve", metavar="DISPLAY", help="resolve an active condition"
    )
    parser.add_argument("--code", default="", help="SNOMED code for --add (optional)")
    parser.add_argument("--name", default="", help="display name for --create-patient")
    parser.add_argument(
        "--nric", default="", help="NRIC for --create-patient (enables account linking)"
    )
    args = parser.parse_args(argv)

    if args.create_patient and not args.name:
        parser.error("--create-patient requires --name")

    client, base = _client()
    with client:
        if args.list:
            return cmd_list(client, base, args.patient)
        if args.create_patient:
            return cmd_create_patient(client, base, args.patient, args.name, args.nric)
        if args.add:
            return cmd_add(client, base, args.patient, args.add, args.code)
        return cmd_resolve(client, base, args.patient, args.resolve)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
