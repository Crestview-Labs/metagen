"""Client factory for creating LLM clients."""

from typing import Optional

from .anthropic_client import AnthropicClient
from .base_client import BaseClient
from .gemini_client import GeminiClient
from .models import ModelProvider, get_model
from .openai_client import OpenAIClient


class LLMClientFactory:
    """Factory for creating different types of LLM clients."""

    @staticmethod
    def create_client(
        provider: str, model: Optional[str] = None, api_key: Optional[str] = None
    ) -> BaseClient:
        """Create a basic LLM client for the specified provider."""
        provider_lower = provider.lower()

        # Handle provider aliases
        if provider_lower in ["anthropic", "claude"]:
            return AnthropicClient(api_key=api_key, default_model=model)
        elif provider_lower in ["openai", "gpt"]:
            return OpenAIClient(api_key=api_key, default_model=model)
        elif provider_lower in ["gemini", "google"]:
            return GeminiClient(api_key=api_key, default_model=model)
        else:
            raise ValueError(f"Unknown provider: {provider}")


def create_client(
    provider: str, api_key: Optional[str] = None, default_model: Optional[str] = None
) -> BaseClient:
    """Create an LLM client for the specified provider.

    Args:
        provider: Provider name ('anthropic', 'openai', 'google')
        api_key: API key for the provider (optional)
        default_model: Default model to use (optional)

    Returns:
        BaseClient instance for the provider

    Raises:
        ValueError: If provider is not supported
    """
    provider = provider.lower()

    if provider == "anthropic":
        return AnthropicClient(api_key=api_key, default_model=default_model)
    elif provider == "openai":
        return OpenAIClient(api_key=api_key, default_model=default_model)
    elif provider == "gemini":
        return GeminiClient(api_key=api_key, default_model=default_model)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def create_client_for_model(model_id: str, api_key: Optional[str] = None) -> BaseClient:
    """Create a client based on a specific model ID.

    Args:
        model_id: Model ID or alias (e.g., 'claude-sonnet-4-20250514', 'gpt-4o-mini')
        api_key: API key for the provider (optional)

    Returns:
        BaseClient instance configured for the model

    Raises:
        ValueError: If model is not found
    """
    model_info = get_model(model_id)

    if model_info.provider == ModelProvider.ANTHROPIC:
        return AnthropicClient(api_key=api_key, default_model=model_info.model_id)
    elif model_info.provider == ModelProvider.OPENAI:
        return OpenAIClient(api_key=api_key, default_model=model_info.model_id)
    elif model_info.provider == ModelProvider.GOOGLE:
        return GeminiClient(api_key=api_key, default_model=model_info.model_id)
    else:
        raise ValueError(f"Unsupported provider: {model_info.provider}")
