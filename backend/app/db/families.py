"""CRUD for the families and family_members tables."""

import uuid
from typing import Any

from app.db import client
from app.db._helpers import latest_approved_for_patient


def get_or_create_family(patient_id: str) -> str:
    """Return the existing family_id for this patient, or create one."""
    supabase = client.get_supabase()
    res = supabase.table("families").select("id").eq("patient_id", patient_id).execute()
    if res.data:
        return res.data[0]["id"]
    family_id = str(uuid.uuid4())
    supabase.table("families").insert(
        {"id": family_id, "patient_id": patient_id}
    ).execute()
    return family_id


def get_or_create_primary_member(family_id: str, name: str) -> str:
    """Return the existing primary (relationship='patient') member_id, or create one."""
    supabase = client.get_supabase()
    res = (
        supabase.table("family_members")
        .select("id")
        .eq("family_id", family_id)
        .eq("relationship", "patient")
        .execute()
    )
    if res.data:
        return res.data[0]["id"]
    member_id = str(uuid.uuid4())
    supabase.table("family_members").insert(
        {
            "id": member_id,
            "family_id": family_id,
            "name": name,
            "relationship": "patient",
        }
    ).execute()
    return member_id


def create_family_member(family_id: str, name: str, relationship: str) -> str:
    """Insert a new family member row and return its id. Always inserts."""
    supabase = client.get_supabase()
    member_id = str(uuid.uuid4())
    supabase.table("family_members").insert(
        {
            "id": member_id,
            "family_id": family_id,
            "name": name,
            "relationship": relationship,
        }
    ).execute()
    return member_id


def get_family_summary(family_id: str, member_id: str) -> dict[str, Any] | None:
    """Validate that member belongs to family, then return the latest approved summary."""
    supabase = client.get_supabase()

    member_res = (
        supabase.table("family_members")
        .select("id")
        .eq("id", member_id)
        .eq("family_id", family_id)
        .execute()
    )
    if not member_res.data:
        return None

    family_res = (
        supabase.table("families").select("patient_id").eq("id", family_id).execute()
    )
    if not family_res.data:
        return None

    return latest_approved_for_patient(family_res.data[0]["patient_id"])
