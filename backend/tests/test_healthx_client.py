"""Tests for the live HealthX FHIR R4B client auth + URL wiring (fhir._fetch_from_sandbox)."""

from typing import Any

import pytest

from app.services import fhir


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.status_code = 200
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeClient:
    """Records constructor headers + GET URLs; returns canned FHIR payloads."""

    last_headers: dict[str, str] = {}
    calls: list[str] = []

    def __init__(
        self, timeout: float | None = None, headers: dict[str, str] | None = None
    ) -> None:
        _FakeClient.last_headers = headers or {}
        _FakeClient.calls = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def get(self, url: str, params: dict[str, str] | None = None) -> _FakeResponse:
        _FakeClient.calls.append(url)
        if "/Patient/" in url:
            return _FakeResponse(
                {
                    "resourceType": "Patient",
                    "name": [{"text": "Aaron Teo"}],
                    "birthDate": "1992-06-02",
                    "gender": "male",
                }
            )
        return _FakeResponse(
            {"resourceType": "Bundle", "type": "searchset", "entry": []}
        )


def test_fetch_sends_x_api_key_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fhir, "HEALTHX_API_KEY", "test-key-123")
    monkeypatch.setattr(fhir, "FHIR_BASE_URL", "https://api.healthx.sg/fhir/r4b/tenant")
    monkeypatch.setattr(fhir.httpx, "Client", _FakeClient)

    result = fhir._fetch_from_sandbox("patient-xyz")

    # HX-IS auth is x-api-key, never a bearer token.
    assert _FakeClient.last_headers.get("x-api-key") == "test-key-123"
    assert "Authorization" not in _FakeClient.last_headers
    # Patient read hits the R4B base URL with the tenant embedded in the path.
    assert (
        _FakeClient.calls[0]
        == "https://api.healthx.sg/fhir/r4b/tenant/Patient/patient-xyz"
    )
    assert result["patient"]["birthDate"] == "1992-06-02"


def test_fetch_without_key_sends_no_auth_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fhir, "HEALTHX_API_KEY", "")
    monkeypatch.setattr(fhir, "FHIR_BASE_URL", "https://api.healthx.sg/fhir/r4b/tenant")
    monkeypatch.setattr(fhir.httpx, "Client", _FakeClient)

    fhir._fetch_from_sandbox("patient-xyz")

    assert "x-api-key" not in _FakeClient.last_headers
    assert "Authorization" not in _FakeClient.last_headers
