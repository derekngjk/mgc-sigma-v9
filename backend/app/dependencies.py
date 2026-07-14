"""FastAPI dependencies shared across routers."""

from typing import Any

import httpx
import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.services.identity import decode_patient_token

_bearer = HTTPBearer()


def verify_clinician_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict[str, Any]:
    """Validate the bearer token against the Supabase Auth API."""
    if not settings.supabase_url or not settings.supabase_key:
        raise HTTPException(
            status_code=503, detail="Auth not configured (SUPABASE_URL/KEY missing)"
        )

    try:
        response = httpx.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {credentials.credentials}",
                "apikey": settings.supabase_key,
            },
            timeout=5.0,
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503, detail="Could not reach auth service"
        ) from exc

    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return response.json()


def verify_patient_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> str:
    """Validate the patient session JWT and return the internal patient id."""
    try:
        return decode_patient_token(credentials.credentials)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=401, detail="Invalid or expired session"
        ) from exc
