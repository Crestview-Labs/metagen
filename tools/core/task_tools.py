"""Core task management tools for reusable task definitions."""

import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agents.memory import MemoryManager
from common.models import TaskConfig, TaskDefinition
from tools.base import BaseCoreTool

logger = logging.getLogger(__name__)


class CreateTaskInput(BaseModel):
    """Input for creating a reusable task definition."""

    task_definition: TaskDefinition = Field(..., description="Complete task definition")


class CreateTaskOutput(BaseModel):
    """Output from creating a task definition."""

    task_id: str = Field(..., description="Created task ID")
    name: str = Field(..., description="Task name")


class ListTasksInput(BaseModel):
    """Input for listing task definitions."""

    limit: int = Field(50, description="Maximum number of tasks to return")


class ListTasksOutput(BaseModel):
    """Output from listing task definitions."""

    tasks: list[TaskDefinition] = Field(..., description="List of task definitions")
    total_count: int = Field(..., description="Total number of tasks")


class ExecuteTaskInput(BaseModel):
    """Input for executing a task definition."""

    task_id: str = Field(..., description="ID of task definition to execute")
    input_values: dict[str, Any] = Field(..., description="Input parameter values")


class ExecuteTaskOutput(BaseModel):
    """Output from task execution."""

    task_id: str = Field(..., description="Task ID that was executed")
    task_name: str = Field(..., description="Task name")
    agent_id: str = Field(..., description="Agent ID that will execute the task")


class CreateTaskTool(BaseCoreTool):
    """Tool for creating reusable task definitions."""

    def __init__(self, memory_manager: MemoryManager):
        super().__init__(
            name="create_task",
            description="Create a new reusable task definition with parameterized inputs",
            input_schema=CreateTaskInput,
            output_schema=CreateTaskOutput,
        )
        self.memory_manager = memory_manager

    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """Create a new reusable task definition."""
        # Input is already validated as CreateTaskInput by BaseCoreTool
        task_input: CreateTaskInput = input_data  # type: ignore

        # Create task config
        task_id = str(uuid.uuid4())
        task_config = TaskConfig(
            id=task_id,
            name=task_input.task_definition.name,
            definition=task_input.task_definition,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        # Store in database
        await self.memory_manager.create_task(task_config)
        logger.info(f"Created task: {task_config.name} (ID: {task_config.id})")

        return CreateTaskOutput(task_id=task_config.id, name=task_config.name)


class ListTasksTool(BaseCoreTool):
    """Tool for listing available task definitions."""

    def __init__(self, memory_manager: MemoryManager):
        super().__init__(
            name="list_tasks",
            description="List available task definitions with optional filtering",
            input_schema=ListTasksInput,
            output_schema=ListTasksOutput,
        )
        self.memory_manager = memory_manager

    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """List available task definitions."""
        # Input is already validated as ListTasksInput by BaseCoreTool
        list_input: ListTasksInput = input_data  # type: ignore

        task_configs = await self.memory_manager.list_tasks(list_input.limit)

        # Extract task definitions from configs
        task_definitions = [config.definition for config in task_configs]

        return ListTasksOutput(tasks=task_definitions, total_count=len(task_definitions))


class ExecuteTaskTool(BaseCoreTool):
    """Tool for executing a task definition.

    This tool is intercepted by AgentManager and routed to TaskExecutionAgent.
    """

    def __init__(self, memory_manager: MemoryManager):
        super().__init__(
            name="execute_task",
            description="Execute a task definition with specific input values",
            input_schema=ExecuteTaskInput,
            output_schema=ExecuteTaskOutput,
        )
        self.memory_manager = memory_manager

    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """Execute a task definition.

        Note: This method is typically intercepted by AgentManager.
        This implementation is a fallback that validates the task exists.
        """
        # Input is already validated as ExecuteTaskInput by BaseCoreTool
        exec_input: ExecuteTaskInput = input_data  # type: ignore

        # Get task config to validate it exists
        task_config = await self.memory_manager.get_task(exec_input.task_id)
        if not task_config:
            raise ValueError(f"Task definition not found: {exec_input.task_id}")

        # Validate input parameters
        missing_params = []
        for param in task_config.definition.input_schema:
            if param.required and param.name not in exec_input.input_values:
                missing_params.append(param.name)

        if missing_params:
            raise ValueError(f"Missing required parameters: {missing_params}")

        # Return basic execution info
        # The actual execution happens in TaskExecutionAgent via interception
        return ExecuteTaskOutput(
            task_id=task_config.id,
            task_name=task_config.name,
            agent_id="task_execution_agent",  # Default agent ID
        )
