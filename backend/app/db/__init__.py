"""Database access layer: Supabase CRUD, storage, and schema init."""

from app.db.changes import (
    delivered_audiences,
    has_open_detected_draft,
    insert_detected_draft,
    list_detected_drafts,
    list_watched_patients,
)
from app.db.client import get_supabase
from app.db.communications import (
    create_communication,
    get_communication,
    get_latest_approved_communication,
    get_translation,
    set_delivered,
    set_translation,
    update_communication,
)
from app.db.patients import (
    get_patient_id_by_identity_hash,
    get_patient_name,
    patient_has_identity,
)
from app.db.portal import (
    create_portal_user,
    get_portal_user,
    get_portal_user_by_email,
    get_read_comm_ids,
    get_role_report_for_user,
    list_role_reports,
    mark_report_read,
)
from app.db.schema import init_db
from app.db.storage import (
    get_audio_url,
    get_image_url,
    set_audio_url,
    set_image_url,
    upload_audio,
    upload_image,
)

__all__ = [
    "create_communication",
    "create_portal_user",
    "delivered_audiences",
    "get_audio_url",
    "get_communication",
    "get_image_url",
    "get_latest_approved_communication",
    "get_patient_id_by_identity_hash",
    "get_patient_name",
    "get_portal_user",
    "get_portal_user_by_email",
    "get_read_comm_ids",
    "get_role_report_for_user",
    "get_supabase",
    "get_translation",
    "has_open_detected_draft",
    "init_db",
    "insert_detected_draft",
    "list_detected_drafts",
    "list_role_reports",
    "list_watched_patients",
    "mark_report_read",
    "patient_has_identity",
    "set_audio_url",
    "set_delivered",
    "set_image_url",
    "set_translation",
    "update_communication",
    "upload_audio",
    "upload_image",
]
