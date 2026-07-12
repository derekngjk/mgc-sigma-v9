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
    """Build a structured, brief-style prompt for gpt-image-2 / Nano Banana.

    Follows OpenAI's image-generation prompting guide (labeled sections rather
    than one long paragraph, quoted label text for reliable in-image rendering,
    explicit exclude list). The same structure works well for Nano Banana.

    Content is strictly grounded in the inputs: the illustration may only depict
    or label facts present in the conditions list and the written summary. The
    amount of detail scales with the length/richness of the summary — a short
    summary yields a sparse image, a detailed summary a denser one.
    """
    primary = conditions[0] if conditions else "the patient's medical condition"
    secondary = conditions[1:3]

    secondary_line = ""
    if secondary:
        secondary_line = (
            "Additional conditions from the same care record: "
            + ", ".join(f'"{c}"' for c in secondary)
            + ". Only depict or label these if the written summary below actually discusses them; otherwise ignore them."
        )

    # Embed the full summary verbatim as the factual source. Strip inline
    # markdown syntax; keep hyphens so compound words like "relapsing-remitting"
    # survive. List/blockquote markers at line start are handled separately.
    if summary_text:
        clean = re.sub(r"[#*_`>]", "", summary_text)
        clean = re.sub(r"(?m)^\s*-\s+", "", clean).strip()
        clean = " ".join(clean.split())
        source_line = (
            "Source content — this is the ONLY factual material to illustrate:\n"
            f'"""\n{clean}\n"""\n'
            "Every symptom, body region, medication, treatment step, care-team action, patient action, or clinical concept that appears in the image must be directly traceable to a phrase or idea in the text above. "
            "Do NOT introduce clinical detail that is not present in the text — no invented symptoms, no assumed treatments, no generic patient-education content added to fill space. "
            "Let the amount of detail follow the source: a brief summary → a sparse layout with only the elements it mentions; a detailed summary → a richer layout with more callouts. "
            "If the source is silent on a topic (body region, symptoms, treatment plan, etc.), the image must be silent on that topic too."
        )
    else:
        source_line = (
            "No written summary was provided. Keep the image minimal: a clear title label naming the condition and a simple, generic depiction of the concept. "
            "Do NOT invent symptoms, treatments, body regions, medications, or care actions."
        )

    sections = [
        f'Audience: an adult patient or family member reading a friendly care summary about "{primary}".',
        "Goal: a supportive, calming illustration that reflects only what the written summary describes. Not a clinical anatomical chart, not a diagnostic diagram.",
        "Format: 1024×1024 square, flat-vector medical infographic on a light background, with enough breathing room around each labeled element that every label is comfortably legible.",
        source_line,
        (
            "Rendered text and layout:\n"
            f'  - Include a clear title label naming the condition (for example "{primary}").\n'
            "  - Add a plain-language subtitle only if the summary provides one; otherwise omit it.\n"
            "  - Use callouts — each connected by a thin line to the part of the illustration it describes — only for concepts the summary actually covers. Prefer short descriptive phrases over single-word labels when a phrase communicates the idea more clearly.\n"
            "  - A reader who only glances at the image should come away with an accurate, self-contained understanding of what the summary says — no more, no less."
        ),
        secondary_line,
        "Colour palette: soft and reassuring — pale blues, warm ambers, sage greens. Avoid saturated reds and dark, ominous tones.",
        "Style keywords: flat illustration, consistent line weight, rounded shapes, subtle gradients, patient-education leaflet aesthetic, clear arrows and callout lines.",
        "Do NOT include: photorealistic bodies, wounds, blood, tears or distressed faces, medical instruments in use, long sentences or paragraphs of body text, watermarks, brand logos, unrelated icons, alarming red accents.",
    ]

    return "\n\n".join(s for s in sections if s)


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
