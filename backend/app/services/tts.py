"""Text-to-speech via OpenAI, plus Markdown/sentence helpers for the audio route."""

import re

from app.config import settings
from app.services.llm import LLMConfigError


def strip_markdown(text: str) -> str:
    """Remove Markdown syntax before TTS — mirrors frontend/src/lib/markdown.ts."""
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"\*(.+?)\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"^[-*+]\s+", "", text, flags=re.MULTILINE)
    return text.strip()


def split_sentences(text: str) -> list[str]:
    """Split stripped text into sentences for client-side proportional highlighting."""
    sentences: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"(?<=[.!?])\s+", line)
        sentences.extend(p.strip() for p in parts if p.strip())
    return sentences


def generate_tts(text: str) -> bytes:
    """Call OpenAI tts-1 (voice=alloy) and return MP3 bytes.

    Raises LLMConfigError if OPENAI_API_KEY is not set.
    """
    if not settings.openai_api_key:
        raise LLMConfigError("OPENAI_API_KEY not set")
    from openai import OpenAI

    client = OpenAI()
    response = client.audio.speech.create(model="tts-1", voice="alloy", input=text)
    return response.content
