"""Type definitions for LLM client module.

These types are used internally by the LLM client and provider implementations.
For public API types, see common/messages.py.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class LLMMessageRole(str, Enum):
    """Message roles in LLM conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class LLMMessage(BaseModel):
    """Message format for LLM providers.

    This is the internal format used for communication between:
    1. LLMClient → Provider clients: Input messages for generation
    2. Provider clients → LLMClient: Response messages with results

    The public API uses the Message types from common/messages.py.
    Agents never see or use LLMMessage directly.
    """

    role: LLMMessageRole
    content: str = ""  # Default empty string for tool-only responses
    name: Optional[str] = None
    tool_calls: Optional[list[Any]] = None  # Provider-specific tool call format
    tool_call_id: Optional[str] = None
    tool_call_results: Optional[list[Any]] = None  # For TOOL role messages
    finish_reason: Optional[str] = None  # For responses: stop, tool_calls, etc
    usage: Optional["LLMTokenUsage"] = None  # For responses: token usage info
    model: Optional[str] = None  # For responses: model that generated this

    class Config:
        """Pydantic configuration."""

        json_encoders = {LLMMessageRole: lambda v: v.value}

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Override to ensure enums are serialized as strings."""
        data = super().model_dump(**kwargs)
        if "role" in data and isinstance(data["role"], LLMMessageRole):
            data["role"] = data["role"].value
        return data


@dataclass
class LLMTokenUsage:
    """Token usage information."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass
class LLMStreamChunk:
    """A chunk of streaming content."""

    content: str
    role: Optional[LLMMessageRole] = None
    finish_reason: Optional[str] = None


# Internal streaming types for provider clients
class LLMStreamEventType(str, Enum):
    """Types of streaming events internal to LLM client providers.

    These are only used internally by provider clients (Anthropic, OpenAI, etc).
    The LLMClient converts these to proper Message objects.
    """

    CONTENT = "content"  # Streaming text content
    ERROR = "error"  # Error during streaming
    USAGE = "usage"  # Token usage information


@dataclass
class LLMStreamEvent:
    """A streaming event that can represent different types of stream data.

    Internal to LLM client module - not part of public API.
    """

    type: LLMStreamEventType
    content: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    chunk: Optional[LLMStreamChunk] = None  # For content events

    @classmethod
    def from_content(cls, chunk: LLMStreamChunk) -> "LLMStreamEvent":
        """Create a content event from a LLMStreamChunk."""
        return cls(type=LLMStreamEventType.CONTENT, content=chunk.content, chunk=chunk)

    @classmethod
    def usage(cls, input_tokens: int, output_tokens: int, total_tokens: int) -> "LLMStreamEvent":
        """Create a usage event with token counts."""
        return cls(
            type=LLMStreamEventType.USAGE,
            content=None,
            metadata={
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                }
            },
        )

    @classmethod
    def error(cls, error: str) -> "LLMStreamEvent":
        """Create an error event."""
        return cls(type=LLMStreamEventType.ERROR, content=error, metadata={"error": error})
