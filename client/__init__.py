"""Client module for LLM interactions."""

from .anthropic_client import AnthropicClient
from .base_provider_client import BaseProviderClient
from .llm_client import LLMClient
from .models import (
    REASONING_MODELS,
    STRUCTURED_OUTPUT_MODELS,
    ModelID,
    ModelInfo,
    ModelProvider,
    get_cheapest_model,
    get_model,
    get_model_for_client,
    get_model_for_tool,
    get_models_by_provider,
    get_reasoning_model,
    get_structured_output_model,
)
from .openai_client import OpenAIClient
from .types import (
    LLMMessage,
    LLMMessageRole,
    LLMStreamChunk,
    LLMStreamEvent,
    LLMStreamEventType,
    LLMTokenUsage,
)

__all__ = [
    # Base classes
    "BaseProviderClient",
    "LLMMessage",
    "LLMStreamChunk",
    "LLMStreamEvent",
    "LLMStreamEventType",
    "LLMTokenUsage",
    "LLMMessageRole",
    # Unified client
    "LLMClient",  # Single client for all LLM interactions
    # Direct client implementations (used by LLMClient)
    "AnthropicClient",
    "OpenAIClient",
    # Model registry
    "get_model",
    "get_models_by_provider",
    "get_cheapest_model",
    "get_reasoning_model",
    "get_structured_output_model",
    "get_model_for_client",
    "get_model_for_tool",
    "ModelProvider",
    "ModelInfo",
    "ModelID",
    "REASONING_MODELS",
    "STRUCTURED_OUTPUT_MODELS",
]
