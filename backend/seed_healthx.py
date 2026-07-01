"""Provision synthetic FHIR R4B resources into the HealthX (HX-IS) tenant.

The HX-IS tenant ships empty: resources must be POSTed/PUT before any read or
search returns data. This one-off ops script upserts (idempotent PUT, so it is
safe to re-run) a small demo cohort:

  * the joinable real Synapxe patients (Aaron Koh/Lim/Teo) via synthea_to_fhir
  * the richer oncology narrative from mock_data/mock-oncology-123.json, re-hosted
    under a live-only id (hx-oncology-001) so it is fetched from the endpoint
    rather than the local mock fallback.

Resources are PUT in dependency order (Patients, then Conditions, then CarePlans)
so subject references resolve. Config is read from backend/.env.

Usage:
    uv run python seed_healthx.py            # provision against the live tenant
    uv run python seed_healthx.py --dry-run  # list resources, make no network calls
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Iterator

import httpx

from synthea_to_fhir import PATIENT_ALLOWLIST, build_all_bundles

MOCK_DATA_DIR: Path = Path(__file__).parent / "mock_data"
ONCOLOGY_SOURCE: Path = MOCK_DATA_DIR / "mock-oncology-123.json"
ONCOLOGY_LIVE_ID: str = "hx-oncology-001"

# (patient_id, display label) for everything this script provisions — handy for
# wiring the frontend selector and for docs.
LIVE_PATIENTS: list[tuple[str, str]] = [
    *[(pid, name) for pid, name in PATIENT_ALLOWLIST.items()],
    (ONCOLOGY_LIVE_ID, "Tan Mei Ling — Breast cancer, stage III"),
]


def _load_dotenv(path: Path) -> None:
    """Populate os.environ from a KEY=VALUE .env file (does not override existing)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


def _load_oncology_bundle() -> dict[str, Any]:
    """Re-host the oncology mock under ONCOLOGY_LIVE_ID (new ids + subject refs)."""
    raw = json.loads(ONCOLOGY_SOURCE.read_text(encoding="utf-8"))
    patient = dict(raw["patient"])
    patient["id"] = ONCOLOGY_LIVE_ID
    display = (patient.get("name") or [{}])[0].get("text", "")

    def _rehost(entries: list[dict[str, Any]], suffix: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for i, entry in enumerate(entries):
            resource = dict(entry["resource"])
            resource["id"] = f"{ONCOLOGY_LIVE_ID}-{suffix}-{i}"
            resource["subject"] = {
                "reference": f"Patient/{ONCOLOGY_LIVE_ID}",
                "display": display,
            }
            out.append({"resource": resource})
        return out

    return {
        "patient": patient,
        "conditions": {
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": _rehost(raw["conditions"]["entry"], "cond"),
        },
        "care_plans": {
            "resourceType": "Bundle",
            "type": "searchset",
            "entry": _rehost(raw["care_plans"]["entry"], "cp"),
        },
    }


def _iter_resources(bundles: dict[str, dict[str, Any]]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    """Yield (resourceType, id, resource) with all Patients before Condition/CarePlan."""
    for bundle in bundles.values():
        patient = bundle["patient"]
        yield "Patient", patient["id"], patient
    for bundle in bundles.values():
        for entry in bundle["conditions"]["entry"]:
            yield "Condition", entry["resource"]["id"], entry["resource"]
    for bundle in bundles.values():
        for entry in bundle["care_plans"]["entry"]:
            yield "CarePlan", entry["resource"]["id"], entry["resource"]


def _collect_bundles() -> dict[str, dict[str, Any]]:
    return {**build_all_bundles(), ONCOLOGY_LIVE_ID: _load_oncology_bundle()}


def main(argv: list[str]) -> int:
    _load_dotenv(Path(__file__).parent / ".env")
    resources = list(_iter_resources(_collect_bundles()))

    if "--dry-run" in argv:
        for rtype, rid, _ in resources:
            print(f"  PUT {rtype}/{rid}")
        print(f"total: {len(resources)} resources across {len(LIVE_PATIENTS)} patients")
        return 0

    base = os.getenv("FHIR_BASE_URL", "").rstrip("/")
    api_key = os.getenv("HEALTHX_API_KEY", "")
    if not base or "your-tenant-id" in base or not api_key:
        print("ERROR: set FHIR_BASE_URL and HEALTHX_API_KEY in backend/.env first.")
        return 1

    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/fhir+json",
        "Accept": "application/fhir+json",
    }
    ok = 0
    with httpx.Client(timeout=30.0, headers=headers) as client:
        for rtype, rid, resource in resources:
            resp = client.put(f"{base}/{rtype}/{rid}", content=json.dumps(resource))
            if resp.status_code in (200, 201):
                ok += 1
                print(f"[ok]   PUT {rtype}/{rid} -> {resp.status_code}")
            else:
                print(f"[FAIL] PUT {rtype}/{rid} -> {resp.status_code}")
                print(f"       {resp.text[:300]}")

    print(f"\n{ok}/{len(resources)} resources provisioned")
    return 0 if ok == len(resources) else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
