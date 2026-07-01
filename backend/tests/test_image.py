import base64
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from image import ImageConfigError, ImageError, _make_image_prompt, generate_visual
from main import app


# ── unit tests for image.py ───────────────────────────────────────────────────


def test_make_image_prompt_includes_condition():
    prompt = _make_image_prompt(["invasive ductal carcinoma", "nausea"])
    assert "invasive ductal carcinoma" in prompt
    # Only the first two conditions are used
    assert "nausea" in prompt


def test_make_image_prompt_no_conditions():
    prompt = _make_image_prompt([])
    assert "medical condition" in prompt


def test_generate_visual_gemini_calls_nano_banana_primary(monkeypatch):
    fake_png = b"\x89PNG\r\n\x1a\nfakedata"
    fake_b64 = base64.b64encode(fake_png).decode()

    fake_interaction = MagicMock()
    fake_interaction.output_image.data = fake_b64

    fake_client = MagicMock()
    fake_client.interactions.create.return_value = fake_interaction

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_PROVIDER", "gemini")

    with patch("google.genai.Client", return_value=fake_client):
        result = generate_visual(
            ["breast cancer"], "Your care summary explains the treatment plan."
        )

    assert result == fake_png
    call_kwargs = fake_client.interactions.create.call_args.kwargs
    assert call_kwargs["model"] == "gemini-3.1-flash-image"
    assert "breast cancer" in call_kwargs["input"]
    assert "treatment plan" in call_kwargs["input"]
    fake_client.models.generate_images.assert_not_called()


def test_generate_visual_gemini_falls_back_to_imagen(monkeypatch):
    fake_png = b"\x89PNG\r\n\x1a\nfakedata"

    fake_image = MagicMock()
    fake_image.image.image_bytes = fake_png

    fake_client = MagicMock()
    fake_client.interactions.create.side_effect = RuntimeError("nano banana down")
    fake_client.models.generate_images.return_value.generated_images = [fake_image]

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_PROVIDER", "gemini")

    with patch("google.genai.Client", return_value=fake_client):
        result = generate_visual(["breast cancer"])

    assert result == fake_png
    imagen_call = fake_client.models.generate_images.call_args
    assert imagen_call.kwargs["model"] == "imagen-4.0-generate-001"


def test_generate_visual_missing_gemini_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("IMAGE_PROVIDER", "gemini")
    with pytest.raises(ImageConfigError, match="GEMINI_API_KEY not set"):
        generate_visual(["some condition"])


def test_generate_visual_both_gemini_apis_fail_raises(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("IMAGE_PROVIDER", "gemini")

    fake_client = MagicMock()
    fake_client.interactions.create.side_effect = RuntimeError("nano banana down")
    fake_client.models.generate_images.side_effect = RuntimeError("imagen down")

    with patch("google.genai.Client", return_value=fake_client):
        with pytest.raises(ImageError, match="Image generation failed") as exc_info:
            generate_visual(["some condition"])

    msg = str(exc_info.value)
    assert "nano banana down" in msg.lower() or "Nano Banana" in msg
    assert "imagen down" in msg.lower() or "Imagen" in msg


def test_generate_visual_openai_provider_calls_gpt_image_2(monkeypatch):
    fake_png = b"\x89PNG\r\n\x1a\nfakedata"
    fake_b64 = base64.b64encode(fake_png).decode()

    fake_data_item = MagicMock()
    fake_data_item.b64_json = fake_b64
    fake_response = MagicMock()
    fake_response.data = [fake_data_item]

    fake_client = MagicMock()
    fake_client.images.generate.return_value = fake_response

    monkeypatch.setenv("IMAGE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with patch("openai.OpenAI", return_value=fake_client):
        result = generate_visual(["breast cancer"], "Treatment plan summary.")

    assert result == fake_png
    call_kwargs = fake_client.images.generate.call_args.kwargs
    assert call_kwargs["model"] == "gpt-image-2"
    assert call_kwargs["quality"] == "medium"
    assert call_kwargs["size"] == "1024x1024"
    assert "breast cancer" in call_kwargs["prompt"]


def test_generate_visual_openai_missing_key_raises(monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ImageConfigError, match="OPENAI_API_KEY not set"):
        generate_visual(["some condition"])


def test_generate_visual_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER", "midjourney")
    with pytest.raises(ImageConfigError, match="Unknown IMAGE_PROVIDER"):
        generate_visual(["some condition"])


# ── route-level tests ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    with patch.dict(
        "os.environ",
        {
            "SUPABASE_URL": "https://placeholder.supabase.co",
            "SUPABASE_KEY": "placeholder",
            "SUPABASE_DB_URL": "postgresql://user:pass@localhost:5432/db",
        },
    ):
        with TestClient(app) as c:
            yield c


def test_approve_calls_image_generation_when_flag_true(client, mock_supabase):
    comm_record = {
        "id": "comm-001",
        "patient_id": "patient-uuid",
        "patient_name": "Tan Mei Ling",
        "status": "Approved",
        "ai_summary_text": "Your care summary.",
        "approved_at": "2026-06-25T10:00:00+00:00",
        "target_audience": "patient",
        "conditions_json": json.dumps(["invasive ductal carcinoma"]),
        "condition_diff": json.dumps({"added": [], "removed": [], "ongoing": []}),
        "translations_json": {},
        "audio_urls_json": {},
        "image_url": None,
    }
    mock_supabase.table("care_plan_translations").execute.side_effect = [
        MagicMock(data=[comm_record]),  # get_communication (pre-update check)
        MagicMock(data=[comm_record]),  # update_communication
        MagicMock(data=[comm_record]),  # get_communication (post-update read)
    ]
    mock_supabase.table("patients").execute.return_value = MagicMock(data=[])
    mock_supabase.table("families").execute.return_value = MagicMock(
        data=[{"id": "fam-uuid"}]
    )
    mock_supabase.table("family_members").execute.return_value = MagicMock(
        data=[{"id": "mem-uuid"}]
    )

    import main as main_module

    with patch.object(main_module, "_generate_and_cache_image") as mock_fn:
        res = client.post(
            "/api/communications/comm-001/approve",
            json={"ai_summary_text": "Your care summary.", "generate_image": True},
        )
    assert res.status_code == 200
    mock_fn.assert_called_once_with(
        "comm-001", ["invasive ductal carcinoma"], "Your care summary."
    )


def test_approve_skips_image_generation_when_flag_false(client, mock_supabase):
    comm_record = {
        "id": "comm-002",
        "patient_id": "patient-uuid",
        "patient_name": "Tan Mei Ling",
        "status": "Approved",
        "ai_summary_text": "Your care summary.",
        "approved_at": "2026-06-25T10:00:00+00:00",
        "target_audience": "patient",
        "conditions_json": json.dumps(["invasive ductal carcinoma"]),
        "condition_diff": json.dumps({"added": [], "removed": [], "ongoing": []}),
        "translations_json": {},
        "audio_urls_json": {},
        "image_url": None,
    }
    mock_supabase.table("care_plan_translations").execute.side_effect = [
        MagicMock(data=[comm_record]),
        MagicMock(data=[comm_record]),
        MagicMock(data=[comm_record]),
    ]
    mock_supabase.table("families").execute.return_value = MagicMock(
        data=[{"id": "fam-uuid"}]
    )
    mock_supabase.table("family_members").execute.return_value = MagicMock(
        data=[{"id": "mem-uuid"}]
    )

    import main as main_module

    with patch.object(main_module, "_generate_and_cache_image") as mock_fn:
        res = client.post(
            "/api/communications/comm-002/approve",
            json={"ai_summary_text": "Your care summary.", "generate_image": False},
        )
    assert res.status_code == 200
    mock_fn.assert_not_called()
