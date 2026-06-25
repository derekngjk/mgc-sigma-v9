import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import psycopg
from supabase import create_client, Client, ClientOptions

# These will be initialized in init_db or from env
_supabase_url = os.getenv("SUPABASE_URL", "")
_supabase_key = os.getenv("SUPABASE_KEY", "")
_client: Optional[Client] = None


# ...
def get_supabase() -> Client:
    global _client
    if _client is None:
        url = _supabase_url or os.getenv(
            "SUPABASE_URL", "https://placeholder.supabase.co"
        )
        key = _supabase_key or os.getenv("SUPABASE_KEY", "placeholder")
        # Use ClientOptions to set timeouts correctly and avoid deprecation warnings
        options = ClientOptions(
            postgrest_client_timeout=10,
            storage_client_timeout=10,
        )
        _client = create_client(url, key, options=options)
    return _client


def init_db(db_url: str) -> None:
    """Initialize Supabase/Postgres tables using psycopg3."""
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS patients (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    epic_patient_id TEXT UNIQUE NOT NULL,
                    patient_name TEXT NOT NULL,
                    dob TEXT,
                    gender TEXT,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS care_plan_translations (
                    id UUID PRIMARY KEY,
                    patient_id UUID REFERENCES patients(id),
                    fhir_source TEXT NOT NULL,
                    raw_clinical_text TEXT NOT NULL,
                    target_audience TEXT NOT NULL,
                    ai_summary_text TEXT,
                    status TEXT NOT NULL DEFAULT 'Draft',
                    created_at TIMESTAMPTZ DEFAULT now(),
                    approved_at TIMESTAMPTZ,
                    conditions_json JSONB NOT NULL DEFAULT '[]',
                    condition_diff JSONB,
                    translations_json JSONB DEFAULT '{}'
                )
            """)
            # Idempotent migrations for columns added after initial schema.
            cur.execute("""
                ALTER TABLE care_plan_translations
                ADD COLUMN IF NOT EXISTS translations_json JSONB DEFAULT '{}'
            """)
            cur.execute("""
                ALTER TABLE care_plan_translations
                ADD COLUMN IF NOT EXISTS approved_by_user_id UUID
            """)
            cur.execute("""
                ALTER TABLE care_plan_translations
                ADD COLUMN IF NOT EXISTS audio_urls_json JSONB DEFAULT '{}'
            """)

            # One family group per patient — stable across approvals
            cur.execute("""
                CREATE TABLE IF NOT EXISTS families (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    patient_id UUID UNIQUE REFERENCES patients(id),
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """)

            # Individual family members who can access the patient's summary
            cur.execute("""
                CREATE TABLE IF NOT EXISTS family_members (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    family_id UUID REFERENCES families(id),
                    name TEXT NOT NULL,
                    relationship TEXT NOT NULL DEFAULT 'patient',
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """)

            # Backend uses the anon key for CRUD — disable RLS so server-side
            # writes are not blocked by missing policies on these tables.
            cur.execute("ALTER TABLE families DISABLE ROW LEVEL SECURITY")
            cur.execute("ALTER TABLE family_members DISABLE ROW LEVEL SECURITY")
    get_supabase()


def create_communication(
    patient_name: str,
    raw_clinical_text: str,
    epic_patient_id: str = "",
    fhir_source: str = "sandbox",
    target_audience: str = "family",
    conditions_json: str = "[]",
    condition_diff: Optional[str] = None,
) -> str:
    supabase = get_supabase()

    # 1. Upsert patient
    patient_data = {
        "epic_patient_id": epic_patient_id,
        "patient_name": patient_name,
    }
    # We use upsert on epic_patient_id
    patient_res = (
        supabase.table("patients")
        .upsert(patient_data, on_conflict="epic_patient_id")
        .execute()
    )
    patient_id = patient_res.data[0]["id"]

    # 2. Create translation record
    comm_id = str(uuid.uuid4())
    translation_data = {
        "id": comm_id,
        "patient_id": patient_id,
        "fhir_source": fhir_source,
        "raw_clinical_text": raw_clinical_text,
        "target_audience": target_audience,
        "status": "Draft",
        "conditions_json": conditions_json,
        "condition_diff": condition_diff,
    }
    supabase.table("care_plan_translations").insert(translation_data).execute()

    return comm_id


def get_communication(comm_id: str) -> Optional[dict]:
    supabase = get_supabase()
    # Join with patients to get patient_name and epic_patient_id
    res = (
        supabase.table("care_plan_translations")
        .select("*, patients(patient_name, epic_patient_id)")
        .eq("id", comm_id)
        .execute()
    )

    if not res.data:
        return None

    record = res.data[0]
    # Flatten the response to match old SQLite shape
    patient = record.pop("patients", {})
    record["patient_name"] = patient.get("patient_name", "")
    record["epic_patient_id"] = patient.get("epic_patient_id", "")

    # Supabase returns JSONB columns as dicts/lists; callers that use json.loads expect strings.
    if isinstance(record.get("conditions_json"), (list, dict)):
        record["conditions_json"] = json.dumps(record["conditions_json"])
    if isinstance(record.get("condition_diff"), (list, dict)):
        record["condition_diff"] = json.dumps(record["condition_diff"])

    return record


def get_latest_approved_communication(epic_patient_id: str) -> Optional[dict]:
    supabase = get_supabase()

    # First find the patient_id
    patient_res = (
        supabase.table("patients")
        .select("id")
        .eq("epic_patient_id", epic_patient_id)
        .execute()
    )
    if not patient_res.data:
        return None
    patient_id = patient_res.data[0]["id"]

    # Then get latest approved translation
    res = (
        supabase.table("care_plan_translations")
        .select("*, patients(patient_name, epic_patient_id)")
        .eq("patient_id", patient_id)
        .eq("status", "Approved")
        .order("approved_at", desc=True)
        .limit(1)
        .execute()
    )

    if not res.data:
        return None

    record = res.data[0]
    patient = record.pop("patients", {})
    record["patient_name"] = patient.get("patient_name", "")
    record["epic_patient_id"] = patient.get("epic_patient_id", "")

    if isinstance(record.get("conditions_json"), (list, dict)):
        record["conditions_json"] = json.dumps(record["conditions_json"])
    if isinstance(record.get("condition_diff"), (list, dict)):
        record["condition_diff"] = json.dumps(record["condition_diff"])

    return record


def get_or_create_family(patient_id: str) -> str:
    """Return existing family_id for this patient, or create one."""
    supabase = get_supabase()
    res = supabase.table("families").select("id").eq("patient_id", patient_id).execute()
    if res.data:
        return res.data[0]["id"]
    family_id = str(uuid.uuid4())
    supabase.table("families").insert(
        {"id": family_id, "patient_id": patient_id}
    ).execute()
    return family_id


def get_or_create_primary_member(family_id: str, name: str) -> str:
    """Return existing primary (relationship='patient') member_id, or create one."""
    supabase = get_supabase()
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
    """Insert a new family member row and return its id. Not idempotent — always inserts."""
    supabase = get_supabase()
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


def get_family_summary(family_id: str, member_id: str) -> Optional[dict]:
    """Validate fid+mid belong together, then return the latest approved summary."""
    supabase = get_supabase()

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
    patient_id = family_res.data[0]["patient_id"]

    res = (
        supabase.table("care_plan_translations")
        .select("*, patients(patient_name, epic_patient_id)")
        .eq("patient_id", patient_id)
        .eq("status", "Approved")
        .order("approved_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None

    record = res.data[0]
    patient = record.pop("patients", {})
    record["patient_name"] = patient.get("patient_name", "")
    record["epic_patient_id"] = patient.get("epic_patient_id", "")

    import json

    if isinstance(record.get("conditions_json"), (list, dict)):
        record["conditions_json"] = json.dumps(record["conditions_json"])
    if isinstance(record.get("condition_diff"), (list, dict)):
        record["condition_diff"] = json.dumps(record["condition_diff"])

    return record


def get_translation(comm_id: str, lang: str) -> Optional[str]:
    """Return a cached translation for lang from translations_json, or None on cache miss."""
    supabase = get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select("translations_json")
        .eq("id", comm_id)
        .execute()
    )
    if not res.data:
        return None
    raw = res.data[0].get("translations_json") or {}
    translations: dict = json.loads(raw) if isinstance(raw, str) else raw
    return translations.get(lang)


def set_translation(comm_id: str, lang: str, text: str) -> None:
    """Write a translation into translations_json, preserving any other cached languages."""
    supabase = get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select("translations_json")
        .eq("id", comm_id)
        .execute()
    )
    if not res.data:
        return
    raw = res.data[0].get("translations_json") or {}
    current: dict = json.loads(raw) if isinstance(raw, str) else raw
    current[lang] = text
    (
        supabase.table("care_plan_translations")
        .update({"translations_json": current})
        .eq("id", comm_id)
        .execute()
    )


def get_audio_url(comm_id: str, lang: str) -> Optional[str]:
    """Return cached Supabase Storage public URL for this comm+lang, or None on miss."""
    supabase = get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select("audio_urls_json")
        .eq("id", comm_id)
        .execute()
    )
    if not res.data:
        return None
    raw = res.data[0].get("audio_urls_json") or {}
    urls: dict = json.loads(raw) if isinstance(raw, str) else raw
    return urls.get(lang)


def set_audio_url(comm_id: str, lang: str, url: str) -> None:
    """Cache a Supabase Storage public URL in audio_urls_json, preserving other languages."""
    supabase = get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select("audio_urls_json")
        .eq("id", comm_id)
        .execute()
    )
    if not res.data:
        return
    raw = res.data[0].get("audio_urls_json") or {}
    current: dict = json.loads(raw) if isinstance(raw, str) else raw
    current[lang] = url
    (
        supabase.table("care_plan_translations")
        .update({"audio_urls_json": current})
        .eq("id", comm_id)
        .execute()
    )


def upload_audio(comm_id: str, lang: str, audio_bytes: bytes) -> str:
    """Upload MP3 bytes to the tts-audio Supabase Storage bucket and return the public URL."""
    supabase = get_supabase()
    path = f"{comm_id}/{lang}.mp3"
    supabase.storage.from_("tts-audio").upload(
        path,
        audio_bytes,
        {"content-type": "audio/mpeg", "upsert": "true"},
    )
    return supabase.storage.from_("tts-audio").get_public_url(path)


_UPDATABLE_FIELDS = {
    "ai_summary_text",
    "status",
    "approved_at",
    "target_audience",
    "approved_by_user_id",
}


def update_communication(comm_id: str, **kwargs: str) -> bool:
    fields = {k: v for k, v in kwargs.items() if k in _UPDATABLE_FIELDS}
    if not fields:
        return False

    if fields.get("status") == "Approved" and "approved_at" not in fields:
        fields["approved_at"] = datetime.now(timezone.utc).isoformat()

    supabase = get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .update(fields)
        .eq("id", comm_id)
        .execute()
    )

    return len(res.data) > 0
