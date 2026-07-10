"""LLM provider interface and error types."""

from typing import Protocol


class LLMError(Exception):
    """An LLM call failed."""


class LLMConfigError(LLMError):
    """The LLM provider is misconfigured (missing key or unknown provider)."""


class LLMProvider(Protocol):
    def complete(self, prompt: str, max_tokens: int = 1024) -> str: ...
