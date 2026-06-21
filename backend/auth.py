import os

import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")

_bearer = HTTPBearer()


def verify_clinician_token(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> dict:
    """FastAPI dependency — validates a Supabase-issued JWT and returns the payload."""
    if not _SUPABASE_JWT_SECRET:
        raise HTTPException(status_code=503, detail="Auth not configured (SUPABASE_JWT_SECRET missing)")
    try:
        payload: dict = jwt.decode(
            credentials.credentials,
            _SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
