"""Task-related SQLModel models.

These models serve as both SQLAlchemy ORM models and Pydantic validation models.
"""

from typing import Any, Optional

from pydantic import BaseModel
from pydantic import Field as PydanticField
from sqlalchemy import Column
from sqlmodel import Field

from .base import TimestampedModel
from .enums import ParameterType
from .types import PydanticJSON


class Parameter(BaseModel):
    """Schema definition for a task parameter."""

    name: str
    description: str
    type: ParameterType
    required: bool = False
    default: Optional[Any] = None


class TaskDefinition(BaseModel):
    """Task definition for API/tool interfaces."""

    name: str
    description: str
    instructions: str  # Parameterized instructions with {param} placeholders
    input_schema: list[Parameter] = PydanticField(default_factory=list)
    output_schema: list[Parameter] = PydanticField(default_factory=list)
    task_type: str = PydanticField(default="general")


class TaskConfig(TimestampedModel, table=True):
    """Model for task configuration storage.

    Stores reusable task definitions with parameterized instructions.
    Runtime execution data is tracked via ConversationTurn.
    """

    __tablename__ = "task_configs"

    # Primary identification
    id: str = Field(primary_key=True, description="Unique task config ID")
    name: str = Field(index=True, description="Human-readable task name")

    # Task definition stored as JSON with automatic serialization
    definition: TaskDefinition = Field(
        sa_column=Column(PydanticJSON(TaskDefinition)),
        description="Complete task definition including instructions and schemas",
    )
