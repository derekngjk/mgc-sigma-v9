import base64
import os
import re


class ImageConfigError(Exception):
    pass


class ImageError(Exception):
    pass


def _make_image_prompt(conditions: list[str], summary_text: str = "") -> str:
    """Build a warm, layperson-friendly illustration prompt (a reassuring scene, not a clinical diagram)."""
    primary = conditions[0] if conditions else "the patient's medical condition"
    all_conds = ", ".join(conditions[:3]) if conditions else "the patient's medical condition"

    # Strip markdown and take the first ~240 chars as context for the image model
    context_snippet = ""
    if summary_text:
        clean = re.sub(r"[#*_`>\-]", "", summary_text).strip()
        clean = " ".join(clean.split())[:240]
        context_snippet = (
            f' The picture should echo the caring, reassuring message of this patient summary: "{clean}".'
        )

    return (
        f"A warm, friendly illustration to help a patient and their family feel calm and supported "
        f"while coping with {all_conds}.{context_snippet} "
        "Show a gentle, hopeful everyday scene — for example a person resting comfortably at home, "
        "drinking water, taking their medicine, going for a light walk, or being comforted by a caring "
        "family member or nurse — that conveys reassurance and simple self-care rather than clinical detail. "
        "Style: soft, rounded, modern flat illustration like a friendly health app or wellness brochure, "
        "with a calm, reassuring colour palette (pale blues, warm ambers, sage greens) and a light background. "
        "Keep it simple, human and uplifting. Do NOT draw anatomy, organs, medical diagrams, charts, needles, "
        "blood, surgery, or anything frightening. Avoid any text, letters, numbers, or words in the image, "
        "as text tends to render incorrectly. "
        f"The goal is emotional reassurance and comfort for someone living with {primary}."
    )


def generate_visual(conditions: list[str], summary_text: str = "") -> bytes:
    """Generate a supportive illustration via Imagen 3 (imagen-3.0-generate-002).

    Falls back to Nano Banana (gemini-2.5-flash-image) if Imagen is unavailable.
    Returns PNG bytes.
    Raises ImageConfigError if GEMINI_API_KEY is not set.
    Raises ImageError on API failure.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ImageConfigError("GEMINI_API_KEY not set")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    prompt = _make_image_prompt(conditions, summary_text)

    try:
        response = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=prompt,
            config=types.GenerateImagesConfig(number_of_images=1),
        )
        return response.generated_images[0].image.image_bytes
    except Exception as imagen_exc:
        # Fall back to Nano Banana interactions API
        try:
            interaction = client.interactions.create(
                model="gemini-2.5-flash-image",
                input=prompt,
            )
            return base64.b64decode(interaction.output_image.data)
        except Exception as nb_exc:
            raise ImageError(
                f"Image generation failed. Imagen: {imagen_exc}. Nano Banana: {nb_exc}"
            ) from nb_exc
