"""Database schema initialization via psycopg (idempotent DDL)."""

import psycopg

from app.db import client


def init_db(db_url: str) -> None:
    """Create/upgrade the Supabase/Postgres tables using psycopg3."""
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS patients (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    epic_patient_id TEXT UNIQUE NOT NULL,
                    patient_name TEXT NOT NULL,
                    dob TEXT,
                    gender TEXT,
                    identity_hash TEXT,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """)
            # Patient-account login key: peppered hash of full name + NRIC (never the
            # raw credential). Idempotent for databases created before this column.
            cur.execute(
                "ALTER TABLE patients ADD COLUMN IF NOT EXISTS identity_hash TEXT"
            )
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS patients_identity_hash_key "
                "ON patients (identity_hash)"
            )

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
            cur.execute("""
                ALTER TABLE care_plan_translations
                ADD COLUMN IF NOT EXISTS image_url TEXT
            """)
            cur.execute("""
                ALTER TABLE care_plan_translations
                ADD COLUMN IF NOT EXISTS review_json JSONB
            """)
            # Patient-account delivery + read tracking. delivered_to_patient_at is set
            # on approval (a report only appears in the account once delivered);
            # viewed_by_patient_at is set when the patient opens the card (unread =
            # delivered but not yet viewed).
            cur.execute("""
                ALTER TABLE care_plan_translations
                ADD COLUMN IF NOT EXISTS delivered_to_patient_at TIMESTAMPTZ
            """)
            cur.execute("""
                ALTER TABLE care_plan_translations
                ADD COLUMN IF NOT EXISTS viewed_by_patient_at TIMESTAMPTZ
            """)
            # Marks a Draft that was auto-created by change detection (a re-fetch from
            # Epic showed the conditions changed vs. the last approved report). The
            # clinician inbox lists Drafts where this is set; NULL = clinician-initiated.
            cur.execute("""
                ALTER TABLE care_plan_translations
                ADD COLUMN IF NOT EXISTS detected_at TIMESTAMPTZ
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS families (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    patient_id UUID UNIQUE REFERENCES patients(id),
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """)

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

            # Portal accounts: one self-registered user per person, each with a role
            # and linked to a patient. Reports are shown role-scoped; read state is
            # tracked per user in portal_report_reads.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS portal_users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    role TEXT NOT NULL,
                    patient_id UUID REFERENCES patients(id) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS portal_report_reads (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    portal_user_id UUID REFERENCES portal_users(id) NOT NULL,
                    comm_id UUID REFERENCES care_plan_translations(id) NOT NULL,
                    viewed_at TIMESTAMPTZ DEFAULT now(),
                    UNIQUE (portal_user_id, comm_id)
                )
            """)

            cur.execute("ALTER TABLE portal_users DISABLE ROW LEVEL SECURITY")
            cur.execute("ALTER TABLE portal_report_reads DISABLE ROW LEVEL SECURITY")
    client.get_supabase()
