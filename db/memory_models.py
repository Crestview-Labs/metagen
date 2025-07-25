"""SQLAlchemy database models for memory storage."""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from .base import Base


class ConversationTurnModel(Base):
    """SQLAlchemy model for conversation turns.

    Each turn represents a complete user query → agent response cycle,
    including any tools used and performance metrics.
    """

    __tablename__ = "conversation_turns"

    # Primary identification
    id = Column(String, primary_key=True)  # UUID for the turn
    agent_id = Column(
        String, nullable=False, default="METAGEN"
    )  # Agent identifier (METAGEN, TASK_EXECUTION_123, etc.)
    turn_number = Column(Integer, nullable=False)  # Sequential turn for this agent
    timestamp = Column(DateTime, nullable=False, default=func.now())  # Turn start time

    # Entity tracking for flexible conversations
    source_entity = Column(String, nullable=False)  # Who initiated this turn (USER, METAGEN, etc.)
    target_entity = Column(String, nullable=False)  # Who receives/processes this turn
    conversation_type = Column(String, nullable=False)  # USER_AGENT, AGENT_AGENT, SYSTEM_MESSAGE

    # Turn content
    user_query = Column(Text, nullable=False)  # User's question/request
    agent_response = Column(Text, nullable=False)  # Agent's final response

    # Task context (for task execution agents)
    task_id = Column(String, nullable=True)  # Task ID if this turn is part of task execution

    # Execution context
    llm_context = Column(JSON, nullable=True)  # Full conversation context sent to LLM
    tools_used = Column(Boolean, nullable=False, default=False)  # Whether any tools were used

    # Observability and performance
    trace_id = Column(String(32), nullable=True)  # OpenTelemetry trace ID
    total_duration_ms = Column(Float, nullable=True)  # Total turn duration
    llm_duration_ms = Column(Float, nullable=True)  # LLM processing time
    tools_duration_ms = Column(Float, nullable=True)  # Total tool execution time

    # Metadata and status
    user_metadata = Column(JSON, nullable=True, default={})  # User-specific metadata
    agent_metadata = Column(JSON, nullable=True, default={})  # Agent-specific metadata
    status = Column(
        String, nullable=False, default="completed"
    )  # in_progress | completed | error | partial
    error_details = Column(JSON, nullable=True)  # Error information if status != completed

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    # Compaction tracking
    compacted = Column(Boolean, nullable=False, default=False)

    # Indexes for optimal query performance
    __table_args__ = (
        Index("idx_turns_agent_number", "agent_id", "turn_number"),
        Index("idx_turns_agent_id", "agent_id"),
        Index("idx_turns_timestamp", "timestamp"),
        Index("idx_turns_trace_id", "trace_id"),
        Index("idx_turns_agent_time", "agent_id", "timestamp"),
        Index("idx_turns_compacted", "compacted"),
        Index("idx_turns_task_id", "task_id"),  # Index for querying by task
        Index("idx_turns_source_entity", "source_entity"),
        Index("idx_turns_target_entity", "target_entity"),
        Index("idx_turns_conversation_type", "conversation_type"),
        # Unique constraint on agent + turn number
        Index("idx_turns_agent_turn_unique", "agent_id", "turn_number", unique=True),
    )


class CompactMemoryModel(Base):
    """SQLAlchemy model for compact memories.

    Represents compressed conversation chunks with semantic labels
    and tool usage analysis.
    """

    __tablename__ = "compact_memories"

    # Primary identification
    id = Column(String, primary_key=True)  # UUID for the compact memory
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())

    # Time range covered
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)

    # Task coverage
    task_ids = Column(
        JSON, nullable=True
    )  # Array of task IDs covered (null for general conversations)

    # Compressed content
    summary = Column(Text, nullable=False)  # Main summary
    key_points = Column(JSON, nullable=True)  # Array of key points
    entities = Column(JSON, nullable=True)  # Extracted entities by type
    semantic_labels = Column(JSON, nullable=True)  # Array of semantic tags

    # Metrics
    turn_count = Column(Integer, nullable=True)  # Number of turns compacted
    token_count = Column(Integer, nullable=True)  # Original token count
    compressed_token_count = Column(Integer, nullable=True)  # Compressed tokens

    # Processing status
    processed = Column(Boolean, nullable=False, default=False)

    # Indexes for efficient queries
    __table_args__ = (
        Index("idx_compact_memories_created_at", "created_at"),
        Index("idx_compact_memories_time_range", "start_time", "end_time"),
        Index("idx_compact_memories_processed", "processed"),
    )


class LongTermMemoryModel(Base):
    """SQLAlchemy model for long-term memories keyed by agent."""

    __tablename__ = "long_term_memories"

    # Primary identification
    id = Column(String, primary_key=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    # Task context
    task_id = Column(String, nullable=True)  # Task ID if this memory relates to a specific task

    # Content
    content = Column(Text, nullable=False)

    # Indexes
    __table_args__ = (
        Index("idx_long_term_memories_created_at", "created_at"),
        Index("idx_long_term_memories_task_id", "task_id"),
    )


class TaskModel(Base):
    """SQLAlchemy model for simplified task definitions."""

    __tablename__ = "tasks"

    # Primary fields - simplified schema
    id = Column(String(255), primary_key=True)
    name = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    instructions = Column(Text, nullable=False)

    # Parameters as JSON
    input_parameters = Column(JSON, nullable=False, default=list)
    output_parameters = Column(JSON, nullable=False, default=list)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    usage_count = Column(Integer, nullable=False, default=0)

    # Indexes for common queries
    __table_args__ = (
        Index("idx_tasks_name", "name"),
        Index("idx_tasks_created", "created_at"),
        Index("idx_tasks_usage", "usage_count"),
    )


class ToolUsageModel(Base):
    """SQLAlchemy model for tool usage tracking.

    Tracks the complete lifecycle of tool usage:
    proposal → user feedback → execution → result
    """

    __tablename__ = "tool_usage"

    # Primary identification
    id = Column(String, primary_key=True)  # UUID
    turn_id = Column(
        String, ForeignKey("conversation_turns.id"), nullable=False
    )  # FK to conversation_turns.id
    entity_id = Column(String, nullable=False)  # Which entity invoked this tool

    # Tool details
    tool_name = Column(String, nullable=False)  # e.g., 'gmail_search', 'execute_task'
    tool_args = Column(JSON, nullable=False)  # Arguments for the tool

    # User feedback (if applicable)
    requires_approval = Column(Boolean, nullable=False, default=False)
    user_decision = Column(String, nullable=True)  # NULL, 'APPROVED', 'REJECTED'
    user_feedback = Column(Text, nullable=True)  # User's reason for rejection
    decision_timestamp = Column(DateTime, nullable=True)

    # Execution details
    execution_started_at = Column(DateTime, nullable=True)
    execution_completed_at = Column(DateTime, nullable=True)
    execution_status = Column(
        String, nullable=True
    )  # 'PENDING', 'APPROVED', 'EXECUTING', 'SUCCESS', 'FAILURE', 'CANCELLED'
    execution_result = Column(JSON, nullable=True)  # Tool output
    execution_error = Column(Text, nullable=True)  # Error message if failed

    # Performance metrics
    duration_ms = Column(Float, nullable=True)
    tokens_used = Column(Integer, nullable=True)

    # Tracing
    trace_id = Column(String(32), nullable=True)  # OpenTelemetry trace

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=func.now())
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    # Relationships
    conversation_turn = relationship(
        "ConversationTurnModel",
        backref="tool_usages",
        foreign_keys=[turn_id],
        primaryjoin="ToolUsageModel.turn_id==ConversationTurnModel.id",
    )

    # Indexes
    __table_args__ = (
        Index("idx_tool_usage_turn", "turn_id"),
        Index("idx_tool_usage_entity", "entity_id"),
        Index("idx_tool_usage_name", "tool_name"),
        Index("idx_tool_usage_status", "execution_status"),
        Index("idx_tool_usage_decision", "user_decision"),
        Index("idx_tool_usage_created", "created_at"),
    )
