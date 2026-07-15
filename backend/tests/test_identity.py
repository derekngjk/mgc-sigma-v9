"""Unit tests for patient identity hashing and session tokens (services/identity)."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import settings
from app.services.identity import (
    decode_portal_token,
    hash_password,
    identity_hash,
    issue_portal_token,
    verify_password,
)


def test_hash_is_stable_across_display_variants() -> None:
    a = identity_hash("Tan Mei Ling", "S6712345A")
    b = identity_hash("  tan   mei  ling ", "s6712345a")
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_hash_differs_for_different_nric() -> None:
    assert identity_hash("Tan Mei Ling", "S6712345A") != identity_hash(
        "Tan Mei Ling", "S9999999Z"
    )


def test_hash_empty_when_credential_incomplete() -> None:
    assert identity_hash("Tan Mei Ling", "") == ""
    assert identity_hash("", "S6712345A") == ""


def test_password_hash_verifies_correct_and_rejects_wrong() -> None:
    salt, pw_hash = hash_password("hunter2")
    assert verify_password("hunter2", salt, pw_hash)
    assert not verify_password("Hunter2", salt, pw_hash)
    assert not verify_password("", salt, pw_hash)


def test_password_hash_uses_a_fresh_salt_each_time() -> None:
    salt_a, hash_a = hash_password("same-password")
    salt_b, hash_b = hash_password("same-password")
    assert salt_a != salt_b
    assert hash_a != hash_b


def test_verify_password_tolerates_malformed_salt() -> None:
    assert not verify_password("hunter2", "not-hex", "deadbeef")


def test_token_round_trip() -> None:
    token = issue_portal_token("portal-user-1")
    assert decode_portal_token(token) == "portal-user-1"


def test_decode_rejects_bad_signature() -> None:
    forged = jwt.encode(
        {"sub": "x", "typ": "patient"}, "a" * 40, algorithm="HS256"
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_portal_token(forged)


def test_decode_rejects_wrong_token_type() -> None:
    other = jwt.encode(
        {"sub": "x", "typ": "clinician"},
        settings.patient_jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_portal_token(other)


def test_decode_rejects_expired_token() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    expired = jwt.encode(
        {"sub": "x", "typ": "patient", "exp": int(past.timestamp())},
        settings.patient_jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_portal_token(expired)
