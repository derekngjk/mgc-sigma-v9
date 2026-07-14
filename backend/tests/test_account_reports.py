"""Tests for the authed, role-scoped account report collection + view."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import account

SUMMARY = "Your care team is looking after you."

# list_role_reports returns cards WITHOUT `viewed` (the router adds it per-user).
CARDS = [
    {
        "comm_id": "comm-new",
        "target_audience": "patient",
        "approved_at": "2024-02-01T00:00:00+00:00",
        "delivered_at": "2024-02-01T00:00:00+00:00",
        "has_image": True,
    },
    {
        "comm_id": "comm-old",
        "target_audience": "patient",
        "approved_at": "2024-01-01T00:00:00+00:00",
        "delivered_at": "2024-01-01T00:00:00+00:00",
        "has_image": False,
    },
]


def _record() -> dict:
    return {
        "id": "comm-new",
        "status": "Approved",
        "patient_name": "Tan Mei Ling",
        "ai_summary_text": SUMMARY,
        "approved_at": "2024-02-01T00:00:00+00:00",
        "condition_diff": '{"added": ["Anaemia"], "removed": [], "ongoing": ["Cancer"]}',
        "image_url": "https://example/visual.png",
    }


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def stub_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        account, "get_portal_user", lambda uid: {"role": "patient", "patient_id": "p1"}
    )
    monkeypatch.setattr(account, "get_patient_name", lambda pid: "Tan Mei Ling")


def test_list_reports_is_role_scoped_and_counts_unread(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple] = []
    monkeypatch.setattr(
        account,
        "list_role_reports",
        lambda pid, role: calls.append((pid, role)) or CARDS,
    )
    monkeypatch.setattr(account, "get_read_comm_ids", lambda uid: {"comm-old"})

    resp = client.get("/api/account/reports")
    assert resp.status_code == 200
    body = resp.json()
    # The DB query is scoped to the user's patient + role.
    assert calls == [("p1", "patient")]
    assert body["role"] == "patient"
    assert body["unread"] == 1  # comm-old is read, comm-new is not
    assert [r["comm_id"] for r in body["reports"]] == ["comm-new", "comm-old"]
    assert body["reports"][0]["viewed"] is False
    assert body["reports"][1]["viewed"] is True


def test_unread_is_per_user_read_state(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(account, "list_role_reports", lambda pid, role: CARDS)

    # A user who has read nothing sees both as unread…
    monkeypatch.setattr(account, "get_read_comm_ids", lambda uid: set())
    assert client.get("/api/account/reports").json()["unread"] == 2

    # …a different read set (a different user) yields a different unread count.
    monkeypatch.setattr(account, "get_read_comm_ids", lambda uid: {"comm-new", "comm-old"})
    assert client.get("/api/account/reports").json()["unread"] == 0


def test_view_report_marks_read(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        account, "get_role_report_for_user", lambda cid, pid, role: _record()
    )
    marked: list[tuple] = []
    monkeypatch.setattr(
        account, "mark_report_read", lambda uid, cid: marked.append((uid, cid))
    )

    resp = client.get("/api/account/reports/comm-new")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ai_summary_text"] == SUMMARY
    assert body["condition_diff"]["added"] == ["Anaemia"]
    assert marked == [("test-portal-user-id", "comm-new")]


def test_view_report_wrong_role_or_patient_returns_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # get_role_report_for_user returns None when the report isn't this user's role/patient.
    monkeypatch.setattr(account, "get_role_report_for_user", lambda cid, pid, role: None)
    resp = client.get("/api/account/reports/not-mine")
    assert resp.status_code == 404
