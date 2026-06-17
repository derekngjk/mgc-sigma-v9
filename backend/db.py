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
    # We use the connection string directly here
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Create patients table
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

            # Create care_plan_translations table (mirrors old Communications)
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
                    condition_diff JSONB
                )
            """)
    # Ensure client is ready
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

    # Supabase might return dict for JSONB, but code expects strings for json.loads
    # For backward compatibility, we convert them back to strings if they are dicts/lists
    import json

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

    import json

    if isinstance(record.get("conditions_json"), (list, dict)):
        record["conditions_json"] = json.dumps(record["conditions_json"])
    if isinstance(record.get("condition_diff"), (list, dict)):
        record["condition_diff"] = json.dumps(record["condition_diff"])

    return record


_UPDATABLE_FIELDS = {"ai_summary_text", "status", "approved_at", "target_audience"}


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
