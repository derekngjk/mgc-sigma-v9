import json

import pytest
from fastapi.testclient import TestClient

from app.services import change_detection as cd

WATCHED = [
    {
        "patient_id": "p1",
        "epic_patient_id": "hx-oncology-001",
        "patient_name": "Tan Mei Ling",
    }
]


def _fhir(conditions: list[str]) -> dict:
    return {
        "patient_name": "Tan Mei Ling",
        "dob": "1980-01-01",
        "gender": "female",
        "nric": "",
        "conditions": conditions,
        "raw_fhir_json": json.dumps({"conditions": conditions}),
        "fhir_source": "sandbox",
    }


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch):
    """
    Stub every DB/LLM/FHIR dependency of the scan; tests set behaviour per case.
    """
    calls: dict[str, list] = {"inserted": [], "generated": []}

    monkeypatch.setattr(cd, "_list_watched_patients", lambda: list(WATCHED))
    monkeypatch.setattr(cd, "delivered_audiences", lambda pid: ["patient"])
    monkeypatch.setattr(cd, "has_open_detected_draft", lambda *a: False)

    def fake_insert(**kw):
        comm_id = f"c{len(calls['inserted'])}"
        calls["inserted"].append({"comm_id": comm_id, **kw})
        return comm_id

    def fake_generate(raw, audience, diff, length):
        calls["generated"].append({"audience": audience, "diff": diff})
        return f"Updated summary for {audience}."

    monkeypatch.setattr(cd, "insert_detected_draft", fake_insert)
    monkeypatch.setattr(cd, "update_communication", lambda comm_id, **kw: True)
    monkeypatch.setattr(cd, "generate_summary", fake_generate)
    return calls


# orchestration


def test_detects_change_and_autodrafts(wire, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cd, "fetch_patient_data", lambda _: _fhir(["Cancer", "Neutropenia"])
    )
    monkeypatch.setattr(
        cd, "latest_approved_for_patient", lambda pid: {"conditions_json": '["Cancer"]'}
    )

    result = cd.scan_for_changes()

    assert result["patients_scanned"] == 1
    assert result["patients_changed"] == 1
    assert result["drafts_created"] == 1
    change = result["changes"][0]
    assert change["added"] == ["Neutropenia"]
    assert change["drafts"][0]["generated"] is True
    assert len(wire["inserted"]) == 1
    assert len(wire["generated"]) == 1


def test_no_change_creates_no_draft(wire, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cd, "fetch_patient_data", lambda _: _fhir(["Cancer"]))
    monkeypatch.setattr(
        cd, "latest_approved_for_patient", lambda pid: {"conditions_json": '["Cancer"]'}
    )

    result = cd.scan_for_changes()

    assert result["patients_changed"] == 0
    assert result["drafts_created"] == 0
    assert wire["inserted"] == []


def test_dedup_skips_existing_detected_draft(
    wire, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cd, "fetch_patient_data", lambda _: _fhir(["Cancer", "Neutropenia"])
    )
    monkeypatch.setattr(
        cd, "latest_approved_for_patient", lambda pid: {"conditions_json": '["Cancer"]'}
    )
    monkeypatch.setattr(cd, "has_open_detected_draft", lambda *a: True)

    result = cd.scan_for_changes()

    assert result["patients_changed"] == 0  # change exists but already drafted
    assert wire["inserted"] == []


def test_llm_failure_still_creates_draft(wire, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.llm import LLMError

    monkeypatch.setattr(
        cd, "fetch_patient_data", lambda _: _fhir(["Cancer", "Neutropenia"])
    )
    monkeypatch.setattr(
        cd, "latest_approved_for_patient", lambda pid: {"conditions_json": '["Cancer"]'}
    )

    def boom(*a):
        raise LLMError("provider down")

    monkeypatch.setattr(cd, "generate_summary", boom)

    result = cd.scan_for_changes()

    assert result["drafts_created"] == 1
    assert result["changes"][0]["drafts"][0]["generated"] is False
    assert len(wire["inserted"]) == 1  # draft created despite generation failure


def test_one_draft_per_delivered_audience(
    wire, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        cd, "fetch_patient_data", lambda _: _fhir(["Cancer", "Neutropenia"])
    )
    monkeypatch.setattr(
        cd, "latest_approved_for_patient", lambda pid: {"conditions_json": '["Cancer"]'}
    )
    monkeypatch.setattr(cd, "delivered_audiences", lambda pid: ["patient", "spouse"])

    result = cd.scan_for_changes()

    assert result["drafts_created"] == 2
    audiences = {d["target_audience"] for d in result["changes"][0]["drafts"]}
    assert audiences == {"patient", "spouse"}


def test_fhir_error_is_recorded_not_raised(
    wire, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.fhir import FHIRError

    def unreachable(_):
        raise FHIRError("sandbox unreachable")

    monkeypatch.setattr(cd, "fetch_patient_data", unreachable)
    monkeypatch.setattr(cd, "latest_approved_for_patient", lambda pid: None)

    result = cd.scan_for_changes()

    assert result["patients_changed"] == 0
    assert len(result["errors"]) == 1
    assert "hx-oncology-001" in result["errors"][0]


# endpoints


def test_scan_disabled_without_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SCAN_TOKEN", raising=False)
    assert client.post("/api/changes/scan").status_code == 503


def test_scan_rejects_wrong_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCAN_TOKEN", "secret")
    resp = client.post("/api/changes/scan", headers={"X-Scan-Token": "wrong"})
    assert resp.status_code == 401


def test_scan_runs_with_correct_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCAN_TOKEN", "secret")
    monkeypatch.setattr(
        "app.routers.changes.scan_for_changes",
        lambda: {
            "patients_scanned": 1,
            "patients_changed": 1,
            "drafts_created": 1,
            "changes": [
                {
                    "patient_name": "Tan Mei Ling",
                    "epic_patient_id": "hx-oncology-001",
                    "added": ["Neutropenia"],
                    "removed": [],
                    "drafts": [
                        {
                            "comm_id": "c0",
                            "target_audience": "patient",
                            "generated": True,
                        }
                    ],
                }
            ],
            "errors": [],
        },
    )
    resp = client.post("/api/changes/scan", headers={"X-Scan-Token": "secret"})
    assert resp.status_code == 200
    assert resp.json()["drafts_created"] == 1


def test_inbox_lists_detected_drafts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.routers.changes.list_detected_drafts",
        lambda: [
            {
                "id": "c0",
                "patient_name": "Tan Mei Ling",
                "epic_patient_id": "hx-oncology-001",
                "target_audience": "patient",
                "conditions_json": '["Cancer", "Neutropenia"]',
                "condition_diff": '{"added": ["Neutropenia"], "removed": [], "ongoing": ["Cancer"]}',
                "ai_summary_text": "Updated summary.",
                "fhir_source": "sandbox",
                "detected_at": "2026-07-19T00:00:00Z",
            }
        ],
    )
    resp = client.get("/api/changes")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["condition_diff"]["added"] == ["Neutropenia"]
    assert items[0]["ai_summary_text"] == "Updated summary."
