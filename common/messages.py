"""Unified message system for agent communication."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field

# Default agent IDs
DEFAULT_AGENT_ID = "METAGEN"  # Default agent ID for MetaAgent


class Direction(str, Enum):
    """Message direction."""

    USER_TO_AGENT = "user_to_agent"
    AGENT_TO_USER = "agent_to_user"


class MessageType(str, Enum):
    """Types of messages in the system."""

    # Chat/content
    CHAT = "chat"
    THINKING = "thinking"

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
    direction: Direction
    timestamp: datetime = Field(default_factory=datetime.now)
    agent_id: str = DEFAULT_AGENT_ID  # TODO: This should be set properly by each agent
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
    """Chat content in either direction."""

    type: MessageType = MessageType.CHAT
    content: str


class UserMessage(ChatMessage):
    """User chat message."""

    direction: Direction = Direction.USER_TO_AGENT


class AgentMessage(ChatMessage):
    """Agent chat message."""

    direction: Direction = Direction.AGENT_TO_USER
    final: bool = False  # Indicates if this is the final message in a response


class SystemMessage(ChatMessage):
    """System message for agent context."""

    direction: Direction = Direction.AGENT_TO_USER


class ThinkingMessage(Message):
    """Agent thinking indicator."""

    type: MessageType = MessageType.THINKING
    direction: Direction = Direction.AGENT_TO_USER
    content: str


# Tool flow messages
class ToolCallMessage(Message):
    """LLM wants to call tools - contains all tool call details."""

    type: MessageType = MessageType.TOOL_CALL
    direction: Direction = Direction.AGENT_TO_USER
    tool_calls: list[ToolCallRequest]  # Properly typed tool calls


class ApprovalRequestMessage(Message):
    """Agent requests approval for a specific tool."""

    type: MessageType = MessageType.APPROVAL_REQUEST
    direction: Direction = Direction.AGENT_TO_USER
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
    direction: Direction = Direction.USER_TO_AGENT
    tool_id: str
    decision: ApprovalDecision
    feedback: Optional[str] = None


class ToolStartedMessage(Message):
    """Agent notifies tool execution started."""

    type: MessageType = MessageType.TOOL_STARTED
    direction: Direction = Direction.AGENT_TO_USER
    tool_id: str
    tool_name: str


class ToolResultMessage(Message):
    """Agent sends tool execution result."""

    type: MessageType = MessageType.TOOL_RESULT
    direction: Direction = Direction.AGENT_TO_USER
    tool_id: str
    tool_name: str
    result: Any


class ToolErrorMessage(Message):
    """Agent sends tool execution error."""

    type: MessageType = MessageType.TOOL_ERROR
    direction: Direction = Direction.AGENT_TO_USER
    tool_id: str
    tool_name: str
    error: str


# Metadata messages
class UsageMessage(Message):
    """Token usage information."""

    type: MessageType = MessageType.USAGE
    direction: Direction = Direction.AGENT_TO_USER
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ErrorMessage(Message):
    """Error message from agent."""

    type: MessageType = MessageType.ERROR
    direction: Direction = Direction.AGENT_TO_USER
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


# Helper functions for message creation
def create_user_message(content: str, agent_id: str = DEFAULT_AGENT_ID) -> UserMessage:
    """Create a user chat message."""
    return UserMessage(content=content, agent_id=agent_id)


def create_agent_message(content: str, agent_id: str = DEFAULT_AGENT_ID) -> AgentMessage:
    """Create an agent chat message."""
    return AgentMessage(content=content, agent_id=agent_id)


def create_thinking_message(message: str, agent_id: str = DEFAULT_AGENT_ID) -> ThinkingMessage:
    """Create a thinking indicator message."""
    return ThinkingMessage(content=message, agent_id=agent_id)


def create_tool_call_message(
    tool_calls: list[ToolCallRequest], agent_id: str = DEFAULT_AGENT_ID
) -> ToolCallMessage:
    """Create a tool call message."""
    return ToolCallMessage(tool_calls=tool_calls, agent_id=agent_id)


def create_approval_request(
    agent_id: str, tool_id: str, tool_name: str, tool_args: dict[str, Any]
) -> ApprovalRequestMessage:
    """Create an approval request message."""
    return ApprovalRequestMessage(
        agent_id=agent_id, tool_id=tool_id, tool_name=tool_name, tool_args=tool_args
    )


def create_approval_response(
    agent_id: str, tool_id: str, decision: ApprovalDecision, feedback: Optional[str] = None
) -> ApprovalResponseMessage:
    """Create an approval response message."""
    return ApprovalResponseMessage(
        agent_id=agent_id, tool_id=tool_id, decision=decision, feedback=feedback
    )


def create_tool_started(tool_id: str, tool_name: str) -> ToolStartedMessage:
    """Create a tool started notification."""
    return ToolStartedMessage(tool_id=tool_id, tool_name=tool_name)


def create_tool_result(tool_id: str, tool_name: str, result: Any) -> ToolResultMessage:
    """Create a tool result message."""
    return ToolResultMessage(tool_id=tool_id, tool_name=tool_name, result=result)


def create_tool_error(tool_id: str, tool_name: str, error: str) -> ToolErrorMessage:
    """Create a tool error message."""
    return ToolErrorMessage(tool_id=tool_id, tool_name=tool_name, error=error)


def create_usage_message(input_tokens: int, output_tokens: int, total_tokens: int) -> UsageMessage:
    """Create a usage statistics message."""
    return UsageMessage(
        input_tokens=input_tokens, output_tokens=output_tokens, total_tokens=total_tokens
    )


def create_error_message(error: str, details: Optional[dict[str, Any]] = None) -> ErrorMessage:
    """Create an error message."""
    return ErrorMessage(error=error, details=details)


@dataclass
class PendingApproval:
    """Pending approval request."""

    tool_id: str
    tool_name: str
    tool_args: dict[str, Any]
    turn_id: str
    requested_at: datetime
