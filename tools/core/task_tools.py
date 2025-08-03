"""Core task management tools for reusable task definitions."""

import logging
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from agents.memory import MemoryManager
from common.models import Task, TaskExecutionRequest, TaskParameter
from tools.base import BaseCoreTool

logger = logging.getLogger(__name__)


class CreateTaskInput(BaseModel):
    """Input for creating a reusable task definition."""

    name: str = Field(..., description="Task name")
    description: str = Field(..., description="Task description")
    instructions: str = Field(..., description="Parameterized instructions for task execution")
    input_parameters: list[dict[str, Any]] = Field(
        default_factory=list, description="Input parameter definitions"
    )
    output_parameters: list[dict[str, Any]] = Field(
        default_factory=list, description="Output parameter definitions"
    )


class CreateTaskOutput(BaseModel):
    """Output from creating a task definition."""

    task_id: str = Field(..., description="Created task ID")
    name: str = Field(..., description="Task name")
    created_at: str = Field(..., description="Creation timestamp")


class ListTasksInput(BaseModel):
    """Input for listing task definitions."""

    limit: int = Field(50, description="Maximum number of tasks to return")


class ListTasksOutput(BaseModel):
    """Output from listing task definitions."""

    tasks: list[dict[str, Any]] = Field(..., description="List of task definitions")
    total_count: int = Field(..., description="Total number of tasks")


class ExecuteTaskInput(BaseModel):
    """Input for executing a task definition."""

    task_id: str = Field(..., description="ID of task definition to execute")
    input_values: dict[str, Any] = Field(..., description="Input parameter values")


class ExecuteTaskOutput(BaseModel):
    """Output from creating a task execution request."""

    execution_request_id: str = Field(..., description="Execution request ID")
    agent_id: str = Field(..., description="Agent ID that will execute the task")
    task_name: str = Field(..., description="Task name")
    resolved_instructions: str = Field(..., description="Instructions with parameters resolved")


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
        # Cast to specific input type
        task_input = CreateTaskInput.model_validate(input_data.model_dump())

        # Convert input parameters to TaskParameter objects
        input_params = []
        for param_data in task_input.input_parameters:
            input_params.append(TaskParameter(**param_data))

        output_params = []
        for param_data in task_input.output_parameters:
            output_params.append(TaskParameter(**param_data))

        # Create task
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            name=task_input.name,
            description=task_input.description,
            instructions=task_input.instructions,
            input_parameters=input_params,
            output_parameters=output_params,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            usage_count=0,
        )

        # Store in database
        await self.memory_manager.create_task(task)
        logger.info(f"Created task: {task.name} (ID: {task.id})")

        return CreateTaskOutput(
            task_id=task.id, name=task.name, created_at=task.created_at.isoformat()
        )


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
        # Cast to specific input type
        list_input = ListTasksInput.model_validate(input_data.model_dump())

        tasks = await self.memory_manager.list_tasks(list_input.limit)

        task_list = []
        for task in tasks:
            task_list.append(
                {
                    "task_id": task.id,
                    "name": task.name,
                    "description": task.description,
                    "usage_count": task.usage_count,
                    "created_at": task.created_at.isoformat(),
                    # TODO: Fix this when we convert input_parameters back to proper
                    # TaskParameter relationships
                    "input_parameters": [
                        {
                            "name": p.get("name", ""),
                            "type": p.get("parameter_type", "string"),
                            "description": p.get("description", ""),
                            "required": p.get("required", False),
                            "example_value": p.get("default_value"),
                        }
                        for p in task.input_parameters
                    ],
                }
            )

        return ListTasksOutput(tasks=task_list, total_count=len(task_list))


class ExecuteTaskTool(BaseCoreTool):
    """Tool for executing a task definition (creates TaskExecutionRequest)."""

    def __init__(self, memory_manager: MemoryManager):
        super().__init__(
            name="execute_task",
            description=(
                "Execute a task definition by creating a TaskExecutionRequest "
                "with specific input values"
            ),
            input_schema=ExecuteTaskInput,
            output_schema=ExecuteTaskOutput,
        )
        self.memory_manager = memory_manager

    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """Create an execution request for a task definition."""
        # Cast to specific input type
        exec_input = ExecuteTaskInput.model_validate(input_data.model_dump())

        # Get task definition
        task = await self.memory_manager.get_task(exec_input.task_id)
        if not task:
            raise ValueError(f"Task definition not found: {exec_input.task_id}")

        # Validate input parameters
        missing_params = task.validate_input_parameters(exec_input.input_values)
        if missing_params:
            raise ValueError(f"Missing required parameters: {missing_params}")

        # Apply defaults for optional parameters
        validated_inputs = {}
        for param in task.input_parameters:
            param_name = param["name"]
            if param_name in exec_input.input_values:
                validated_inputs[param_name] = exec_input.input_values[param_name]
            elif not param.get("required", False) and param.get("default_value") is not None:
                validated_inputs[param_name] = param["default_value"]

        # Create execution request
        execution_request = TaskExecutionRequest.create_for_task(
            task_id=exec_input.task_id, input_values=validated_inputs
        )

        # Increment usage count
        task.usage_count += 1
        await self.memory_manager.update_task(task)

        logger.info(f"Created execution request for task {task.name}: {execution_request.id}")

        return ExecuteTaskOutput(
            execution_request_id=execution_request.id,
            agent_id=execution_request.requested_by,  # type: ignore[attr-defined]  # TODO: Fix this mess
            task_name=task.name,
            resolved_instructions=task.resolve_instructions(validated_inputs),
        )
