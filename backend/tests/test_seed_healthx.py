"""Tests for the HealthX provisioning helpers (no network; no live-tenant access)."""

from typing import Any

import pytest

import seed_healthx as seed


@pytest.mark.parametrize("source, live_id, _label", seed.MOCK_LIVE_PATIENTS)
def test_rehost_mock_bundle_rewrites_ids_and_refs(source, live_id, _label) -> None:
    bundle = seed._rehost_mock_bundle(source, live_id)

    assert bundle["patient"]["id"] == live_id

    resources = [
        e["resource"]
        for key in ("conditions", "care_plans")
        for e in bundle[key]["entry"]
    ]
    assert resources, "expected at least one condition/careplan"
    ref = f"Patient/{live_id}"
    assert all(r["subject"]["reference"] == ref for r in resources)
    ids = [r["id"] for r in resources]
    assert len(ids) == len(set(ids))  # ids are unique
    assert all(rid.startswith(live_id) for rid in ids)


@pytest.mark.parametrize("source, live_id, _label", seed.MOCK_LIVE_PATIENTS)
def test_rehost_careplan_activities_have_status(source, live_id, _label) -> None:
    # FHIR R4B requires CarePlan.activity.detail.status (1..1); the mock omits it,
    # so the re-host must inject it or the Firely server rejects it with a 422.
    bundle = seed._rehost_mock_bundle(source, live_id)
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
