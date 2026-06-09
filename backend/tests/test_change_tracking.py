"""
Condition change tracking — cross-cutting feature (pre-Task 4.3).

Groups:
  A — DB layer: get_latest_approved_communication
  B — Route integration: diff computed and stored on GET /api/patient/{id}
  C — LLM prompt: condition_diff included in generate_summary prompt
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import db
from main import app


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path: pytest.TempPathFactory) -> str:
    path = str(tmp_path / "test.db")
    db.init_db(path)
    return path


@pytest.fixture
def client(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    import main
    monkeypatch.setattr(main, "DB_PATH", db_path)
    db.init_db(db_path)
    with TestClient(app) as c:
        yield c


def _make_mock_fhir(conditions: list[str]) -> dict:
    """Return a minimal FHIR-shaped dict that fhir.py will accept."""
    return {
        "patient_name": "Elena Vasquez",
        "dob": "1980-01-01",
        "gender": "female",
        "conditions": conditions,
        "raw_fhir_json": json.dumps({"conditions": conditions}),
        "fhir_source": "mock",
    }


# ── Group A: DB layer ─────────────────────────────────────────────────────────

def test_get_latest_approved_returns_none_when_no_records(db_path: str) -> None:
    result = db.get_latest_approved_communication(db_path, "patient-xyz")
    assert result is None


def test_get_latest_approved_returns_none_when_only_draft(db_path: str) -> None:
    db.create_communication(
        db_path,
        patient_name="Test Patient",
        raw_clinical_text="{}",
        epic_patient_id="patient-xyz",
    )
    result = db.get_latest_approved_communication(db_path, "patient-xyz")
    assert result is None


def test_get_latest_approved_returns_approved_record(db_path: str) -> None:
    comm_id = db.create_communication(
        db_path,
        patient_name="Test Patient",
        raw_clinical_text="{}",
        epic_patient_id="patient-xyz",
    )
    db.update_communication(db_path, comm_id, status="Approved")
    result = db.get_latest_approved_communication(db_path, "patient-xyz")
    assert result is not None
    assert result["id"] == comm_id
    assert result["status"] == "Approved"


def test_get_latest_approved_returns_most_recent_when_multiple(db_path: str) -> None:
    comm_id1 = db.create_communication(
        db_path,
        patient_name="Test Patient",
        raw_clinical_text="{}",
        epic_patient_id="patient-xyz",
    )
    db.update_communication(db_path, comm_id1, status="Approved")

    comm_id2 = db.create_communication(
        db_path,
        patient_name="Test Patient",
        raw_clinical_text="{}",
        epic_patient_id="patient-xyz",
    )
    db.update_communication(db_path, comm_id2, status="Approved")

    result = db.get_latest_approved_communication(db_path, "patient-xyz")
    assert result is not None
    assert result["id"] == comm_id2


# ── Group B: Route integration ────────────────────────────────────────────────

CONDITIONS_A = ["Acute myeloid leukaemia", "Anaemia"]
CONDITIONS_B = ["Acute myeloid leukaemia", "Neutropenia"]  # Anaemia removed, Neutropenia added


def test_first_fetch_all_conditions_are_ongoing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main
    monkeypatch.setattr(main, "fetch_patient_data", lambda _: _make_mock_fhir(CONDITIONS_A))
    resp = client.get("/api/patient/test-patient-001")
    assert resp.status_code == 200
    diff = resp.json()["condition_diff"]
    assert sorted(diff["ongoing"]) == sorted(CONDITIONS_A)
    assert diff["added"] == []
    assert diff["removed"] == []


def test_second_fetch_detects_new_condition(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main

    monkeypatch.setattr(main, "fetch_patient_data", lambda _: _make_mock_fhir(CONDITIONS_A))
    resp1 = client.get("/api/patient/test-patient-001")
    comm_id1 = resp1.json()["comm_id"]
    client.post(
        f"/api/communications/{comm_id1}/approve",
        json={"ai_summary_text": "First report."},
    )

    monkeypatch.setattr(main, "fetch_patient_data", lambda _: _make_mock_fhir(CONDITIONS_B))
    resp2 = client.get("/api/patient/test-patient-001")
    diff = resp2.json()["condition_diff"]
    assert "Neutropenia" in diff["added"]


def test_second_fetch_detects_resolved_condition(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main

    monkeypatch.setattr(main, "fetch_patient_data", lambda _: _make_mock_fhir(CONDITIONS_A))
    resp1 = client.get("/api/patient/test-patient-001")
    comm_id1 = resp1.json()["comm_id"]
    client.post(
        f"/api/communications/{comm_id1}/approve",
        json={"ai_summary_text": "First report."},
    )

    monkeypatch.setattr(main, "fetch_patient_data", lambda _: _make_mock_fhir(CONDITIONS_B))
    resp2 = client.get("/api/patient/test-patient-001")
    diff = resp2.json()["condition_diff"]
    assert "Anaemia" in diff["removed"]


def test_second_fetch_ongoing_is_intersection(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main

    monkeypatch.setattr(main, "fetch_patient_data", lambda _: _make_mock_fhir(CONDITIONS_A))
    resp1 = client.get("/api/patient/test-patient-001")
    comm_id1 = resp1.json()["comm_id"]
    client.post(
        f"/api/communications/{comm_id1}/approve",
        json={"ai_summary_text": "First report."},
    )

    monkeypatch.setattr(main, "fetch_patient_data", lambda _: _make_mock_fhir(CONDITIONS_B))
    resp2 = client.get("/api/patient/test-patient-001")
    diff = resp2.json()["condition_diff"]
    assert "Acute myeloid leukaemia" in diff["ongoing"]


def test_diff_stored_in_db(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main

    monkeypatch.setattr(main, "fetch_patient_data", lambda _: _make_mock_fhir(CONDITIONS_A))
    resp = client.get("/api/patient/test-patient-001")
    comm_id = resp.json()["comm_id"]
    record = db.get_communication(main.DB_PATH, comm_id)
    assert record is not None
    assert record["condition_diff"] is not None
    stored = json.loads(record["condition_diff"])
    assert "added" in stored and "removed" in stored and "ongoing" in stored


def test_conditions_json_stored_in_db(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import main

    monkeypatch.setattr(main, "fetch_patient_data", lambda _: _make_mock_fhir(CONDITIONS_A))
    resp = client.get("/api/patient/test-patient-001")
    comm_id = resp.json()["comm_id"]
    record = db.get_communication(main.DB_PATH, comm_id)
    assert record is not None
    stored = json.loads(record["conditions_json"])
    assert sorted(stored) == sorted(CONDITIONS_A)


# ── Group C: LLM prompt ───────────────────────────────────────────────────────

def test_generate_summary_includes_new_condition_in_prompt() -> None:
    from llm import generate_summary

    captured: list[str] = []

    def fake_llm(prompt: str) -> str:
        captured.append(prompt)
        return "Summary."

    with patch("llm._call_llm", fake_llm):
        generate_summary(
            raw_clinical_text="{}",
            target_audience="family",
            condition_diff={"added": ["Neutropenia"], "removed": [], "ongoing": []},
        )

    assert "Neutropenia" in captured[0]
    assert "New" in captured[0] or "new" in captured[0]


def test_generate_summary_includes_removed_condition_in_prompt() -> None:
    from llm import generate_summary

    captured: list[str] = []

    def fake_llm(prompt: str) -> str:
        captured.append(prompt)
        return "Summary."

    with patch("llm._call_llm", fake_llm):
        generate_summary(
            raw_clinical_text="{}",
            target_audience="family",
            condition_diff={"added": [], "removed": ["Anaemia"], "ongoing": []},
        )

    assert "Anaemia" in captured[0]
    assert "Resolved" in captured[0] or "resolved" in captured[0]


def test_generate_summary_includes_ongoing_condition_in_prompt() -> None:
    from llm import generate_summary

    captured: list[str] = []

    def fake_llm(prompt: str) -> str:
        captured.append(prompt)
        return "Summary."

    with patch("llm._call_llm", fake_llm):
        generate_summary(
            raw_clinical_text="{}",
            target_audience="family",
            condition_diff={
                "added": [],
                "removed": [],
                "ongoing": ["Acute myeloid leukaemia"],
            },
        )

    assert "Acute myeloid leukaemia" in captured[0]


def test_generate_summary_no_changes_section_when_no_added_or_removed() -> None:
    from llm import generate_summary

    captured: list[str] = []

    def fake_llm(prompt: str) -> str:
        captured.append(prompt)
        return "Summary."

    with patch("llm._call_llm", fake_llm):
        generate_summary(
            raw_clinical_text="{}",
            target_audience="family",
            condition_diff={
                "added": [],
                "removed": [],
                "ongoing": ["Acute myeloid leukaemia"],
            },
        )

    assert "Changes since" not in captured[0]
