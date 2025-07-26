"""Base client interface for LLM generation."""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Union


class Role(str, Enum):
    """Message roles."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ToolErrorType(str, Enum):
    """Types of tool execution errors."""

    EXECUTION_ERROR = "execution_error"  # Tool threw exception
    LOOP_DETECTED = "loop_detected"  # Repeated calls detected
    RESOURCE_LIMIT = "resource_limit"  # Hit max tools/tokens
    USER_REJECTED = "user_rejected"  # User said no (future)
    INVALID_ARGS = "invalid_args"  # Bad parameters
    PERMISSION_DENIED = "permission_denied"  # Not authorized


# Error message templates for each error type
TOOL_ERROR_MESSAGES = {
    ToolErrorType.EXECUTION_ERROR: "Tool execution failed: {error_detail}",
    ToolErrorType.LOOP_DETECTED: (
        "Tool '{tool_name}' with arguments {tool_args} has been called {count} times. "
        "Skipping to prevent infinite loop."
    ),
    ToolErrorType.RESOURCE_LIMIT: (
        "Resource limit exceeded: {limit_type} ({current}/{max_allowed}). "
        "Cannot execute tool '{tool_name}'."
    ),
    ToolErrorType.USER_REJECTED: (
        "User rejected tool execution: '{tool_name}'. User feedback: {feedback}"
    ),
    ToolErrorType.INVALID_ARGS: "Invalid arguments for tool '{tool_name}': {validation_error}",
    ToolErrorType.PERMISSION_DENIED: "Permission denied for tool '{tool_name}': {reason}",
}


@dataclass
class ToolResult:
    """Represents a tool execution result."""

    tool_call_id: str  # ID from the original tool call
    tool_name: str
    content: str  # The actual result
    is_error: bool = False
    error_type: Optional[ToolErrorType] = None


@dataclass
class Message:
    """Represents a message in a conversation."""

    role: Role
    content: str
    tool_results: Optional[list[ToolResult]] = None  # For tool result messages
    tool_calls: Optional[list[dict[str, Any]]] = None  # For assistant tool calls

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for API calls.
        Note: Each provider client should handle tool results in their own format.
        """
        base: dict[str, Any] = {"role": self.role.value, "content": self.content}

        # Include raw data for provider-specific formatting
        if self.tool_results:
            base["tool_results"] = self.tool_results
        if self.tool_calls:
            base["tool_calls"] = self.tool_calls

        return base


@dataclass
class Usage:
    """Token usage information."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass
class GenerationResponse:
    """Response from an LLM generation request."""

    content: str
    usage: Optional[Usage] = None
    model: Optional[str] = None
    finish_reason: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None
    raw_response: Optional[Any] = None


@dataclass
class StreamChunk:
    """A chunk of streamed response."""

    content: Optional[str] = None
    finish_reason: Optional[str] = None


class StreamEventType(str, Enum):
    """Types of streaming events."""

    CONTENT = "content"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    # New events for tool approval flow
    TOOL_APPROVAL_REQUEST = "tool_approval_request"
    TOOL_APPROVED = "tool_approved"
    TOOL_REJECTED = "tool_rejected"
    AGENT_STATE = "agent_state"


@dataclass
class StreamEvent:
    """A streaming event that can represent different types of stream data."""

    type: StreamEventType
    content: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    chunk: Optional[StreamChunk] = None  # For content events

    @classmethod
    def from_content(cls, chunk: StreamChunk) -> "StreamEvent":
        """Create a content event from a StreamChunk."""
        return cls(type=StreamEventType.CONTENT, content=chunk.content, chunk=chunk)

    @classmethod
    def tool_call(cls, tool_name: str, tool_args: dict[str, Any]) -> "StreamEvent":
        """Create a tool call event."""
        args_str = ", ".join(f"{k}={v}" for k, v in tool_args.items())
        return cls(
            type=StreamEventType.TOOL_CALL,
            content=f"{tool_name}({args_str})",
            metadata={"tool_name": tool_name, "tool_args": tool_args},
        )

    @classmethod
    def tool_approval_request(
        cls, tool_name: str, tool_args: dict[str, Any], tool_id: str
    ) -> "StreamEvent":
        """Create a tool approval request event."""
        args_str = ", ".join(f"{k}={v}" for k, v in tool_args.items())
        return cls(
            type=StreamEventType.TOOL_APPROVAL_REQUEST,
            content=f"{tool_name}({args_str})",
            metadata={
                "tool_name": tool_name,
                "tool_args": tool_args,
                "tool_id": tool_id,
                "requires_approval": True,
            },
        )

    @classmethod
    def tool_approved(cls, tool_id: str, tool_name: str) -> "StreamEvent":
        """Create a tool approved event."""
        return cls(
            type=StreamEventType.TOOL_APPROVED,
            content=f"Tool approved: {tool_name}",
            metadata={"tool_id": tool_id, "tool_name": tool_name},
        )

    @classmethod
    def tool_rejected(
        cls, tool_id: str, tool_name: str, feedback: Optional[str] = None
    ) -> "StreamEvent":
        """Create a tool rejected event."""
        content = f"Tool rejected: {tool_name}"
        if feedback:
            content += f" - {feedback}"
        return cls(
            type=StreamEventType.TOOL_REJECTED,
            content=content,
            metadata={"tool_id": tool_id, "tool_name": tool_name, "feedback": feedback},
        )

    @classmethod
    def agent_state(cls, state: str, agent_id: str) -> "StreamEvent":
        """Create an agent state change event."""
        return cls(
            type=StreamEventType.AGENT_STATE,
            content=f"Agent state: {state}",
            metadata={"state": state, "agent_id": agent_id},
        )

    @classmethod
    def tool_result(
        cls,
        tool_name: str,
        success: bool,
        result: Optional[Any] = None,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None,
        error_type: Optional[ToolErrorType] = None,
    ) -> "StreamEvent":
        """Create a tool result event."""
        if success:
            metadata = {"tool_name": tool_name, "success": True, "result": result}
            if duration_ms is not None:
                metadata["duration_ms"] = duration_ms
            return cls(
                type=StreamEventType.TOOL_RESULT,
                content=f"Tool '{tool_name}' completed successfully",
                metadata=metadata,
            )
        else:
            metadata = {
                "tool_name": tool_name,
                "success": False,
                "error": error,
                "error_type": error_type.value if error_type else None,
            }
            if duration_ms is not None:
                metadata["duration_ms"] = duration_ms
            return cls(
                type=StreamEventType.TOOL_RESULT,
                content=f"Tool '{tool_name}' failed: {error}",
                metadata=metadata,
            )

    def is_tool_call(self) -> bool:
        """Check if this is a tool call event."""
        return self.type == StreamEventType.TOOL_CALL

    def is_tool_result(self) -> bool:
        """Check if this is a tool result event."""
        return self.type == StreamEventType.TOOL_RESULT

    def is_content(self) -> bool:
        """Check if this is a content event."""
        return self.type == StreamEventType.CONTENT

    def get_tool_name(self) -> Optional[str]:
        """Get tool name from metadata if this is a tool-related event."""
        return self.metadata.get("tool_name") if self.metadata else None

    def is_tool_success(self) -> bool:
        """Check if tool execution was successful (for tool result events)."""
        return self.metadata.get("success", False) if self.metadata else False


class BaseClient(ABC):
    """Abstract base class for LLM generation clients."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the client.

        Args:
            api_key: API key for the provider. If not provided, will look for
                    environment variables or /tmp/env.secrets
        """
        self.api_key = api_key or self._get_api_key()

    @abstractmethod
    def _get_api_key(self) -> str:
        """Get API key from environment or secrets file."""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the client (connect to services, etc.)."""
        pass

    @abstractmethod
    async def generate(
        self,
        messages: list[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[GenerationResponse, AsyncIterator[StreamEvent]]:
        """Generate text from the LLM.

        Args:
            messages: List of messages in the conversation
            model: Model to use (if None, uses default for provider)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            **kwargs: Additional provider-specific parameters

        Returns:
            GenerationResponse if stream=False, AsyncIterator[StreamChunk] if stream=True
        """
        pass

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[Message],
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

    async def __aenter__(self) -> "BaseClient":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    @staticmethod
    def load_secrets_from_file(file_path: Optional[str] = None) -> dict[str, str]:
        """Load secrets from a file.

        Args:
            file_path: Path to the secrets file. Defaults to finding .env in project root.

        Returns:
            Dictionary of environment variables
        """
        secrets = {}

        if file_path is None:
            # Find project root by looking for pyproject.toml
            current_dir = Path(__file__).resolve()
            for parent in current_dir.parents:
                if (parent / "pyproject.toml").exists():
                    env_path = parent / ".env"
                    if env_path.exists():
                        file_path = str(env_path)
                        break

        if file_path and os.path.exists(file_path):
            with open(file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        secrets[key.strip()] = value.strip().strip('"').strip("'")

        return secrets
