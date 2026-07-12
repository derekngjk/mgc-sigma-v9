"""Tests for the structured image-brief extraction step."""

import json

import pytest

from app.services import llm
from app.services.image_brief import (
    ImageBrief,
    _care_plan_lines,
    _clean_brief,
    _parse_brief_json,
    _strip_clinical_quantities,
    generate_image_brief,
    minimal_brief,
)

VALID_JSON = json.dumps(
    {
        "title": "Your diabetes",
        "condition_illustration": (
            "A pancreas making little insulin, with sugar building up in the blood."
        ),
        "labels": ["Pancreas: low insulin", "Sugar in blood"],
        "reference_items": [
            {
                "category": "do",
                "icon": "pill-clock",
                "label": "Take Metformin 500 mg with meals",
            },
            {"category": "dont", "icon": "leaf", "label": "Avoid sugary drinks"},
            {"category": "bogus", "icon": "x", "label": "should be dropped"},
        ],
    }
)


# ── generate_image_brief ──────────────────────────────────────────────────────


def test_generate_image_brief_parses_and_scrubs(monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda prompt, **_: VALID_JSON)
    brief = generate_image_brief(
        ["type 2 diabetes"], "patient", "You have diabetes.", ""
    )

    assert isinstance(brief, ImageBrief)
    assert brief.title == "Your diabetes"
    assert "Pancreas: low insulin" in brief.labels
    labels = [i.label for i in brief.reference_items]
    # Dose scrubbed from a reference label, drug name kept.
    assert any("Metformin" in label and "500 mg" not in label for label in labels)
    # Unknown category dropped.
    assert all(i.category != "bogus" for i in brief.reference_items)


def test_generate_image_brief_handles_fenced_json(monkeypatch):
    fenced = f"```json\n{VALID_JSON}\n```"
    monkeypatch.setattr(llm, "complete", lambda prompt, **_: fenced)
    brief = generate_image_brief(["type 2 diabetes"], "patient", "x", "")
    assert brief.condition_illustration.startswith("A pancreas")


def test_generate_image_brief_malformed_raises(monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda prompt, **_: "sorry, no JSON here")
    with pytest.raises(llm.LLMError):
        generate_image_brief(["type 2 diabetes"], "patient", "x", "")


def test_generate_image_brief_prompt_carries_audience_voice(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(
        llm, "complete", lambda p, **_: captured.append(p) or VALID_JSON
    )

    generate_image_brief(["asthma"], "patient", "x", "")
    assert "Your <condition" in captured[0]
    assert '"emergency" or "crisis"' in captured[0]

    generate_image_brief(["asthma"], "spouse", "x", "")
    assert "Your loved one's <condition" in captured[1]
    assert "Never address the patient as 'you'" in captured[1]


def test_generate_image_brief_prompt_carries_pronoun_rule(monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(
        llm, "complete", lambda p, **_: captured.append(p) or VALID_JSON
    )

    generate_image_brief(["asthma"], "spouse", "", json.dumps({"gender": "female"}))
    assert "she/her" in captured[0]

    generate_image_brief(["asthma"], "spouse", "", json.dumps({"care_plans": {}}))
    assert "avoid gendered pronouns" in captured[1]


def test_generate_image_brief_retries_once_on_bad_json(monkeypatch):
    calls = {"n": 0}

    def fake_complete(prompt: str, **_: object) -> str:
        calls["n"] += 1
        return "not json at all" if calls["n"] == 1 else VALID_JSON

    monkeypatch.setattr(llm, "complete", fake_complete)
    brief = generate_image_brief(["asthma"], "patient", "x", "")
    assert brief.title == "Your diabetes"
    assert calls["n"] == 2


# ── minimal_brief fallback ────────────────────────────────────────────────────


def test_parse_brief_json_handles_prose_and_trailing_commas():
    raw = (
        "Sure, here is the brief:\n"
        '{"title": "A", "condition_illustration": "B", "reference_items": [],}\n'
        "Let me know if you want changes."
    )
    data = _parse_brief_json(raw)
    assert data["title"] == "A"
    assert data["reference_items"] == []


def test_parse_brief_json_handles_prose_before_fenced_json():
    raw = 'Here you go:\n```json\n{"title": "A", "condition_illustration": "B"}\n```'
    assert _parse_brief_json(raw)["title"] == "A"


def test_minimal_brief_fallback_is_clean():
    brief = minimal_brief(["Thyroid storm (thyrotoxic crisis)"], "spouse")
    assert brief.title == "Your loved one's Thyroid storm"
    assert "crisis" not in brief.title.lower()


def test_clean_brief_softens_alarming_title():
    brief = ImageBrief(
        title="Your loved one's thyroid and diabetes emergency",
        condition_illustration="An overactive thyroid.",
    )
    _clean_brief(brief)
    assert "emergency" not in brief.title.lower()
    assert "crisis" not in brief.title.lower()
    assert brief.title == "Your loved one's thyroid and diabetes"


def test_minimal_brief_audience_titles():
    assert minimal_brief(["asthma"], "patient").title == "Your asthma"
    assert minimal_brief(["asthma"], "spouse").title == "Your loved one's asthma"
    assert minimal_brief([], "patient").title == "Your condition"


# ── helpers ───────────────────────────────────────────────────────────────────


def test_strip_clinical_quantities_removes_doses_keeps_timing():
    out = _strip_clinical_quantities("metformin 500 mg daily")
    assert "500 mg" not in out
    assert "daily" in out
    assert "0.9%" not in _strip_clinical_quantities("normal saline 0.9%")


def test_care_plan_lines_extracts_titles_and_activities():
    raw = json.dumps(
        {
            "care_plans": {
                "entry": [
                    {
                        "resource": {
                            "title": "Oncology plan",
                            "activity": [
                                {
                                    "detail": {
                                        "description": "Chemotherapy every 2 weeks"
                                    }
                                },
                                {"detail": {"description": "Anti-nausea medication"}},
                            ],
                        }
                    }
                ]
            }
        }
    )
    lines = _care_plan_lines(raw)
    assert "Oncology plan" in lines
    assert "Chemotherapy every 2 weeks" in lines
    assert "Anti-nausea medication" in lines


def test_care_plan_lines_handles_empty_and_malformed():
    assert _care_plan_lines("") == []
    assert _care_plan_lines("not json {") == []
    assert _care_plan_lines(json.dumps({"conditions": {}})) == []
