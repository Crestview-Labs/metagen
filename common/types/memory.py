"""Memory management types for typed interfaces."""

from typing import Any, Optional

from pydantic import BaseModel, Field

from common.models.enums import TurnStatus
from common.types.tools import ToolCall, ToolCallResult


# Turn Management Types
class TurnCreationRequest(BaseModel):
    """Request to create a new conversation turn."""

    user_query: str
    agent_id: str
    session_id: str
    task_id: Optional[str] = None
    source_entity: str = "USER"
    target_entity: Optional[str] = None
    conversation_type: str = "USER_AGENT"
    user_metadata: Optional[dict[str, Any]] = None


class TurnUpdateRequest(BaseModel):
    """Request to update an existing turn."""

    turn_id: str
    agent_response: Optional[str] = None
    status: Optional[TurnStatus] = None
    llm_context: Optional[dict[str, Any]] = None
    total_duration_ms: Optional[int] = None
    llm_duration_ms: Optional[int] = None
    tools_duration_ms: Optional[int] = None
    error_details: Optional[dict[str, Any]] = None
    agent_metadata: Optional[dict[str, Any]] = None


class TurnCompletionRequest(BaseModel):
    """Request to complete a conversation turn."""

    turn_id: str
    agent_response: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolCallResult] = Field(default_factory=list)
    status: TurnStatus = TurnStatus.COMPLETED
    total_duration_ms: Optional[int] = None
    llm_duration_ms: Optional[int] = None
    tools_duration_ms: Optional[int] = None
    error_details: Optional[str] = None


# Tool Usage Types
class ToolUsageRequest(BaseModel):
    """Request to record tool usage."""

    tool_name: str
    tool_args: dict[str, Any]
    turn_id: str
    agent_id: str
    requires_approval: bool = False
    tool_call_id: Optional[str] = None


class ToolApprovalUpdate(BaseModel):
    """Update for tool approval status."""

    tool_usage_id: str
    approved: bool
    user_feedback: Optional[str] = None


class ToolExecutionStart(BaseModel):
    """Mark tool execution as started."""

    tool_usage_id: str


class ToolExecutionComplete(BaseModel):
    """Mark tool execution as complete."""

    tool_usage_id: str
    result: ToolCallResult
    duration_ms: int
