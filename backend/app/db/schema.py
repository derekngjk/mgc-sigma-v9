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
            cur.execute("""
                ALTER TABLE care_plan_translations
                ADD COLUMN IF NOT EXISTS image_url TEXT
            """)
            cur.execute("""
                ALTER TABLE care_plan_translations
                ADD COLUMN IF NOT EXISTS review_json JSONB
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
    client.get_supabase()
