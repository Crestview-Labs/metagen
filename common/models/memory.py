"""Memory-related SQLModel models.

These models serve as both SQLAlchemy ORM models and Pydantic validation models.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column, Index, String
from sqlmodel import Field, Relationship

from .base import TimestampedModel
from .enums import ToolUsageStatus, TurnStatus


class ConversationTurn(TimestampedModel, table=True):
    """Model for a complete conversation turn.

    Represents a user query → agent response cycle, including
    all tool usage and performance metrics.
    """

    __tablename__ = "conversation_turns"

    # Primary identification
    id: str = Field(primary_key=True, description="Unique turn ID")
    agent_id: str = Field(
        index=True,
        default="METAGEN",
        description="Agent identifier (METAGEN, TASK_EXECUTION_123, etc.)",
    )
    session_id: str = Field(index=True, description="Session identifier for multi-client routing")
    turn_number: int = Field(description="Sequential turn number for this agent")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, index=True, description="Turn start time"
    )

    # Entity tracking for flexible conversations
    source_entity: str = Field(description="Who initiated this turn (USER, METAGEN, etc.)")
    target_entity: str = Field(description="Who receives/processes this turn")
    conversation_type: str = Field(description="Type: USER_AGENT, AGENT_AGENT, SYSTEM_MESSAGE")

    # Turn content
    user_query: str = Field(description="User's question/request")
    agent_response: str = Field(description="Agent's final response")

    # Task context (for task execution agents)
    task_id: Optional[str] = Field(
        default=None, index=True, description="Task ID if part of task execution"
    )

    # Execution context
    llm_context: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON), description="Full conversation context sent to LLM"
    )
    tools_used: bool = Field(default=False, description="Whether any tools were used")

    # Observability and performance
    total_duration_ms: Optional[float] = Field(default=None, description="Total turn duration")
    llm_duration_ms: Optional[float] = Field(default=None, description="LLM processing time")
    tools_duration_ms: Optional[float] = Field(
        default=None, description="Total tool execution time"
    )

    # Metadata and status
    user_metadata: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON), description="User-specific metadata"
    )
    agent_metadata: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON), description="Agent-specific metadata"
    )
    status: TurnStatus = Field(default=TurnStatus.COMPLETED, description="Turn completion status")
    error_details: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON), description="Error information if status != completed"
    )

    # Compaction tracking
    compacted: bool = Field(default=False, description="Whether this turn has been compacted")

    # Relationships
    tool_usages: list["ToolUsage"] = Relationship(back_populates="conversation_turn")

    # Table configuration
    __table_args__ = (
        Index("idx_turns_agent_number", "agent_id", "turn_number"),
        Index("idx_turns_agent_time", "agent_id", "timestamp"),
        Index("idx_turns_agent_turn_unique", "agent_id", "turn_number", unique=True),
        Index("idx_turns_compacted", "compacted"),
        Index("idx_turns_source_entity", "source_entity"),
        Index("idx_turns_target_entity", "target_entity"),
        Index("idx_turns_conversation_type", "conversation_type"),
    )


class ToolUsage(TimestampedModel, table=True):
    """Model for tool usage tracking.

    Tracks the complete lifecycle of tool usage:
    proposal → user feedback → execution → result
    """

    __tablename__ = "tool_usage"

    # Primary identification
    id: str = Field(primary_key=True, description="Unique tool usage ID")
    turn_id: str = Field(
        foreign_key="conversation_turns.id",
        index=True,
        description="Associated conversation turn ID",
    )
    agent_id: str = Field(index=True, description="Agent that invoked this tool")

    # Tool details
    tool_name: str = Field(index=True, description="Name of the tool")
    tool_args: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON), description="Tool arguments"
    )
    tool_call_id: Optional[str] = Field(
        default=None, description="LLM's tool call ID for correlation"
    )

    # User feedback (if applicable)
    requires_approval: bool = Field(default=False, description="Whether user approval is required")
    user_decision: Optional[str] = Field(
        default=None, index=True, description="User's decision: APPROVED or REJECTED"
    )
    user_feedback: Optional[str] = Field(default=None, description="User's reason for rejection")
    decision_timestamp: Optional[datetime] = Field(
        default=None, description="When user made the decision"
    )

    # Execution details
    execution_started_at: Optional[datetime] = Field(
        default=None, description="Execution start time"
    )
    execution_completed_at: Optional[datetime] = Field(
        default=None, description="Execution completion time"
    )
    execution_status: Optional[ToolUsageStatus] = Field(
        default=None, sa_column=Column(String, index=True), description="Current status"
    )
    execution_result: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON), description="Tool execution result"
    )
    execution_error: Optional[str] = Field(default=None, description="Error message if failed")

    # Performance metrics
    duration_ms: Optional[float] = Field(
        default=None, description="Execution duration in milliseconds"
    )
    tokens_used: Optional[int] = Field(default=None, description="Tokens consumed")

    # Relationships
    conversation_turn: Optional[ConversationTurn] = Relationship(back_populates="tool_usages")

    # Table configuration
    __table_args__ = (Index("idx_tool_usage_created", "created_at"),)


class CompactMemory(TimestampedModel, table=True):
    """Model for compact memories.

    Represents compressed conversation chunks with semantic labels
    and tool usage analysis.
    """

    __tablename__ = "compact_memories"

    # Primary identification
    id: str = Field(primary_key=True, description="Unique memory ID")

    # Time range covered
    start_time: datetime = Field(index=True, description="Start of time range")
    end_time: datetime = Field(index=True, description="End of time range")

    # Task coverage
    task_ids: Optional[list[str]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Task IDs covered (null for general conversations)",
    )

    # Compressed content
    summary: str = Field(description="Main summary of the conversation segment")
    key_points: Optional[list[str]] = Field(
        default=None, sa_column=Column(JSON), description="Key points extracted"
    )
    entities: Optional[dict[str, list[str]]] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Named entities by type (people, places, etc)",
    )
    semantic_labels: Optional[list[str]] = Field(
        default=None, sa_column=Column(JSON), description="Semantic labels/topics for this memory"
    )

    # Metrics
    turn_count: Optional[int] = Field(default=None, description="Number of turns compacted")
    token_count: Optional[int] = Field(
        default=None, description="Original token count before compression"
    )
    compressed_token_count: Optional[int] = Field(
        default=None, description="Token count after compression"
    )

    # Processing status
    processed: bool = Field(
        default=False, index=True, description="Whether semantic processing is complete"
    )

    # Table configuration
    __table_args__ = (Index("idx_compact_memories_time_range", "start_time", "end_time"),)


class LongTermMemory(TimestampedModel, table=True):
    """Model for long-term memories keyed by agent."""

    __tablename__ = "long_term_memories"

    # Primary identification
    id: str = Field(primary_key=True, description="Unique memory ID")

    # Task context
    task_id: Optional[str] = Field(
        default=None, index=True, description="Task ID if memory relates to a specific task"
    )

    # Content
    content: str = Field(description="The memory content")

    # Table configuration
    __table_args__ = (Index("idx_long_term_memories_created_at", "created_at"),)
