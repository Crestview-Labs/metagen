"""Common shared modules across the Metagen system."""

from .messages import (
    # Constants
    DEFAULT_AGENT_ID,
    AgentMessage,
    AnyMessage,
    ApprovalRequestMessage,
    ApprovalResponseMessage,
    # Chat messages
    ChatMessage,
    # Base classes
    Direction,
    ErrorMessage,
    Message,
    MessageType,
    PendingApproval,
    ThinkingMessage,
    # Tool flow messages
    ToolCallMessage,
    ToolCallRequest,
    ToolErrorMessage,
    ToolResultMessage,
    ToolStartedMessage,
    # Metadata messages
    UsageMessage,
    UserMessage,
    create_agent_message,
    create_approval_request,
    create_approval_response,
    create_error_message,
    create_thinking_message,
    create_tool_call_message,
    create_tool_error,
    create_tool_result,
    create_tool_started,
    create_usage_message,
    # Helper functions
    create_user_message,
)
from .types import (
    # Data classes
    ToolCall,
    ToolCallResult,
    ToolExecution,
)

__all__ = [
    # Constants
    "DEFAULT_AGENT_ID",
    # Base classes
    "Direction",
    "MessageType",
    "Message",
    "AnyMessage",
    # Chat messages
    "ChatMessage",
    "UserMessage",
    "AgentMessage",
    "ThinkingMessage",
    # Tool flow messages
    "ToolCallMessage",
    "ToolCallRequest",
    "ApprovalRequestMessage",
    "ApprovalResponseMessage",
    "ToolStartedMessage",
    "ToolResultMessage",
    "ToolErrorMessage",
    # Metadata messages
    "UsageMessage",
    "ErrorMessage",
    # Data classes
    "ToolCall",
    "ToolCallResult",
    "ToolExecution",
    "PendingApproval",
    # Helper functions
    "create_user_message",
    "create_agent_message",
    "create_thinking_message",
    "create_tool_call_message",
    "create_approval_request",
    "create_approval_response",
    "create_tool_started",
    "create_tool_result",
    "create_tool_error",
    "create_usage_message",
    "create_error_message",
]
