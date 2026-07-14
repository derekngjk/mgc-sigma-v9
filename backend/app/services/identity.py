"""Patient-account identity: name+NRIC login hashing and session tokens.

The login credential (patient full name + NRIC) is never stored — only an
HMAC-SHA256 hash (peppered with a server secret) is kept on ``patients.identity_hash``
and compared at login. A successful login mints a short-lived JWT that authorizes
the patient-facing account endpoints.
"""

import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

import jwt

from app.config import settings

_TOKEN_ALG = "HS256"
_TOKEN_TTL = timedelta(days=7)
_TOKEN_TYPE = "patient"

# PBKDF2-HMAC-SHA256 password hashing (stdlib — no external dependency).
_PBKDF2_ITERATIONS = 240_000
_SALT_BYTES = 16


def normalize_name(name: str) -> str:
    """Uppercase and collapse whitespace so display variants hash identically."""
    return " ".join((name or "").upper().split())


def normalize_nric(nric: str) -> str:
    """Uppercase and strip the NRIC/FIN so ' s6712345a ' and 'S6712345A' match."""
    return (nric or "").strip().upper()


def identity_hash(name: str, nric: str) -> str:
    """Return the peppered HMAC-SHA256 of the normalized name+NRIC, or '' if incomplete.

    Both a name and an NRIC are required — a patient missing either cannot form an
    account, so callers can treat '' as "no account".
    """
    norm_name = normalize_name(name)
    norm_nric = normalize_nric(nric)
    if not norm_name or not norm_nric:
        return ""
    message = f"{norm_name}|{norm_nric}".encode()
    return hmac.new(
        settings.patient_id_pepper.encode(), message, hashlib.sha256
    ).hexdigest()


def hash_password(password: str) -> tuple[str, str]:
    """Return (salt_hex, hash_hex) for a new password using PBKDF2-HMAC-SHA256."""
    salt = os.urandom(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, _PBKDF2_ITERATIONS
    )
    return salt.hex(), derived.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """Constant-time check of a password against a stored (salt, hash) pair."""
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, _PBKDF2_ITERATIONS
    )
    return hmac.compare_digest(derived.hex(), hash_hex)


def issue_patient_token(patient_id: str) -> str:
    """Mint a signed patient session JWT for the given internal patient id."""
    now = datetime.now(UTC)
    payload = {
        "sub": patient_id,
        "typ": _TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int((now + _TOKEN_TTL).timestamp()),
    }
    return jwt.encode(payload, settings.patient_jwt_secret, algorithm=_TOKEN_ALG)


def decode_patient_token(token: str) -> str:
    """Return the patient id from a valid patient token.

    Raises jwt.InvalidTokenError (incl. expiry / wrong type / bad signature).
    """
    payload = jwt.decode(token, settings.patient_jwt_secret, algorithms=[_TOKEN_ALG])
    if payload.get("typ") != _TOKEN_TYPE:
        raise jwt.InvalidTokenError("not a patient token")
    patient_id = payload.get("sub")
    if not patient_id:
        raise jwt.InvalidTokenError("missing subject")
    return patient_id
