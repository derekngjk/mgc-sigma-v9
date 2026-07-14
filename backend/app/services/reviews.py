"""
Independent second-pass review of a generated summary against the source facts.

A second LLM instance sees only the clinical facts and the finished draft,
without the generator's reasoning. Reports what the draft claims but cannot support,
what it misses out, and what it oversimplifies dangerously.

If reviewer call fails for whatever reason, default to review unavailable.
"""

import json
import re
from typing import Any

from app.config import settings
from app.services import llm
from app.services.prompts import REVIEW_SYSTEM_PROMPT

__all__ = ["verify_summary"]

_CATEGORIES = ("unsupported_claims", "omissions", "risky_simplifications")


def _neutral_verdict(note: str) -> dict[str, Any]:
    # used when reviewer call fails
    return {
        "verdict": "unavailable",
        "unsupported_claims": [],
        "omissions": [],
        "risky_simplifications": [],
        "note": note,
    }


def _parse_verdict(raw: str) -> dict[str, Any]:
    """
    Parse the reviewer's JSON into a normalised verdict. If parse failure,
    set to review unavailable
    """
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return _neutral_verdict("Review response was not valid JSON")
    if not isinstance(parsed, dict):
        return _neutral_verdict("Review response was not a JSON object")

    flags: dict[str, list[str]] = {}
    for category in _CATEGORIES:
        value = parsed.get(category, [])
        flags[category] = (
            [str(item).strip() for item in value if str(item).strip()]
            if isinstance(value, list)
            else []
        )

    has_flags = any(flags[category] for category in _CATEGORIES)
    return {
        "verdict": "warnings" if has_flags else "ok",
        **flags,
        "note": "",
    }


def verify_summary(
    raw_clinical_text: str,
    conditions: list[str],
    summary_text: str,
) -> dict[str, Any]:
    """
    Review `summary_text` against the clinical facts using the reviewer provider.

    Returns a dict with keys: verdict ('ok' | 'warnings' | 'unavailable'),
    unsupported_claims, omissions, risky_simplifications, note. Never raises.
    """
    prompt = (
        f"{REVIEW_SYSTEM_PROMPT}\n\n"
        f"Active conditions (parsed): {', '.join(conditions) if conditions else '(none parsed)'}\n\n"
        f"Clinical facts (JSON source of truth):\n{raw_clinical_text}\n\n"
        f"Drafted patient-facing summary to review:\n{summary_text}"
    )
    try:
        raw = llm.complete(prompt, provider=settings.reviewer_provider)
    except llm.LLMError as exc:
        return _neutral_verdict(f"Review unavailable: {exc}")
    return _parse_verdict(raw)
