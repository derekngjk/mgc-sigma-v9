"""Supabase Storage uploads and cached public URLs for audio and images."""

from app.db import client
from app.db._helpers import get_json_column, set_json_column


def get_audio_url(comm_id: str, lang: str) -> str | None:
    return get_json_column(comm_id, "audio_urls_json", lang)


def set_audio_url(comm_id: str, lang: str, url: str) -> None:
    set_json_column(comm_id, "audio_urls_json", lang, url)


def upload_audio(comm_id: str, lang: str, audio_bytes: bytes) -> str:
    """Upload MP3 bytes to the tts-audio bucket and return the public URL."""
    supabase = client.get_supabase()
    path = f"{comm_id}/{lang}.mp3"
    supabase.storage.from_("tts-audio").upload(
        path,
        audio_bytes,
        {"content-type": "audio/mpeg", "upsert": "true"},
    )
    return supabase.storage.from_("tts-audio").get_public_url(path)


def get_image_url(comm_id: str) -> str | None:
    supabase = client.get_supabase()
    res = (
        supabase.table("care_plan_translations")
        .select("image_url")
        .eq("id", comm_id)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0].get("image_url")


def set_image_url(comm_id: str, url: str) -> None:
    supabase = client.get_supabase()
    (
        supabase.table("care_plan_translations")
        .update({"image_url": url})
        .eq("id", comm_id)
        .execute()
    )


def upload_image(comm_id: str, image_bytes: bytes) -> str:
    """Upload PNG bytes to the visual-aids bucket and return the public URL."""
    supabase = client.get_supabase()
    path = f"{comm_id}/visual.png"
    supabase.storage.from_("visual-aids").upload(
        path,
        image_bytes,
        {"content-type": "image/png", "upsert": "true"},
    )
    return supabase.storage.from_("visual-aids").get_public_url(path)
