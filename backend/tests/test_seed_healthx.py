"""Tests for the HealthX provisioning helpers (no network; no live-tenant access)."""

from typing import Any

import seed_healthx as seed


def test_load_oncology_bundle_rehosts_under_live_id() -> None:
    bundle = seed._load_oncology_bundle()

    assert bundle["patient"]["id"] == seed.ONCOLOGY_LIVE_ID

    resources = [
        e["resource"]
        for key in ("conditions", "care_plans")
        for e in bundle[key]["entry"]
    ]
    assert resources, "expected at least one condition/careplan"
    ref = f"Patient/{seed.ONCOLOGY_LIVE_ID}"
    assert all(r["subject"]["reference"] == ref for r in resources)
    ids = [r["id"] for r in resources]
    assert len(ids) == len(set(ids))  # ids are unique
    assert all(rid.startswith(seed.ONCOLOGY_LIVE_ID) for rid in ids)


def test_oncology_careplan_activities_have_status() -> None:
    # FHIR R4B requires CarePlan.activity.detail.status (1..1); the mock omits it,
    # so the re-host must inject it or the Firely server rejects it with a 422.
    bundle = seed._load_oncology_bundle()
    for entry in bundle["care_plans"]["entry"]:
        for activity in entry["resource"].get("activity", []):
            detail = activity.get("detail")
            if isinstance(detail, dict):
                assert detail.get("status"), "activity.detail.status must be set"


def test_iter_resources_puts_patients_before_children() -> None:
    bundles: dict[str, dict[str, Any]] = {
        "p1": {
            "patient": {"resourceType": "Patient", "id": "p1"},
            "conditions": {"entry": [{"resource": {"resourceType": "Condition", "id": "c1"}}]},
            "care_plans": {"entry": [{"resource": {"resourceType": "CarePlan", "id": "cp1"}}]},
        }
    }
    ordered = list(seed._iter_resources(bundles))
    types = [rtype for rtype, _, _ in ordered]

    assert types == ["Patient", "Condition", "CarePlan"]
    last_patient = max(i for i, t in enumerate(types) if t == "Patient")
    first_child = min(i for i, t in enumerate(types) if t != "Patient")
    assert last_patient < first_child
