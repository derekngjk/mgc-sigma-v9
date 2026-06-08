"""
Task 1.1 — Foundation scaffold.
Acceptance: backend returns 200 OK health check; root returns a message.
"""


def test_health_returns_200(client):
    assert client.get("/health").status_code == 200


def test_health_body_shape(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["service"] == "mgc-backend"
    assert "version" in body


def test_root_returns_200(client):
    assert client.get("/").status_code == 200


def test_root_has_message(client):
    assert "message" in client.get("/").json()
