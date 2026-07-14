"""Portal-account queries: per-user registration/login, role-scoped reports, read state."""

import uuid
from datetime import UTC, datetime
from typing import Any

from app.db import client
from app.db._helpers import normalize_record

_CARD_COLUMNS = "id, target_audience, approved_at, delivered_to_patient_at, image_url"


def get_portal_user_by_email(email: str) -> dict[str, Any] | None:
    """Return the portal user row for an email (incl. password hash), or None."""
    supabase = client.get_supabase()
    res = (
        supabase.table("portal_users")
        .select("*")
        .eq("email", email.strip().lower())
        .execute()
    )
    return res.data[0] if res.data else None


def get_portal_user(user_id: str) -> dict[str, Any] | None:
    """Return a portal user row (role, patient_id, email) by id, or None."""
    supabase = client.get_supabase()
    res = supabase.table("portal_users").select("*").eq("id", user_id).execute()
    return res.data[0] if res.data else None


def create_portal_user(
    email: str,
    password_hash: str,
    password_salt: str,
    role: str,
    patient_id: str,
) -> str:
    """Insert a portal user and return its id."""
    supabase = client.get_supabase()
    user_id = str(uuid.uuid4())
    supabase.table("portal_users").insert(
        {
            "id": user_id,
            "email": email.strip().lower(),
            "password_hash": password_hash,
            "password_salt": password_salt,
            "role": role,
            "patient_id": patient_id,
        }
    ).execute()
    return user_id


def list_role_reports(patient_id: str, role: str) -> list[dict[str, Any]]:
    """Delivered, approved reports for a patient whose audience matches the role.

    Newest first. `viewed` is per-user and added by the router from the read set.
    """
    supabase = client.get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select(_CARD_COLUMNS)
        .eq("patient_id", patient_id)
        .eq("status", "Approved")
        .eq("target_audience", role)
        .order("delivered_to_patient_at", desc=True)
        .execute()
    )
    cards: list[dict[str, Any]] = []
    for row in res.data or []:
        if not row.get("delivered_to_patient_at"):
            continue
        cards.append(
            {
                "comm_id": row["id"],
                "target_audience": row.get("target_audience", role),
                "approved_at": row.get("approved_at"),
                "delivered_at": row.get("delivered_to_patient_at"),
                "has_image": bool(row.get("image_url")),
            }
        )
    return cards


def get_role_report_for_user(
    comm_id: str, patient_id: str, role: str
) -> dict[str, Any] | None:
    """Return a report only if it is this patient's, this role's, approved, delivered.

    The authorization gate for the account report view — a user can only read a
    comm_id that belongs to their linked patient and matches their role.
    """
    supabase = client.get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select("*, patients(patient_name, epic_patient_id)")
        .eq("id", comm_id)
        .eq("patient_id", patient_id)
        .eq("target_audience", role)
        .eq("status", "Approved")
        .execute()
    )
    if not res.data:
        return None
    record = res.data[0]
    if not record.get("delivered_to_patient_at"):
        return None
    return normalize_record(record)


def get_read_comm_ids(portal_user_id: str) -> set[str]:
    """Return the set of comm_ids this user has opened."""
    supabase = client.get_supabase()
    res = (
        supabase.table("portal_report_reads")
        .select("comm_id")
        .eq("portal_user_id", portal_user_id)
        .execute()
    )
    return {row["comm_id"] for row in (res.data or [])}


def mark_report_read(portal_user_id: str, comm_id: str) -> None:
    """Record that a user opened a report (idempotent on the (user, report) pair)."""
    supabase = client.get_supabase()
    supabase.table("portal_report_reads").upsert(
        {
            "portal_user_id": portal_user_id,
            "comm_id": comm_id,
            "viewed_at": datetime.now(UTC).isoformat(),
        },
        on_conflict="portal_user_id,comm_id",
    ).execute()
