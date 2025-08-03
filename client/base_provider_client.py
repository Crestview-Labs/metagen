"""Base provider client interface for LLM providers."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Optional, Union

from client.types import LLMMessage, LLMStreamEvent
from tools.base import Tool


class BaseProviderClient(ABC):
    """Abstract base class for LLM provider clients."""

    def __init__(self, api_key: str):
        """Initialize the provider client.

        Args:
            api_key: API key for the provider
        """
        self.api_key = api_key

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the client (connect to services, etc.)."""
        pass

    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        tools: Optional[list[Tool]] = None,
        **kwargs: Any,
    ) -> Union[LLMMessage, AsyncIterator[LLMStreamEvent]]:
        """Generate text from the LLM.

        Args:
            messages: List of messages in the conversation
            model: Model to use (if None, uses default for provider)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            tools: Optional list of tools available for the model
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMMessage if stream=False, AsyncIterator[LLMStreamEvent] if stream=True
        """
        pass

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[LLMMessage],
        response_model: type[Any],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        """Generate structured output using Instructor.

        Args:
            messages: List of messages in the conversation
            response_model: Pydantic model class for the response
            model: Model to use (if None, uses default for provider)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            Instance of response_model with structured data
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close any open connections."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider client name."""
        pass
