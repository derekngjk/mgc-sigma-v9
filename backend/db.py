import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    with _connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS Communications (
                id                TEXT PRIMARY KEY,
                epic_patient_id   TEXT NOT NULL,
                fhir_source       TEXT NOT NULL,
                patient_name      TEXT NOT NULL,
                raw_clinical_text TEXT NOT NULL,
                target_audience   TEXT NOT NULL,
                ai_summary_text   TEXT,
                status            TEXT NOT NULL DEFAULT 'Draft',
                created_at        TEXT NOT NULL,
                approved_at       TEXT
            )
        """)


def create_communication(
    db_path: str,
    patient_name: str,
    raw_clinical_text: str,
    epic_patient_id: str = "",
    fhir_source: str = "sandbox",
    target_audience: str = "family",
) -> str:
    comm_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO Communications
                (id, epic_patient_id, fhir_source, patient_name, raw_clinical_text,
                 target_audience, ai_summary_text, status, created_at, approved_at)
            VALUES (?, ?, ?, ?, ?, ?, NULL, 'Draft', ?, NULL)
            """,
            (comm_id, epic_patient_id, fhir_source, patient_name, raw_clinical_text,
             target_audience, now),
        )
    return comm_id


def get_communication(db_path: str, comm_id: str) -> Optional[dict]:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM Communications WHERE id = ?", (comm_id,)
        ).fetchone()
    return dict(row) if row else None


_UPDATABLE_FIELDS = {"ai_summary_text", "status", "approved_at"}


def update_communication(db_path: str, comm_id: str, **kwargs: str) -> bool:
    fields = {k: v for k, v in kwargs.items() if k in _UPDATABLE_FIELDS}
    if not fields:
        return False
    if fields.get("status") == "Approved" and "approved_at" not in fields:
        fields["approved_at"] = datetime.now(timezone.utc).isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [comm_id]
    with _connect(db_path) as conn:
        cursor = conn.execute(
            f"UPDATE Communications SET {set_clause} WHERE id = ?", values  # noqa: S608
        )
    return cursor.rowcount > 0
