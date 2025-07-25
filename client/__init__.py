"""Client module for LLM interactions."""

from .agentic_client import AgenticClient
from .anthropic_client import AnthropicClient
from .base_client import BaseClient, GenerationResponse, Message, Role, StreamChunk, Usage
from .factory import LLMClientFactory, create_client, create_client_for_model
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
from .structured_client import StructuredClient

__all__ = [
    # Base classes
    "BaseClient",
    "Message",
    "GenerationResponse",
    "StreamChunk",
    "Usage",
    "Role",
    # Client types
    "AgenticClient",  # For agents - LLM + tool calling
    "StructuredClient",  # For tools - instructor-based structured outputs
    # Direct client implementations (used by above)
    "AnthropicClient",
    "OpenAIClient",
    # Factory functions
    "create_client",
    "create_client_for_model",
    "LLMClientFactory",
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
