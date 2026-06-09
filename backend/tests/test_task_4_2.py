"""
Task 4.2 — Approval + Magic Link Flow (TDD).
Acceptance: POST /api/communications/{id}/approve saves the edited summary,
flips status to Approved, and returns a family magic link.

Groups:
  A — Happy path
  B — Error paths
"""

import re

import pytest
from fastapi.testclient import TestClient

import db
from main import app

ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+\d{2}:\d{2}$")

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
def seeded_comm_id(client: TestClient) -> str:
    import main
    return db.create_communication(
        main.DB_PATH,
        patient_name="Elena Vasquez",
        raw_clinical_text='{"conditions": [], "care_plans": []}',
        epic_patient_id="mock-oncology-123",
        fhir_source="mock",
    )


# ── Group A: happy path ───────────────────────────────────────────────────────

def test_approve_returns_200(client: TestClient, seeded_comm_id: str) -> None:
    resp = client.post(
        f"/api/communications/{seeded_comm_id}/approve",
        json={"ai_summary_text": APPROVED_TEXT},
    )
    assert resp.status_code == 200


def test_approve_response_has_required_fields(client: TestClient, seeded_comm_id: str) -> None:
    body = client.post(
        f"/api/communications/{seeded_comm_id}/approve",
        json={"ai_summary_text": APPROVED_TEXT},
    ).json()
    for field in ("id", "approved_at", "family_link"):
        assert field in body, f"missing field: {field}"


def test_approve_sets_status_in_db(client: TestClient, seeded_comm_id: str) -> None:
    import main
    client.post(
        f"/api/communications/{seeded_comm_id}/approve",
        json={"ai_summary_text": APPROVED_TEXT},
    )
    record = db.get_communication(main.DB_PATH, seeded_comm_id)
    assert record is not None
    assert record["status"] == "Approved"


def test_approve_sets_approved_at_in_db(client: TestClient, seeded_comm_id: str) -> None:
    import main
    client.post(
        f"/api/communications/{seeded_comm_id}/approve",
        json={"ai_summary_text": APPROVED_TEXT},
    )
    record = db.get_communication(main.DB_PATH, seeded_comm_id)
    assert record is not None
    assert record["approved_at"] is not None
    assert ISO_RE.match(record["approved_at"]), f"bad timestamp: {record['approved_at']}"


def test_approve_updates_ai_summary_text(client: TestClient, seeded_comm_id: str) -> None:
    import main
    client.post(
        f"/api/communications/{seeded_comm_id}/approve",
        json={"ai_summary_text": APPROVED_TEXT},
    )
    record = db.get_communication(main.DB_PATH, seeded_comm_id)
    assert record is not None
    assert record["ai_summary_text"] == APPROVED_TEXT


def test_approve_family_link_contains_comm_id(client: TestClient, seeded_comm_id: str) -> None:
    body = client.post(
        f"/api/communications/{seeded_comm_id}/approve",
        json={"ai_summary_text": APPROVED_TEXT},
    ).json()
    assert seeded_comm_id in body["family_link"]


def test_approve_approved_at_in_response_is_iso8601(
    client: TestClient, seeded_comm_id: str
) -> None:
    body = client.post(
        f"/api/communications/{seeded_comm_id}/approve",
        json={"ai_summary_text": APPROVED_TEXT},
    ).json()
    assert ISO_RE.match(body["approved_at"]), f"bad timestamp: {body['approved_at']}"


# ── Group B: error paths ──────────────────────────────────────────────────────

def test_approve_unknown_id_returns_404(client: TestClient) -> None:
    resp = client.post(
        "/api/communications/00000000-0000-0000-0000-000000000000/approve",
        json={"ai_summary_text": APPROVED_TEXT},
    )
    assert resp.status_code == 404


def test_error_body_has_detail_key(client: TestClient) -> None:
    body = client.post(
        "/api/communications/00000000-0000-0000-0000-000000000000/approve",
        json={"ai_summary_text": APPROVED_TEXT},
    ).json()
    assert "detail" in body
