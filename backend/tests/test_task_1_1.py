"""
Task 1.1 — Foundation scaffold.
Acceptance: backend returns 200 OK health check; root returns a message.
"""

from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def test_health_body_shape(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "mgc-backend"
    assert body["version"] == "0.1.0"


def test_root_returns_200(client: TestClient) -> None:
    assert client.get("/").status_code == 200


def test_root_has_message(client: TestClient) -> None:
    assert "message" in client.get("/").json()
