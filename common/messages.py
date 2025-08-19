"""Unified message system for agent communication."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field

# Default agent IDs
DEFAULT_AGENT_ID = "METAGEN"  # Default agent ID for MetaAgent


class MessageType(str, Enum):
    """Types of messages in the system."""

    # Chat/content
    USER = "user"  # User message
    AGENT = "agent"  # Agent response
    SYSTEM = "system"  # System message
    THINKING = "thinking"  # Agent thinking/reasoning

    # Tool flow
    TOOL_CALL = "tool_call"  # LLM wants to call tools (contains full details)
    APPROVAL_REQUEST = "approval_request"  # Agent requests approval
    APPROVAL_RESPONSE = "approval_response"  # User approves/rejects
    TOOL_STARTED = "tool_started"  # Agent notifies tool execution started
    TOOL_RESULT = "tool_result"  # Agent sends tool result
    TOOL_ERROR = "tool_error"  # Agent sends tool error

    # Metadata
    USAGE = "usage"
    ERROR = "error"


class Message(BaseModel):
    """Base message class for all communication."""

    type: MessageType
    timestamp: datetime = Field(default_factory=datetime.now)
    agent_id: str = DEFAULT_AGENT_ID  # TODO: This should be set properly by each agent
    session_id: str  # Required - for routing responses to correct client(s)
    # TODO: Consider adding task_id as well for task context tracking
    # TODO: Review if we need both agent_id on Message base and on
    # specific messages like ApprovalRequest

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump(mode="json")


# Structured data models
class ToolCallRequest(BaseModel):
    """A single tool call request from the LLM."""

    tool_id: str
    tool_name: str
    tool_args: dict[str, Any]


# Chat messages
class ChatMessage(Message):
    """Base class for chat content messages."""

    content: str


class UserMessage(ChatMessage):
    """User chat message."""

    type: MessageType = MessageType.USER


class AgentMessage(ChatMessage):
    """Agent chat message."""

    type: MessageType = MessageType.AGENT
    final: bool = False  # Indicates if this is the final message in a response


class SystemMessage(ChatMessage):
    """System message for agent context."""

    type: MessageType = MessageType.SYSTEM


class ThinkingMessage(Message):
    """Agent thinking indicator."""

    type: MessageType = MessageType.THINKING
    content: str


# Tool flow messages
class ToolCallMessage(Message):
    """LLM wants to call tools - contains all tool call details."""

    type: MessageType = MessageType.TOOL_CALL
    tool_calls: list[ToolCallRequest]  # Properly typed tool calls


class ApprovalRequestMessage(Message):
    """Agent requests approval for a specific tool."""

    type: MessageType = MessageType.APPROVAL_REQUEST
    tool_id: str
    tool_name: str
    tool_args: dict[str, Any]


class ApprovalDecision(str, Enum):
    """Tool approval decisions."""

    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalResponseMessage(Message):
    """User responds to approval request."""

    type: MessageType = MessageType.APPROVAL_RESPONSE
    tool_id: str
    decision: ApprovalDecision
    feedback: Optional[str] = None


class ToolStartedMessage(Message):
    """Agent notifies tool execution started."""

    type: MessageType = MessageType.TOOL_STARTED
    tool_id: str
    tool_name: str


class ToolResultMessage(Message):
    """Agent sends tool execution result."""

    type: MessageType = MessageType.TOOL_RESULT
    tool_id: str
    tool_name: str
    result: Any


class ToolErrorMessage(Message):
    """Agent sends tool execution error."""

    type: MessageType = MessageType.TOOL_ERROR
    tool_id: str
    tool_name: str
    error: str


# Metadata messages
class UsageMessage(Message):
    """Token usage information."""

    type: MessageType = MessageType.USAGE
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ErrorMessage(Message):
    """Error message from agent."""

    type: MessageType = MessageType.ERROR
    error: str
    details: Optional[dict[str, Any]] = None


# Union type for all messages
AnyMessage = Union[
    UserMessage,
    AgentMessage,
    SystemMessage,
    ThinkingMessage,
    ToolCallMessage,
    ApprovalRequestMessage,
    ApprovalResponseMessage,
    ToolStartedMessage,
    ToolResultMessage,
    ToolErrorMessage,
    UsageMessage,
    ErrorMessage,
]

# SSE streaming message type - used for documenting the streaming endpoint
SSEMessage = AnyMessage  # Alias for clarity in API documentation


# Helper functions for message creation
def create_user_message(agent_id: str, session_id: str, content: str) -> UserMessage:
    """Create a user chat message."""
    return UserMessage(agent_id=agent_id, session_id=session_id, content=content)


def create_agent_message(agent_id: str, session_id: str, content: str) -> AgentMessage:
    """Create an agent chat message."""
    return AgentMessage(agent_id=agent_id, session_id=session_id, content=content)


def create_thinking_message(agent_id: str, session_id: str, message: str) -> ThinkingMessage:
    """Create a thinking indicator message."""
    return ThinkingMessage(agent_id=agent_id, session_id=session_id, content=message)


def create_tool_call_message(
    agent_id: str, session_id: str, tool_calls: list[ToolCallRequest]
) -> ToolCallMessage:
    """Create a tool call message."""
    return ToolCallMessage(agent_id=agent_id, session_id=session_id, tool_calls=tool_calls)


def create_approval_request(
    agent_id: str, session_id: str, tool_id: str, tool_name: str, tool_args: dict[str, Any]
) -> ApprovalRequestMessage:
    """Create an approval request message."""
    return ApprovalRequestMessage(
        agent_id=agent_id,
        session_id=session_id,
        tool_id=tool_id,
        tool_name=tool_name,
        tool_args=tool_args,
    )


def create_approval_response(
    agent_id: str,
    session_id: str,
    tool_id: str,
    decision: ApprovalDecision,
    feedback: Optional[str] = None,
) -> ApprovalResponseMessage:
    """Create an approval response message."""
    return ApprovalResponseMessage(
        agent_id=agent_id,
        session_id=session_id,
        tool_id=tool_id,
        decision=decision,
        feedback=feedback,
    )


def create_tool_started(
    agent_id: str, session_id: str, tool_id: str, tool_name: str
) -> ToolStartedMessage:
    """Create a tool started notification."""
    return ToolStartedMessage(
        agent_id=agent_id, session_id=session_id, tool_id=tool_id, tool_name=tool_name
    )


def create_tool_result(
    agent_id: str, session_id: str, tool_id: str, tool_name: str, result: Any
) -> ToolResultMessage:
    """Create a tool result message."""
    return ToolResultMessage(
        agent_id=agent_id,
        session_id=session_id,
        tool_id=tool_id,
        tool_name=tool_name,
        result=result,
    )


def create_tool_error(
    agent_id: str, session_id: str, tool_id: str, tool_name: str, error: str
) -> ToolErrorMessage:
    """Create a tool error message."""
    return ToolErrorMessage(
        agent_id=agent_id, session_id=session_id, tool_id=tool_id, tool_name=tool_name, error=error
    )


def create_usage_message(
    agent_id: str, session_id: str, input_tokens: int, output_tokens: int, total_tokens: int
) -> UsageMessage:
    """Create a usage statistics message."""
    return UsageMessage(
        agent_id=agent_id,
        session_id=session_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def create_error_message(
    agent_id: str, session_id: str, error: str, details: Optional[dict[str, Any]] = None
) -> ErrorMessage:
    """Create an error message."""
    return ErrorMessage(agent_id=agent_id, session_id=session_id, error=error, details=details)


def message_from_dict(data: dict[str, Any]) -> Message:
    """Reconstruct a Message object from a dictionary.

    Args:
        data: Dictionary with message data including 'type' field

    Returns:
        Appropriate Message subclass instance

    Raises:
        ValueError: If message type is unknown
    """
    msg_type = data.get("type")
    if msg_type is None:
        raise ValueError("Missing 'type' field in message data")

    # Map MessageType enum values to Message classes
    type_map: dict[str, type[Message]] = {
        MessageType.AGENT.value: AgentMessage,
        MessageType.USER.value: UserMessage,
        MessageType.SYSTEM.value: SystemMessage,
        MessageType.THINKING.value: ThinkingMessage,
        MessageType.TOOL_CALL.value: ToolCallMessage,
        MessageType.TOOL_RESULT.value: ToolResultMessage,
        MessageType.TOOL_STARTED.value: ToolStartedMessage,
        MessageType.TOOL_ERROR.value: ToolErrorMessage,
        MessageType.APPROVAL_REQUEST.value: ApprovalRequestMessage,
        MessageType.APPROVAL_RESPONSE.value: ApprovalResponseMessage,
        MessageType.ERROR.value: ErrorMessage,
        MessageType.USAGE.value: UsageMessage,
    }

    message_class = type_map.get(msg_type)
    if not message_class:
        raise ValueError(f"Unknown message type: {msg_type}")

    # Use Pydantic validation
    return message_class(**data)


@dataclass
class PendingApproval:
    """Pending approval request."""

    tool_id: str
    tool_name: str
    tool_args: dict[str, Any]
    turn_id: str
    requested_at: datetime
