"""Patient/family-facing endpoints: approved summary, translation, and audio."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db import (
    get_audio_url,
    get_communication,
    get_family_summary,
    get_image_url,
    get_translation,
    set_audio_url,
    set_translation,
    upload_audio,
)
from app.schemas import (
    VALID_LANGS,
    AudioResponse,
    ConditionDiff,
    FamilyViewResponse,
)
from app.services.llm import LLMConfigError, LLMError
from app.services.summaries import translate_summary
from app.services.tts import generate_tts, split_sentences, strip_markdown

router = APIRouter()


def _validate_lang(lang: str) -> None:
    if lang not in VALID_LANGS:
        raise HTTPException(
            status_code=400, detail=f"lang must be one of: {sorted(VALID_LANGS)}"
        )


def _condition_diff(record: dict[str, Any]) -> ConditionDiff:
    diff_raw = (
        json.loads(record["condition_diff"])
        if record.get("condition_diff")
        else {"added": [], "removed": [], "ongoing": []}
    )
    return ConditionDiff(**diff_raw)


def resolve_summary_text(comm_id: str, source_text: str, lang: str) -> str:
    """Return the summary in the requested language, using and filling the cache."""
    if lang == "en":
        return source_text
    cached = get_translation(comm_id, lang)
    if cached is not None:
        return cached
    try:
        translated = translate_summary(source_text, lang)
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    set_translation(comm_id, lang, translated)
    return translated


@router.get("/api/communications/{comm_id}", response_model=FamilyViewResponse)
def get_family_view(
    comm_id: str,
    lang: str = Query(default="en"),
) -> FamilyViewResponse:
    _validate_lang(lang)
    record = get_communication(comm_id)
    if record is None or record["status"] != "Approved":
        raise HTTPException(
            status_code=404, detail="Summary not found or not yet approved"
        )
    return FamilyViewResponse(
        id=comm_id,
        patient_name=record["patient_name"],
        ai_summary_text=resolve_summary_text(comm_id, record["ai_summary_text"], lang),
        approved_at=record["approved_at"],
        condition_diff=_condition_diff(record),
        image_url=get_image_url(comm_id),
    )


@router.get(
    "/api/family/{family_id}/member/{member_id}", response_model=FamilyViewResponse
)
def get_family_member_view(
    family_id: str,
    member_id: str,
    lang: str = Query(default="en"),
) -> FamilyViewResponse:
    _validate_lang(lang)
    record = get_family_summary(family_id, member_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail="Summary not found or not yet approved"
        )
    comm_id = record["id"]
    return FamilyViewResponse(
        id=comm_id,
        patient_name=record["patient_name"],
        ai_summary_text=resolve_summary_text(comm_id, record["ai_summary_text"], lang),
        approved_at=record["approved_at"],
        condition_diff=_condition_diff(record),
        image_url=get_image_url(comm_id),
    )


@router.get(
    "/api/family/{family_id}/member/{member_id}/audio", response_model=AudioResponse
)
def get_family_member_audio(
    family_id: str,
    member_id: str,
    lang: str = Query(default="en"),
) -> AudioResponse:
    _validate_lang(lang)
    record = get_family_summary(family_id, member_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail="Summary not found or not yet approved"
        )
    comm_id = record["id"]
    summary_text = resolve_summary_text(comm_id, record["ai_summary_text"], lang)

    clean_text = strip_markdown(summary_text)
    sentences = split_sentences(clean_text)

    cached_url = get_audio_url(comm_id, lang)
    if cached_url:
        return AudioResponse(url=cached_url, sentences=sentences)

    try:
        audio_bytes = generate_tts(clean_text)
    except LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"TTS generation failed: {exc}"
        ) from exc

    try:
        url = upload_audio(comm_id, lang, audio_bytes)
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail=f"Audio upload failed: {exc}"
        ) from exc

    set_audio_url(comm_id, lang, url)
    return AudioResponse(url=url, sentences=sentences)
