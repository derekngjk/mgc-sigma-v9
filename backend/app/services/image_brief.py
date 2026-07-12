"""Structured 'image brief' extraction — turns clinical text into a render-ready brief.

A text LLM does the interpreting (voice, anatomy vs. analogy, de-jargoning, de-dosing)
and returns a validated ImageBrief. The image model then renders only the brief.
"""

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.services import llm
from app.services.prompts import AUDIENCE_INSTRUCTIONS, IMAGE_BRIEF_SYSTEM_PROMPT

# Numeric dose / lab quantities that must never reach a patient-facing image.
# Trailing (?![a-z]) instead of \b so units ending in non-word chars (e.g. %) match.
_QUANTITY_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|µg|kg|g|ml|units?|iu|mmol/l|mmol|mmhg|%)(?![a-z])",
    re.IGNORECASE,
)

_VALID_CATEGORIES = {"watch", "do", "dont"}
_PRONOUNS = {"female": "she/her", "male": "he/him"}

# Alarming words the calm-tone rule bans from the title (belt-and-suspenders vs. the prompt).
_ALARMING_RE = re.compile(r"\b(?:emergency|crisis)\b", re.IGNORECASE)


class ReferenceItem(BaseModel):
    category: str
    icon: str
    label: str


class ImageBrief(BaseModel):
    title: str
    condition_illustration: str
    labels: list[str] = Field(default_factory=list)
    reference_items: list[ReferenceItem] = Field(default_factory=list)


def _strip_clinical_quantities(text: str) -> str:
    """Remove numeric doses / lab values (e.g. '500 mg', '0.9%') and tidy whitespace.

    Medication timing words ('daily', 'at night') are preserved — only quantities go.
    """
    return " ".join(_QUANTITY_RE.sub("", text).split())


def _soften_alarming(text: str) -> str:
    """Drop alarming words ('emergency', 'crisis') so the title stays calm."""
    return " ".join(_ALARMING_RE.sub("", text).split()).rstrip(" ,;:-").strip()


def _care_plan_lines(raw_clinical_text: str) -> list[str]:
    """Extract patient-relevant care-plan text from the serialized clinical JSON.

    Walks care_plans.entry[].resource, collecting each plan's title, description, and
    activity[].detail.description. Returns [] on empty/missing/malformed input.
    """
    if not raw_clinical_text:
        return []
    try:
        data = json.loads(raw_clinical_text)
    except (json.JSONDecodeError, TypeError):
        return []

    lines: list[str] = []
    entries = (data.get("care_plans") or {}).get("entry", [])
    for entry in entries:
        resource = entry.get("resource", {})
        for key in ("title", "description"):
            value = (resource.get(key) or "").strip()
            if value:
                lines.append(value)
        for activity in resource.get("activity", []):
            desc = ((activity.get("detail") or {}).get("description") or "").strip()
            if desc:
                lines.append(desc)
    return lines


def _first_json_object(text: str) -> str | None:
    """Return the first balanced {...} object, respecting quoted strings and escapes."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _patient_gender(raw_clinical_text: str) -> str:
    """Return the patient's gender ('male'/'female'/…) from the clinical JSON, or ''."""
    if not raw_clinical_text:
        return ""
    try:
        return (json.loads(raw_clinical_text).get("gender") or "").strip().lower()
    except (json.JSONDecodeError, TypeError, AttributeError):
        return ""


def _pronoun_rule(gender: str, target_audience: str) -> str:
    """Instruct consistent pronouns for the patient so the brief never mixes genders."""
    if target_audience == "patient":
        return "Pronouns: the patient is the reader — use 'you'/'your', no third-person pronouns."
    if gender in _PRONOUNS:
        return (
            f"Pronouns: the patient is {gender}; refer to them consistently with "
            f"{_PRONOUNS[gender]} pronouns and never mix genders."
        )
    return (
        "Pronouns: the patient's gender is not given — avoid gendered pronouns; use 'your "
        "loved one' or 'they/them' consistently."
    )


def _parse_brief_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from an LLM response that may be fenced, padded with
    prose, or contain trailing commas."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    candidate = _first_json_object(cleaned) or cleaned
    # Second attempt tolerates trailing commas (a common LLM JSON slip).
    for attempt in (candidate, re.sub(r",(\s*[}\]])", r"\1", candidate)):
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            continue
    raise llm.LLMError("image brief response was not valid JSON")


def _complete_and_parse(prompt: str) -> dict[str, Any]:
    """Run the LLM and parse its JSON, retrying once with a stricter reminder on failure."""
    try:
        return _parse_brief_json(llm.complete(prompt))
    except llm.LLMError:
        strict = (
            f"{prompt}\n\nIMPORTANT: reply with ONLY the JSON object — start with '{{' and "
            "end with '}}', no prose, no markdown, no code fences."
        )
        return _parse_brief_json(llm.complete(strict))


def _clean_brief(brief: ImageBrief) -> ImageBrief:
    """Scrub doses from all rendered text and drop items with a bad/empty category."""
    brief.title = _soften_alarming(_strip_clinical_quantities(brief.title))
    brief.condition_illustration = _strip_clinical_quantities(
        brief.condition_illustration
    )
    brief.labels = [
        scrubbed
        for label in brief.labels
        if (scrubbed := _strip_clinical_quantities(label))
    ]

    cleaned: list[ReferenceItem] = []
    for item in brief.reference_items:
        if item.category not in _VALID_CATEGORIES:
            continue
        item.label = _strip_clinical_quantities(item.label)
        if item.label:
            cleaned.append(item)
    brief.reference_items = cleaned
    return brief


def minimal_brief(conditions: list[str], target_audience: str) -> ImageBrief:
    """Fallback brief for when the extraction LLM is unavailable or returns bad output."""
    primary = re.sub(r"\s*\([^)]*\)", "", conditions[0]).strip() if conditions else ""
    subject = primary or "condition"
    if target_audience == "patient":
        title = f"Your {subject}"
    else:
        title = f"Your loved one's {subject}"
    illustration = (
        f"A simple, calm labeled diagram of the body area affected by {primary}."
        if primary
        else "A simple, calm labeled medical diagram."
    )
    return _clean_brief(ImageBrief(title=title, condition_illustration=illustration))


def generate_image_brief(
    conditions: list[str],
    target_audience: str,
    summary_text: str = "",
    raw_clinical_text: str = "",
) -> ImageBrief:
    """Produce a structured, render-ready image brief via the configured text LLM.

    Raises LLMError (incl. LLMConfigError) if the provider fails or returns non-JSON.
    """
    audience_instruction = AUDIENCE_INSTRUCTIONS.get(
        target_audience, AUDIENCE_INSTRUCTIONS["patient"]
    )
    calm_title = (
        'Use plain, calm wording — do not use "emergency" or "crisis". Keep the title short '
        "and clear. When several conditions are present, base the title on the 1-2 most acute "
        "or primary ones (the main reason for this episode of care), not long-standing "
        "background conditions; keep each named condition's words intact (e.g. 'thyroid storm "
        "and high blood sugar') and do not merge or reorder them."
    )
    if target_audience == "patient":
        title_rule = (
            "Title: address the patient directly in second person — "
            f'"Your <condition in plain words>". {calm_title}'
        )
        voice_rule = (
            "Voice: speak to the patient as 'you'/'your' throughout — in the title, the "
            "labels, and every reference item. Keep the voice consistent."
        )
    else:
        title_rule = (
            "Title: address the family member about the patient — "
            f'"Your loved one\'s <condition in plain words>". {calm_title}'
        )
        voice_rule = (
            "Voice: speak to the family member throughout and refer to the patient in the "
            "third person (your loved one). Never address the patient as 'you'. Keep the "
            "voice consistent across the title, labels, and every reference item."
        )

    pronoun_rule = _pronoun_rule(_patient_gender(raw_clinical_text), target_audience)
    summary_clean = (
        " ".join(summary_text.split()) if summary_text else "(none provided)"
    )
    care_plan_text = "\n".join(_care_plan_lines(raw_clinical_text)) or "(none provided)"
    conditions_line = ", ".join(conditions) if conditions else "unspecified"

    prompt = (
        f"{IMAGE_BRIEF_SYSTEM_PROMPT}\n\n"
        f"Audience: {audience_instruction}\n"
        f"{title_rule}\n"
        f"{voice_rule}\n"
        f"{pronoun_rule}\n\n"
        f"Conditions: {conditions_line}\n\n"
        f"Approved patient summary:\n{summary_clean}\n\n"
        f"Care-plan notes (clinician-written; simplify, never copy doses):\n{care_plan_text}"
    )

    data = _complete_and_parse(prompt)
    try:
        brief = ImageBrief.model_validate(data)
    except Exception as exc:
        raise llm.LLMError(
            f"image brief did not match the expected schema: {exc}"
        ) from exc
    return _clean_brief(brief)
