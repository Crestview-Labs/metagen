"""Task-related SQLModel models.

These models serve as both SQLAlchemy ORM models and Pydantic validation models.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column, Index, String, Text
from sqlmodel import Field, Relationship

from .base import TimestampedModel
from .enums import TaskStatus


class Task(TimestampedModel, table=True):
    """Model for task definitions and tracking.

    Tasks are long-running operations delegated to specialized agents.
    """

    __tablename__ = "tasks"

    # Primary identification
    id: str = Field(primary_key=True, description="Unique task ID")

    # Task definition
    name: str = Field(description="Human-readable task name")
    description: str = Field(sa_column=Column(Text), description="Detailed task description")
    instructions: str = Field(
        sa_column=Column(Text), description="Step-by-step instructions for the task"
    )

    # Task metadata
    task_type: str = Field(index=True, description="Type of task (research, code_generation, etc)")
    priority: int = Field(
        default=5, ge=1, le=10, description="Priority from 1 (lowest) to 10 (highest)"
    )
    tags: list[str] = Field(
        default_factory=list, sa_column=Column(JSON), description="Task tags for categorization"
    )

    # Agent assignment
    assigned_agent_id: Optional[str] = Field(
        default=None, index=True, description="ID of agent assigned to this task"
    )
    agent_type: Optional[str] = Field(
        default=None, description="Type of agent needed (task_execution, research, etc)"
    )

    # Task configuration
    config: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON), description="Task-specific configuration"
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Contextual information for the task",
    )

    # Execution tracking
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        sa_column=Column(String, index=True),
        description="Current task status",
    )
    started_at: Optional[datetime] = Field(default=None, description="When task execution started")
    completed_at: Optional[datetime] = Field(default=None, description="When task completed")

    # Results and outputs
    result: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON), description="Task execution result"
    )
    error: Optional[str] = Field(
        default=None, sa_column=Column(Text), description="Error message if failed"
    )
    outputs: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Task outputs (files created, data generated, etc)",
    )

    # Progress tracking
    progress_percentage: int = Field(
        default=0, ge=0, le=100, description="Task completion percentage"
    )
    progress_message: Optional[str] = Field(
        default=None, description="Current progress status message"
    )
    milestones: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON), description="List of completed milestones"
    )

    # Performance metrics
    execution_time_ms: Optional[float] = Field(default=None, description="Total execution time")
    tokens_used: Optional[int] = Field(default=None, description="Total tokens consumed")
    tool_calls_count: Optional[int] = Field(default=None, description="Number of tool calls made")

    # Usage tracking
    usage_count: int = Field(default=0, description="Number of times this task has been executed")

    # Parent task support
    parent_task_id: Optional[str] = Field(
        default=None, foreign_key="tasks.id", index=True, description="Parent task ID for subtasks"
    )

    # Task parameters stored as JSON for now (until we fix the relationship)
    input_parameters: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON), description="Input parameter definitions"
    )
    output_parameters: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON), description="Output parameter definitions"
    )

    # Relationships
    subtasks: list["Task"] = Relationship(
        back_populates="parent_task", sa_relationship_kwargs={"remote_side": "Task.id"}
    )
    parent_task: Optional["Task"] = Relationship(back_populates="subtasks")
    execution_requests: list["TaskExecutionRequest"] = Relationship(back_populates="task")
    parameters: list["TaskParameter"] = Relationship(back_populates="task")

    # Table configuration
    __table_args__ = (
        Index("idx_tasks_status_priority", "status", "priority"),
        Index("idx_tasks_assigned_agent", "assigned_agent_id", "status"),
        Index("idx_tasks_type_status", "task_type", "status"),
    )

    def resolve_instructions(self, input_values: dict[str, Any]) -> str:
        """Resolve instructions by substituting input parameters.

        Replaces {param_name} placeholders in instructions with actual values.
        """
        resolved = self.instructions
        for key, value in input_values.items():
            placeholder = f"{{{key}}}"
            resolved = resolved.replace(placeholder, str(value))
        return resolved

    def validate_input_parameters(self, input_values: dict[str, Any]) -> list[str]:
        """Validate that all required parameters are provided.

        Returns list of missing required parameter names.
        """
        missing = []
        # Since input_parameters is now a list of dicts (JSON)
        for param in self.input_parameters:
            if param.get("required", False) and param["name"] not in input_values:
                missing.append(param["name"])
        return missing


class TaskExecutionRequest(TimestampedModel, table=True):
    """Model for task execution requests.

    Tracks requests to execute tasks, including retries.
    """

    __tablename__ = "task_execution_requests"

    # Primary identification
    id: str = Field(primary_key=True, description="Unique request ID")
    task_id: str = Field(foreign_key="tasks.id", index=True, description="Task being executed")

    # Request metadata
    requested_by: str = Field(description="Who requested the execution (user ID or system)")
    request_type: str = Field(
        default="manual", description="Type of request (manual, scheduled, retry, etc)"
    )
    retry_count: int = Field(default=0, description="Number of retry attempts")

    # Execution details
    started_at: Optional[datetime] = Field(default=None, description="Execution start time")
    completed_at: Optional[datetime] = Field(default=None, description="Execution completion time")
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        sa_column=Column(String, index=True),
        description="Execution status",
    )

    # Results
    result: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON), description="Execution result"
    )
    error: Optional[str] = Field(
        default=None, sa_column=Column(Text), description="Error details if failed"
    )

    # Execution context
    execution_context: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON),
        description="Context specific to this execution",
    )

    # Relationships
    task: Optional[Task] = Relationship(back_populates="execution_requests")

    # Table configuration
    __table_args__ = (
        Index("idx_execution_requests_task_status", "task_id", "status"),
        Index("idx_execution_requests_created", "created_at"),
    )

    @classmethod
    def create_for_task(cls, task_id: str, input_values: dict[str, Any]) -> "TaskExecutionRequest":
        """Create execution request with deterministic agent_id."""
        from uuid import uuid4

        return cls(
            id=str(uuid4()),
            task_id=task_id,
            requested_by=f"TASK_EXECUTION_{task_id}",
            execution_context={"input_values": input_values},
        )


class TaskParameter(TimestampedModel, table=True):
    """Model for task parameters.

    Defines expected parameters for task execution.
    """

    __tablename__ = "task_parameters"

    # Primary identification
    id: str = Field(primary_key=True, description="Unique parameter ID")
    task_id: str = Field(foreign_key="tasks.id", index=True, description="Associated task")

    # Parameter definition
    name: str = Field(description="Parameter name")
    description: Optional[str] = Field(default=None, description="Parameter description")
    parameter_type: str = Field(description="Data type (string, number, boolean, etc)")

    # Validation
    required: bool = Field(default=False, description="Whether parameter is required")
    default_value: Optional[Any] = Field(
        default=None, sa_column=Column(JSON), description="Default value if not provided"
    )
    validation_rules: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON), description="Validation rules (min/max, regex, etc)"
    )

    # Options for enumerated types
    allowed_values: Optional[list[Any]] = Field(
        default=None, sa_column=Column(JSON), description="List of allowed values for enum types"
    )

    # Display metadata
    display_order: int = Field(default=0, description="Order for UI display")
    ui_hints: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON), description="UI rendering hints"
    )

    # Relationships
    task: Optional[Task] = Relationship(back_populates="parameters")

    # Table configuration
    __table_args__ = (Index("idx_task_parameters_task_order", "task_id", "display_order"),)
