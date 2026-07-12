"""Educational visual-aid generation — renders a structured ImageBrief, dispatching on IMAGE_PROVIDER."""

import base64
import logging

from app.config import settings
from app.services.image_brief import ImageBrief

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


def _make_image_prompt(brief: ImageBrief) -> str:
    """Render a patient-education infographic prompt from a structured image brief.

    The brief is already grounded, audience-correct, and dose-free, so this is a pure
    rendering spec — the image model illustrates exactly what the brief specifies.
    """
    main_lines = [
        "Layout — two zones:",
        "  - MAIN (centered, ~60% of the canvas): illustrate the scene described here. This "
        "description is DRAWING GUIDANCE ONLY — do NOT write these sentences anywhere in the "
        "image.",
        f"    Scene to draw: {brief.condition_illustration}",
        f'    Title label (render verbatim, large, across the top): "{brief.title}".',
    ]
    if brief.labels:
        label_list = ", ".join(f'"{label}"' for label in brief.labels)
        main_lines.append(
            "    Label the drawn parts with ONLY these short callouts, each rendered verbatim "
            f"and joined by a thin line to the part it names: {label_list}."
        )

    sections: list[str] = [
        "This is a patient-education infographic — a calm, supportive visual, not a "
        "clinical anatomical chart or diagnostic diagram.",
        "Format: 1024x1024 square, flat-vector illustration on a light background, with "
        "generous whitespace so every label is comfortably legible.",
        "\n".join(main_lines),
    ]

    groups = (
        ("watch", "WARNING", "Get help right away", "soft red"),
        ("do", "DO", "Things you can do", "soft green"),
        ("dont", "DON'T", "Things to avoid", "soft amber"),
    )
    group_blocks: list[str] = []
    for category, header, subtitle, tint in groups:
        items = [i for i in brief.reference_items if i.category == category]
        if not items:
            continue
        rows = "\n".join(f'      - {i.icon} icon + "{i.label}"' for i in items)
        group_blocks.append(
            f'  {header} card ({tint} tint): a bold "{header}" header with the subtitle '
            f'"{subtitle}", then these rows, each a small contextual icon beside its short '
            f"text:\n{rows}"
        )
    if group_blocks:
        sections.append(
            "REFERENCE SIDEBAR (right column, ~35% of the canvas): stacked, clearly separated "
            "rounded cards — one per group below, in this order. Render only the groups "
            "listed:\n" + "\n".join(group_blocks)
        )

    sections.append(
        "The ONLY text allowed in the image is: the title, the short part labels, and the "
        "sidebar headers, subtitles, and item labels listed above. Do NOT render the scene "
        "description or any other sentences as image text. Put label text in quotes; keep it "
        "legible; avoid tiny text."
    )
    sections.append(
        "Style: clean, flat visual system with a consistent icon style, clear thin callout "
        "lines, rounded shapes, and readable labels. Colour palette: soft and reassuring — "
        "pale blues, warm ambers, sage greens; avoid saturated reds and dark, ominous tones."
    )
    sections.append(
        "Do NOT include: photorealistic bodies, wounds, blood, tears or distressed faces, "
        "medical instruments in use, numeric doses/units/lab values, long sentences or dense "
        "body text, watermarks, brand logos, unrelated icons, or alarming red accents."
    )

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


def generate_visual(brief: ImageBrief) -> bytes:
    """Generate a supportive illustration as PNG bytes from a brief, dispatching on IMAGE_PROVIDER.

    Raises ImageConfigError on missing keys / unknown provider, ImageError on API failure.
    """
    provider = settings.image_provider.lower()
    logger.info("generate_visual: provider=%s, title=%r", provider, brief.title)
    prompt = _make_image_prompt(brief)
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
