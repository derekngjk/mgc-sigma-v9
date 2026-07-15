"""Tests for portal registration + login (POST /api/account/register|login)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import account
from app.services.identity import decode_portal_token, hash_password


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


# ── registration ─────────────────────────────────────────────────────────────


def test_register_success_returns_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(account, "get_patient_id_by_identity_hash", lambda h: "p1")
    monkeypatch.setattr(account, "get_portal_user_by_email", lambda e: None)
    monkeypatch.setattr(account, "create_portal_user", lambda *a, **k: "user-1")
    monkeypatch.setattr(account, "get_patient_name", lambda pid: "Tan Mei Ling")

    resp = client.post(
        "/api/account/register",
        json={
            "email": "Caregiver@Example.com",
            "password": "hunter2",
            "role": "caregiver",
            "patient_full_name": "Tan Mei Ling",
            "patient_nric": "S6712345A",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "caregiver"
    assert body["patient_name"] == "Tan Mei Ling"
    assert decode_portal_token(body["token"]) == "user-1"


def test_register_unknown_patient_returns_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(account, "get_patient_id_by_identity_hash", lambda h: None)
    resp = client.post(
        "/api/account/register",
        json={
            "email": "x@example.com",
            "password": "hunter2",
            "role": "caregiver",
            "patient_full_name": "Nobody",
            "patient_nric": "S0000000A",
        },
    )
    assert resp.status_code == 404


def test_register_duplicate_email_returns_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(account, "get_patient_id_by_identity_hash", lambda h: "p1")
    monkeypatch.setattr(account, "get_portal_user_by_email", lambda e: {"id": "u0"})
    resp = client.post(
        "/api/account/register",
        json={
            "email": "taken@example.com",
            "password": "hunter2",
            "role": "patient",
            "patient_full_name": "Tan Mei Ling",
            "patient_nric": "S6712345A",
        },
    )
    assert resp.status_code == 409


def test_register_bad_role_returns_400(client: TestClient) -> None:
    resp = client.post(
        "/api/account/register",
        json={
            "email": "x@example.com",
            "password": "hunter2",
            "role": "boss",
            "patient_full_name": "Tan Mei Ling",
            "patient_nric": "S6712345A",
        },
    )
    assert resp.status_code == 400


def test_register_short_password_returns_400(client: TestClient) -> None:
    resp = client.post(
        "/api/account/register",
        json={
            "email": "x@example.com",
            "password": "12345",
            "role": "patient",
            "patient_full_name": "Tan Mei Ling",
            "patient_nric": "S6712345A",
        },
    )
    assert resp.status_code == 400


# ── login ────────────────────────────────────────────────────────────────────


def _user_row() -> dict:
    salt, pw_hash = hash_password("hunter2")
    return {
        "id": "user-1",
        "email": "caregiver@example.com",
        "password_salt": salt,
        "password_hash": pw_hash,
        "role": "caregiver",
        "patient_id": "p1",
    }


def test_login_success_returns_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(account, "get_portal_user_by_email", lambda e: _user_row())
    monkeypatch.setattr(account, "get_patient_name", lambda pid: "Tan Mei Ling")

    resp = client.post(
        "/api/account/login",
        json={"email": "caregiver@example.com", "password": "hunter2"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "caregiver"
    assert decode_portal_token(body["token"]) == "user-1"


def test_login_wrong_password_returns_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(account, "get_portal_user_by_email", lambda e: _user_row())
    resp = client.post(
        "/api/account/login",
        json={"email": "caregiver@example.com", "password": "wrongpass"},
    )
    assert resp.status_code == 401


def test_login_unknown_email_returns_401(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(account, "get_portal_user_by_email", lambda e: None)
    resp = client.post(
        "/api/account/login",
        json={"email": "nobody@example.com", "password": "hunter2"},
    )
    assert resp.status_code == 401
