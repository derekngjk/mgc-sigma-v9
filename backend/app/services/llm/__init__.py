"""Model-agnostic text LLM: provider registry and configured-provider entry point."""

from app.config import settings
from app.services.llm.base import LLMConfigError, LLMError, LLMProvider
from app.services.llm.providers import (
    AnthropicProvider,
    GoogleProvider,
    OpenAIProvider,
)

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "google": GoogleProvider,
}


def get_provider(name: str | None = None) -> LLMProvider:
    """Return the LLMProvider for `name`, defaulting to settings.llm_provider."""
    provider_name = name or settings.llm_provider
    provider_cls = _PROVIDERS.get(provider_name)
    if provider_cls is None:
        raise LLMConfigError(
            f"Unknown LLM_PROVIDER: {provider_name!r}. Use 'anthropic', 'openai', or 'google'."
        )
    return provider_cls()


def complete(prompt: str, max_tokens: int = 1024, provider: str | None = None) -> str:
    """
    Run a completion against `provider`, defaulting to the configured provider.
    """
    return get_provider(provider).complete(prompt, max_tokens)


__all__ = [
    "LLMConfigError",
    "LLMError",
    "LLMProvider",
    "complete",
    "get_provider",
]
