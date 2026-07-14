"""Build patient/family-facing prompts and run them through the configured LLM."""

from typing import Any

from fastapi import HTTPException

from app.db import get_translation, set_translation
from app.services import llm
from app.services.prompts import (
    AUDIENCE_INSTRUCTIONS,
    CLINICAL_GLOSSARY,
    LENGTH_INSTRUCTIONS,
    SUPPORTED_LANGS,
    SYSTEM_PROMPT_BASE,
    VALID_AUDIENCES,
)

__all__ = [
    "VALID_AUDIENCES",
    "generate_summary",
    "resolve_summary_text",
    "translate_summary",
]


def generate_summary(
    raw_clinical_text: str,
    target_audience: str,
    condition_diff: dict[str, Any] | None = None,
    length: str = "medium",
) -> str:
    length_instruction = LENGTH_INSTRUCTIONS.get(length, LENGTH_INSTRUCTIONS["medium"])

    diff_section = ""
    if condition_diff:
        added = condition_diff.get("added", [])
        removed = condition_diff.get("removed", [])
        ongoing = condition_diff.get("ongoing", [])
        parts: list[str] = []
        if ongoing:
            parts.append(f"Ongoing conditions: {', '.join(ongoing)}")
        if added:
            parts.append(f"New conditions since last report: {', '.join(added)}")
        if removed:
            parts.append(f"Resolved conditions since last report: {', '.join(removed)}")
        if parts:
            diff_section = "\n\nCondition summary:\n" + "\n".join(
                f"- {p}" for p in parts
            )
        if added or removed:
            diff_section += (
                "\n\nChanges since last report: please mention these changes clearly."
            )

    audience_instruction = AUDIENCE_INSTRUCTIONS.get(
        target_audience, AUDIENCE_INSTRUCTIONS["patient"]
    )
    prompt = (
        f"{SYSTEM_PROMPT_BASE}\n\n"
        f"Audience: {audience_instruction}\n\n"
        f"{length_instruction}"
        f"{diff_section}\n\n"
        f"Clinical data (JSON):\n{raw_clinical_text}"
    )
    return llm.complete(prompt)


def translate_summary(text: str, lang: str) -> str:
    """Translate an approved English summary into a Singapore official language.

    Returns text unchanged for lang='en'. Raises LLMConfigError for an unsupported
    language code, and LLMError if the LLM call fails.
    """
    if lang == "en":
        return text
    if lang not in SUPPORTED_LANGS:
        raise llm.LLMConfigError(
            f"Unsupported language: {lang!r}. Supported non-English codes: {list(SUPPORTED_LANGS)}"
        )
    lang_name = SUPPORTED_LANGS[lang]
    glossary = CLINICAL_GLOSSARY.get(lang, {})
    glossary_lines = "\n".join(f"  {en} → {target}" for en, target in glossary.items())
    prompt = (
        f"Translate the following patient health summary from English into {lang_name}.\n\n"
        "Rules:\n"
        "- Preserve the warm, empathetic tone exactly.\n"
        "- Keep the same paragraph and heading structure (separate paragraphs with a blank line).\n"
        "- Preserve all Markdown formatting markers exactly as they appear: **bold**, *italic*, ## headings, - list items.\n"
        "- Use the medical term translations listed below for consistency.\n"
        "- Return only the translated text. No explanations, no added commentary.\n\n"
        f"Medical term reference (use these translations):\n{glossary_lines}\n\n"
        f"Summary to translate:\n{text}"
    )
    # Tamil and Malay scripts are token-heavy, so translations need more headroom.
    return llm.complete(prompt, max_tokens=4096)


def resolve_summary_text(comm_id: str, source_text: str, lang: str) -> str:
    """Return the summary in the requested language, using and filling the cache.

    English short-circuits; non-English is translated once, cached, and reused.
    Raises HTTPException(503/502) on LLM config / call failure, matching the routes.
    """
    if lang == "en":
        return source_text
    cached = get_translation(comm_id, lang)
    if cached is not None:
        return cached
    try:
        translated = translate_summary(source_text, lang)
    except llm.LLMConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    set_translation(comm_id, lang, translated)
    return translated
