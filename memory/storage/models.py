"""Pydantic models for turn-based conversation storage."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TurnStatus(str, Enum):
    """Status of a conversation turn."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ERROR = "error"
    PARTIAL = "partial"


class ConversationTurn(BaseModel):
    """Model for a complete conversation turn.

    Represents a user query → agent response cycle, including
    all tool usage and performance metrics.
    """

    id: str = Field(..., description="Unique turn ID")
    agent_id: str = Field(..., description="Agent identifier (METAGEN, TASK_EXECUTION_123, etc.)")
    turn_number: int = Field(..., description="Sequential turn number for this agent")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Turn start time")

    # Entity tracking
    source_entity: str = Field(..., description="Who initiated this turn")
    target_entity: str = Field(..., description="Who receives/processes this turn")
    conversation_type: str = Field(
        ..., description="Type of conversation: USER_AGENT, AGENT_AGENT, SYSTEM_MESSAGE"
    )

    # Turn content
    user_query: str = Field(..., description="User's question/request")
    agent_response: str = Field(..., description="Agent's final response")

    # Task context (for task execution agents)
    task_id: Optional[str] = Field(
        None, description="Task ID if this turn is part of task execution"
    )

    # Execution context
    llm_context: Optional[dict[str, Any]] = Field(
        None, description="Full conversation context sent to LLM"
    )
    tools_used: bool = Field(default=False, description="Whether any tools were used in this turn")

    # Observability and performance
    trace_id: Optional[str] = Field(None, description="OpenTelemetry trace ID")
    total_duration_ms: Optional[float] = Field(None, description="Total turn duration")
    llm_duration_ms: Optional[float] = Field(None, description="LLM processing time")
    tools_duration_ms: Optional[float] = Field(None, description="Total tool execution time")

    # Metadata and status
    user_metadata: dict[str, Any] = Field(
        default_factory=dict, description="User-specific metadata"
    )
    agent_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Agent-specific metadata"
    )
    status: TurnStatus = Field(TurnStatus.COMPLETED, description="Turn completion status")
    error_details: Optional[dict[str, Any]] = Field(
        None, description="Error information if status != completed"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Compaction status
    compacted: bool = Field(False, description="Whether this turn has been compacted")

    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class ToolUsageStatus(str, Enum):
    """Status of tool usage."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    CANCELLED = "CANCELLED"


class ToolUsage(BaseModel):
    """Model for tool usage tracking.

    Tracks the complete lifecycle of tool usage:
    proposal → user feedback → execution → result
    """

    id: str = Field(..., description="Unique tool usage ID")
    turn_id: str = Field(..., description="Associated conversation turn ID")
    entity_id: str = Field(..., description="Entity that invoked this tool")

    # Tool details
    tool_name: str = Field(..., description="Name of the tool")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="Tool arguments")

    # User feedback
    requires_approval: bool = Field(False, description="Whether user approval is required")
    user_decision: Optional[str] = Field(None, description="User's decision: APPROVED or REJECTED")
    user_feedback: Optional[str] = Field(None, description="User's feedback on rejection")
    decision_timestamp: Optional[datetime] = Field(None, description="When user made the decision")

    # Execution details
    execution_started_at: Optional[datetime] = Field(None, description="Execution start time")
    execution_completed_at: Optional[datetime] = Field(
        None, description="Execution completion time"
    )
    execution_status: Optional[ToolUsageStatus] = Field(None, description="Current status")
    execution_result: Optional[dict[str, Any]] = Field(None, description="Tool execution result")
    execution_error: Optional[str] = Field(None, description="Error message if failed")

    # Performance metrics
    duration_ms: Optional[float] = Field(None, description="Execution duration in milliseconds")
    tokens_used: Optional[int] = Field(None, description="Tokens consumed")

    # Tracing
    trace_id: Optional[str] = Field(None, description="OpenTelemetry trace ID")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}
