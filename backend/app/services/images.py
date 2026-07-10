"""Educational visual-aid generation, dispatching on IMAGE_PROVIDER."""

import base64
import logging
import re

from app.config import settings

logger = logging.getLogger(__name__)


GEMINI_PRIMARY_MODEL = "gemini-3.1-flash-image"
GEMINI_FALLBACK_MODEL = "imagen-4.0-generate-001"
OPENAI_IMAGE_MODEL = "gpt-image-2"
OPENAI_IMAGE_QUALITY = "medium"
OPENAI_IMAGE_SIZE = "1024x1024"


class ImageConfigError(Exception):
    pass


class ImageError(Exception):
    pass


def _make_image_prompt(conditions: list[str], summary_text: str = "") -> str:
    """Build a specific, labeled educational diagram prompt from conditions and summary."""
    primary = conditions[0] if conditions else "the patient's medical condition"
    all_conds = (
        " and ".join(conditions[:3])
        if conditions
        else "the patient's medical condition"
    )

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


def _generate_via_gemini(prompt: str) -> bytes:
    """Nano Banana (gemini-3.1-flash-image) primary; Imagen 4 fallback."""
    if not settings.gemini_api_key:
        raise ImageConfigError("GEMINI_API_KEY not set")

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.gemini_api_key)

    try:
        interaction = client.interactions.create(
            model=GEMINI_PRIMARY_MODEL,
            input=prompt,
        )
        logger.info("gemini primary model succeeded (%s)", GEMINI_PRIMARY_MODEL)
        return base64.b64decode(interaction.output_image.data)
    except Exception as nb_exc:
        logger.warning(
            "gemini primary failed (%s), falling back to imagen (%s)",
            nb_exc,
            GEMINI_FALLBACK_MODEL,
        )
        try:
            response = client.models.generate_images(
                model=GEMINI_FALLBACK_MODEL,
                prompt=prompt,
                config=types.GenerateImagesConfig(number_of_images=1),
            )
            logger.info("imagen fallback succeeded (%s)", GEMINI_FALLBACK_MODEL)
            return response.generated_images[0].image.image_bytes
        except Exception as imagen_exc:
            logger.error(
                "gemini image generation failed on both models: nano_banana=%s imagen=%s",
                nb_exc,
                imagen_exc,
            )
            raise ImageError(
                f"Image generation failed. Nano Banana: {nb_exc}. Imagen: {imagen_exc}"
            ) from imagen_exc


def _generate_via_openai(prompt: str) -> bytes:
    """OpenAI gpt-image-2 at medium quality, 1024x1024, returned as PNG bytes."""
    if not settings.openai_api_key:
        raise ImageConfigError("OPENAI_API_KEY not set")

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)

    try:
        response = client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=prompt,
            quality=OPENAI_IMAGE_QUALITY,
            size=OPENAI_IMAGE_SIZE,
        )
        logger.info("openai model succeeded (%s)", OPENAI_IMAGE_MODEL)
        return base64.b64decode(response.data[0].b64_json)
    except Exception as exc:
        logger.error("openai image generation failed: %s", exc)
        raise ImageError(f"Image generation failed. OpenAI: {exc}") from exc


def generate_visual(conditions: list[str], summary_text: str = "") -> bytes:
    """Generate a supportive illustration as PNG bytes, dispatching on IMAGE_PROVIDER.

    Raises ImageConfigError on missing keys / unknown provider, ImageError on API failure.
    """
    provider = settings.image_provider.lower()
    logger.info(
        "generate_visual: provider=%s, %d conditions", provider, len(conditions)
    )
    prompt = _make_image_prompt(conditions, summary_text)
    logger.debug("image prompt: %s", prompt)

    if provider == "gemini":
        image_bytes = _generate_via_gemini(prompt)
    elif provider == "openai":
        image_bytes = _generate_via_openai(prompt)
    else:
        logger.error("unknown IMAGE_PROVIDER: %r", provider)
        raise ImageConfigError(
            f"Unknown IMAGE_PROVIDER: {provider!r}. Valid values: 'gemini', 'openai'."
        )

    logger.debug("image bytes returned: %d", len(image_bytes))
    return image_bytes
