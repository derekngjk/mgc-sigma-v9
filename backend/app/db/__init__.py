"""Database access layer: Supabase CRUD, storage, and schema init."""

from app.db.client import get_supabase
from app.db.communications import (
    create_communication,
    get_communication,
    get_latest_approved_communication,
    get_translation,
    set_translation,
    update_communication,
)
from app.db.families import (
    create_family_member,
    get_family_summary,
    get_or_create_family,
    get_or_create_primary_member,
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
    "create_family_member",
    "get_audio_url",
    "get_communication",
    "get_family_summary",
    "get_image_url",
    "get_latest_approved_communication",
    "get_or_create_family",
    "get_or_create_primary_member",
    "get_supabase",
    "get_translation",
    "init_db",
    "set_audio_url",
    "set_image_url",
    "set_translation",
    "update_communication",
    "upload_audio",
    "upload_image",
]
