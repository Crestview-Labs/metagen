"""Tool-related types used throughout the system."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ToolErrorType(str, Enum):
    """Types of errors that can occur during tool execution."""

    EXECUTION_ERROR = "execution_error"
    TIMEOUT = "timeout"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    USER_REJECTED = "user_rejected"
    INVALID_ARGS = "invalid_args"


TOOL_ERROR_MESSAGES = {
    ToolErrorType.EXECUTION_ERROR: "Tool execution failed: {error}",
    ToolErrorType.TIMEOUT: "Tool execution timed out after {timeout}s",
    ToolErrorType.VALIDATION_ERROR: "Invalid arguments for tool '{tool_name}': {validation_error}",
    ToolErrorType.NOT_FOUND: (
        "Tool '{tool_name}' not found. "
        "Available tools: {available_tools}. "
        "Cannot execute tool '{tool_name}'."
    ),
    ToolErrorType.USER_REJECTED: (
        "User rejected tool execution: '{tool_name}'. User feedback: {feedback}"
    ),
    ToolErrorType.INVALID_ARGS: "Invalid arguments for tool '{tool_name}': {validation_error}",
    ToolErrorType.PERMISSION_DENIED: "Permission denied for tool '{tool_name}': {reason}",
}


class ToolCall(BaseModel):
    """Represents a tool call request from the LLM.

    This standardized structure represents what the LLM wants to execute:
    - LLM providers generate tool calls in their format
    - We normalize them to this structure
    - Agent processes these and gets ToolCallResult objects back
    """

    # Identification
    id: str = Field(..., description="Unique identifier for this tool call")
    name: str = Field(..., description="Name of the tool to execute")

    # Arguments - JSON-compatible dict
    arguments: dict[str, Any] = Field(
        ..., description="Arguments to pass to the tool as a JSON-compatible dictionary"
    )


class ToolCallResult(BaseModel):
    """Standardized result from tool call execution.

    This unified structure is used throughout the system:
    - Tool executors return this format
    - Agent passes it to LLMClient without conversion
    - LLM-specific clients format it as needed for their APIs
    """

    # Identification fields
    tool_name: str = Field(..., description="Name of the tool that was executed")
    tool_call_id: Optional[str] = Field(
        None, description="ID from the original tool call for correlation"
    )

    # Result content
    content: str = Field(..., description="The actual result content")

    # Status
    is_error: bool = Field(False, description="Whether this result represents an error")

    # Error details (only populated if is_error=True)
    error: Optional[str] = Field(None, description="Error message if execution failed")
    error_type: Optional[ToolErrorType] = Field(
        None, description="Type of error if execution failed"
    )

    # Optional fields
    user_display: Optional[str] = Field(None, description="Human-readable display of the result")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata about the execution"
    )


class ToolExecution(BaseModel):
    """Record of a tool execution."""

    tool_call: ToolCall
    result: ToolCallResult
