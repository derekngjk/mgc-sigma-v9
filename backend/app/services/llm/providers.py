"""Concrete LLMProvider implementations, one per vendor SDK."""

from app.config import settings
from app.services.llm.base import LLMConfigError, LLMError

ANTHROPIC_MODEL = "claude-opus-4-7"
OPENAI_MODEL = "gpt-4o"
GEMINI_MODEL = "gemini-3.5-flash"


class AnthropicProvider:
    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        if not settings.anthropic_api_key:
            raise LLMConfigError("ANTHROPIC_API_KEY is not set")
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        try:
            message = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text
        except Exception as exc:
            raise LLMError(f"Anthropic completion failed: {exc}") from exc


class OpenAIProvider:
    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        if not settings.openai_api_key:
            raise LLMConfigError("OPENAI_API_KEY is not set")
        import openai

        client = openai.OpenAI(api_key=settings.openai_api_key)
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as exc:
            raise LLMError(f"OpenAI completion failed: {exc}") from exc


class GoogleProvider:
    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        if not settings.gemini_api_key:
            raise LLMConfigError("GEMINI_API_KEY is not set")
        from google import genai

        client = genai.Client(api_key=settings.gemini_api_key)
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            return response.text
        except Exception as exc:
            raise LLMError(f"Google completion failed: {exc}") from exc
