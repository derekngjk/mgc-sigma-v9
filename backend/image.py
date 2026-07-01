import base64
import os
import re


class ImageConfigError(Exception):
    pass


class ImageError(Exception):
    pass


def _make_image_prompt(conditions: list[str], summary_text: str = "") -> str:
    """Build a specific, labeled educational diagram prompt from conditions and summary."""
    primary = conditions[0] if conditions else "the patient's medical condition"
    all_conds = " and ".join(conditions[:3]) if conditions else "the patient's medical condition"

    # Strip markdown and take the first ~200 chars as context for the image model
    context_snippet = ""
    if summary_text:
        clean = re.sub(r"[#*_`>\-]", "", summary_text).strip()
        clean = " ".join(clean.split())[:200]
        context_snippet = f' Context from the patient summary: "{clean}..."'

    return (
        f"An informative, labeled medical illustration for a patient education document about {all_conds}.{context_snippet} "
        f"Style: clean educational diagram with a soft, reassuring colour palette (pale blues, warm ambers, sage greens). "
        f"Include clear text labels and callout lines identifying the key anatomical structures or treatment concepts "
        f"relevant to {primary}. Labels should name the specific condition, affected body area, or treatment step. "
        "Layout: professional medical infographic — approachable and clear, not graphic or alarming. "
        "Light background. Suitable for a hospital patient information leaflet."
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
