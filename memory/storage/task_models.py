"""Task management models for Metagen system."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"  # Task created but not started
    IN_PROGRESS = "in_progress"  # Task currently being executed
    COMPLETED = "completed"  # Task finished successfully
    FAILED = "failed"  # Task failed with error
    CANCELLED = "cancelled"  # Task cancelled by user
    PAUSED = "paused"  # Task paused for user input


class TaskExecutionRequest(BaseModel):
    """Request to execute a task with specific input values."""

    id: str = Field(..., description="Unique execution request identifier")
    task_id: str = Field(..., description="ID of the Task definition to execute")
    input_values: dict[str, Any] = Field(default_factory=dict, description="Input parameter values")
    agent_id: str = Field(..., description="Deterministic agent ID for execution tracking")

    # Metadata
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Request creation time"
    )

    @classmethod
    def create_for_task(cls, task_id: str, input_values: dict[str, Any]) -> "TaskExecutionRequest":
        """Create execution request with deterministic agent_id."""
        from uuid import uuid4

        return cls(
            id=str(uuid4()),
            task_id=task_id,
            input_values=input_values,
            agent_id=f"TASK_EXECUTION_{task_id}",
        )

    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class TaskExecution(BaseModel):
    """Track individual task execution attempts."""

    id: str = Field(..., description="Unique execution ID")
    task_id: str = Field(..., description="Task being executed")
    agent_id: str = Field(..., description="Agent executing the task")

    # Execution tracking
    started_at: datetime = Field(
        default_factory=datetime.utcnow, description="Execution start time"
    )
    completed_at: Optional[datetime] = Field(None, description="Execution completion time")
    status: TaskStatus = Field(default=TaskStatus.IN_PROGRESS, description="Execution status")

    # Execution context
    context_snapshot: dict[str, Any] = Field(
        default_factory=dict, description="Context at execution start"
    )
    steps_completed: list[str] = Field(
        default_factory=list, description="Completed execution steps"
    )
    current_step: Optional[str] = Field(None, description="Current execution step")

    # Results
    result: Optional[dict[str, Any]] = Field(None, description="Execution result")
    error_details: Optional[dict[str, Any]] = Field(None, description="Error details if failed")
    logs: list[dict[str, Any]] = Field(default_factory=list, description="Execution logs")

    # Performance metrics
    total_duration_ms: Optional[int] = Field(
        None, description="Total execution time in milliseconds"
    )
    llm_calls_count: int = Field(0, description="Number of LLM calls made")
    tool_calls_count: int = Field(0, description="Number of tool calls made")

    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class TaskParameter(BaseModel):
    """Input/output parameter definition for tasks."""

    name: str = Field(..., description="Parameter name")
    type: str = Field(
        ..., description="Parameter type (string, number, date, list, email_address, etc.)"
    )
    description: str = Field(..., description="Parameter description")
    required: bool = Field(True, description="Whether parameter is required")
    default_value: Optional[Any] = Field(None, description="Default value if not required")
    example_value: Optional[str] = Field(None, description="Example value for user guidance")

    class Config:
        use_enum_values = True


class Task(BaseModel):
    """Reusable task definition with parameterized inputs/outputs."""

    id: str = Field(..., description="Unique task ID")
    name: str = Field(..., description="Task name")
    description: str = Field(..., description="Task description")
    instructions: str = Field(..., description="Parameterized instructions for task execution")

    # Input/Output specification
    input_parameters: list[TaskParameter] = Field(
        default_factory=list, description="Input parameters for task"
    )
    output_parameters: list[TaskParameter] = Field(
        default_factory=list, description="Expected output parameters"
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Task creation time")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="Last update time")
    usage_count: int = Field(0, description="Number of times task has been used")

    def resolve_instructions(self, input_values: dict[str, Any]) -> str:
        """Resolve instructions with input parameter values."""
        try:
            return self.instructions.format(**input_values)
        except KeyError as e:
            return f"Error resolving instructions: Missing parameter {e}"

    def validate_input_parameters(self, input_values: dict[str, Any]) -> list[str]:
        """Check if all required input parameters have values."""
        missing = []
        for param in self.input_parameters:
            if param.required and param.name not in input_values:
                missing.append(param.name)
        return missing

    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}


# Task-related DTOs for API/Service layer
class CreateTaskRequest(BaseModel):
    """Request to create a new task."""

    title: str = Field(..., description="Task title")
    description: str = Field(..., description="Task description")
    parent_task_id: Optional[str] = Field(None, description="Parent task ID if subtask")


class UpdateTaskRequest(BaseModel):
    """Request to update an existing task."""

    title: Optional[str] = Field(None, description="Updated task title")
    description: Optional[str] = Field(None, description="Updated task description")
    status: Optional[TaskStatus] = Field(None, description="Updated task status")
    user_feedback: Optional[str] = Field(None, description="User feedback")
    user_rating: Optional[int] = Field(None, description="User rating (1-5)")
