"""Structured Client - LLM client with instructor support for tools."""

import logging
from typing import Any, AsyncIterator, Optional, Union

from .anthropic_client import AnthropicClient
from .base_client import BaseClient, GenerationResponse, Message, StreamEvent
from .gemini_client import GeminiClient
from .models import ModelID, ModelInfo, get_model, get_structured_output_model
from .openai_client import OpenAIClient

logger = logging.getLogger(__name__)


class StructuredClient(BaseClient):
    """
    Structured Client for tools that need precise structured outputs.

    Uses instructor for reliable structured generation.
    Used by tools, not agents.
    """

    def __init__(self, model: Optional[ModelID] = None, api_key: Optional[str] = None):
        """
        Initialize structured client.

        Args:
            model: Model ID enum (defaults to best structured output model)
            api_key: API key (optional, will use environment or .env)
        """
        # Use default structured output model if not specified
        if model is None:
            model_info = get_structured_output_model()
            self._model_id = ModelID(model_info.model_id)
        else:
            self._model_id = model
            model_info = get_model(model.value)

        # Create LLM provider first
        self.llm_provider = self._create_llm_client(self._model_id, model_info, api_key)
        # Then initialize parent with explicit api_key
        super().__init__(api_key=api_key)

        self.provider = model_info.provider.value
        self._initialized = False

    def _create_llm_client(
        self, model_id: ModelID, model_info: ModelInfo, api_key: Optional[str]
    ) -> BaseClient:
        """Create the appropriate LLM client based on model provider."""
        provider = model_info.provider.value
        model_string = model_id.value

        if provider == "anthropic":
            return AnthropicClient(api_key=api_key, default_model=model_string)
        elif provider == "openai":
            return OpenAIClient(api_key=api_key, default_model=model_string)
        elif provider == "google":
            return GeminiClient(api_key=api_key, default_model=model_string)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    def _get_api_key(self) -> str:
        """Get API key from underlying LLM client."""
        return self.llm_provider.api_key

    async def initialize(self) -> None:
        """Initialize the structured client and underlying LLM."""
        if self._initialized:
            return

        await self.llm_provider.initialize()
        self._initialized = True
        logger.info(f"Structured client initialized with {self.provider} provider")

    async def generate(
        self,
        messages: list[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[GenerationResponse, AsyncIterator[StreamEvent]]:
        """Generate text (delegates to underlying LLM)."""
        if not self._initialized:
            await self.initialize()

        return await self.llm_provider.generate(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            **kwargs,
        )

    async def generate_structured(
        self,
        messages: list[Message],
        response_model: type,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Generate structured output using instructor.

        This is the primary method for tools that need reliable structured outputs.
        """
        if not self._initialized:
            await self.initialize()

        return await self.llm_provider.generate_structured(
            messages=messages,
            response_model=response_model,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    async def close(self) -> None:
        """Close the structured client and underlying LLM."""
        if self.llm_provider:
            await self.llm_provider.close()
        self._initialized = False

    @property
    def name(self) -> str:
        """Client name."""
        return f"Structured-{self.provider}"

    @property
    def model(self) -> str:
        """Current model."""
        # Return the model ID value directly
        return self._model_id.value
