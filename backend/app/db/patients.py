"""Patient-table lookups: identity link, delivery eligibility, display name."""

from app.db import client


def get_patient_id_by_identity_hash(identity_hash: str) -> str | None:
    """Return the internal patient id for a name+NRIC hash, or None on no match.

    Used at portal registration to link a new user to an existing patient.
    """
    if not identity_hash:
        return None
    supabase = client.get_supabase()
    res = (
        supabase.table("patients")
        .select("id")
        .eq("identity_hash", identity_hash)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]["id"]


def patient_has_identity(patient_id: str) -> bool:
    """True if the patient has a login hash (so users can register against them)."""
    supabase = client.get_supabase()
    res = (
        supabase.table("patients")
        .select("identity_hash")
        .eq("id", patient_id)
        .execute()
    )
    if not res.data:
        return False
    return bool(res.data[0].get("identity_hash"))


def get_patient_name(patient_id: str) -> str:
    """Return the patient's display name for the account header, or ''."""
    supabase = client.get_supabase()
    res = (
        supabase.table("patients")
        .select("patient_name")
        .eq("id", patient_id)
        .execute()
    )
    if not res.data:
        return ""
    return res.data[0].get("patient_name", "")
