"""Task-related types for typed interfaces."""

from typing import Any, Optional

from pydantic import BaseModel, Field

from common.models.enums import ParameterType


class ParameterValue(BaseModel):
    """Runtime value for a task parameter."""

    value: Any
    parameter_type: ParameterType

    def to_string(self) -> str:
        """Convert to string for instruction substitution."""
        if isinstance(self.value, (list, dict)):
            import json

            return json.dumps(self.value)
        return str(self.value)


class TaskExecutionContext(BaseModel):
    """In-memory context for task execution."""

    task_id: str
    task_name: str
    instructions: str  # Original parameterized instructions
    input_values: dict[str, ParameterValue]  # The typed parameter values

    # Optional metadata from task config
    retry_count: int = Field(default=0)
    timeout_seconds: Optional[int] = None
    allowed_tools: Optional[list[str]] = None
