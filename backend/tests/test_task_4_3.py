"""
Task 4.3 — Patient/Family Mobile Viewer (TDD).
Acceptance: GET /api/communications/{id} returns the approved summary for the
family viewer. Returns 404 for unknown IDs or unapproved (Draft) records.

Groups:
  A — Happy path
  B — Error paths
"""

import pytest
from fastapi.testclient import TestClient

import db
from main import app

APPROVED_TEXT = "Think of the cancer cells like weeds taking over a garden."


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    import main
    monkeypatch.setattr(main, "DB_PATH", db_path)
    db.init_db(db_path)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def approved_comm_id(client: TestClient) -> str:
    import main
    comm_id = db.create_communication(
        main.DB_PATH,
        patient_name="Elena Vasquez",
        raw_clinical_text='{"conditions": [], "care_plans": []}',
        epic_patient_id="mock-oncology-123",
        fhir_source="mock",
        conditions_json='["Acute myeloid leukaemia"]',
        condition_diff='{"added": [], "removed": [], "ongoing": ["Acute myeloid leukaemia"]}',
    )
    client.post(
        f"/api/communications/{comm_id}/approve",
        json={"ai_summary_text": APPROVED_TEXT},
    )
    return comm_id


# ── Group A: happy path ───────────────────────────────────────────────────────

def test_family_view_returns_200(client: TestClient, approved_comm_id: str) -> None:
    resp = client.get(f"/api/communications/{approved_comm_id}")
    assert resp.status_code == 200


def test_family_view_has_required_fields(client: TestClient, approved_comm_id: str) -> None:
    body = client.get(f"/api/communications/{approved_comm_id}").json()
    for field in ("id", "patient_name", "ai_summary_text", "approved_at", "condition_diff"):
        assert field in body, f"missing field: {field}"


def test_family_view_condition_diff_has_three_categories(
    client: TestClient, approved_comm_id: str
) -> None:
    body = client.get(f"/api/communications/{approved_comm_id}").json()
    diff = body["condition_diff"]
    for key in ("added", "removed", "ongoing"):
        assert key in diff, f"missing condition_diff key: {key}"


def test_family_view_returns_correct_summary_text(
    client: TestClient, approved_comm_id: str
) -> None:
    body = client.get(f"/api/communications/{approved_comm_id}").json()
    assert body["ai_summary_text"] == APPROVED_TEXT


# ── Group B: error paths ──────────────────────────────────────────────────────

def test_family_view_unknown_id_returns_404(client: TestClient) -> None:
    resp = client.get("/api/communications/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


def test_family_view_draft_record_returns_404(client: TestClient) -> None:
    import main
    comm_id = db.create_communication(
        main.DB_PATH,
        patient_name="Draft Patient",
        raw_clinical_text="{}",
        epic_patient_id="draft-patient",
        fhir_source="mock",
    )
    resp = client.get(f"/api/communications/{comm_id}")
    assert resp.status_code == 404


def test_error_body_has_detail_key(client: TestClient) -> None:
    body = client.get("/api/communications/00000000-0000-0000-0000-000000000000").json()
    assert "detail" in body
