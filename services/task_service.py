"""Task service that calls core task tools inline."""

import logging
from typing import Any, Optional

from agents.memory import MemoryManager
from common.models import Task, TaskExecutionRequest, TaskParameter
from tools.core.task_tools import (
    CreateTaskInput,
    CreateTaskTool,
    ExecuteTaskInput,
    ExecuteTaskTool,
    ListTasksInput,
    ListTasksTool,
)

logger = logging.getLogger(__name__)


class TaskService:
    """Service for managing reusable task definitions and execution requests.

    This service calls the same core tools that agents use, ensuring consistency.
    """

    def __init__(self, memory_manager: MemoryManager):
        """Initialize task service with memory manager."""
        self.memory_manager = memory_manager

        # Initialize tools (same ones agents use)
        self.create_task_tool = CreateTaskTool(memory_manager)
        self.list_tasks_tool = ListTasksTool(memory_manager)
        self.execute_task_tool = ExecuteTaskTool(memory_manager)

    async def create_task(
        self,
        name: str,
        description: str,
        # task_type: TaskType,  # TODO: TaskType not defined
        # title_template: str,  # TODO: Not used in CreateTaskInput
        instructions: str,
        input_parameters: Optional[list[TaskParameter]] = None,
        output_parameters: Optional[list[TaskParameter]] = None,
    ) -> Task:
        """Create a new reusable task definition.

        This calls the same create_task tool that agents use.
        """
        # Convert TaskParameter objects to dict format expected by tool
        input_params_dict = []
        if input_parameters:
            for param in input_parameters:
                input_params_dict.append(param.dict())

        output_params_dict = []
        if output_parameters:
            for param in output_parameters:
                output_params_dict.append(param.dict())

        # Call the core tool inline
        input_data = CreateTaskInput(
            name=name,
            description=description,
            instructions=instructions,
            input_parameters=input_params_dict,
            output_parameters=output_params_dict,
        )

        base_result = await self.create_task_tool._execute_impl(input_data)
        # Cast to specific output type
        from tools.core.task_tools import CreateTaskOutput

        result = CreateTaskOutput.model_validate(base_result.model_dump())

        # Return the created Task object
        task = await self.memory_manager.get_task(result.task_id)
        if task is None:
            raise ValueError(f"Failed to retrieve created task {result.task_id}")
        return task

    async def list_tasks(self, limit: int = 50) -> list[Task]:
        """List available task definitions.

        This calls the same list_tasks tool that agents use.
        """
        input_data = ListTasksInput(limit=limit)

        base_result = await self.list_tasks_tool._execute_impl(input_data)
        # Cast to specific output type
        from tools.core.task_tools import ListTasksOutput

        result = ListTasksOutput.model_validate(base_result.model_dump())

        # Convert back to Task objects
        tasks = []
        for task_dict in result.tasks:
            task = await self.memory_manager.get_task(task_dict["task_id"])
            if task:
                tasks.append(task)

        return tasks

    async def create_execution_request(
        self, task_id: str, input_values: dict[str, Any]
    ) -> TaskExecutionRequest:
        """Create an execution request for a task.

        This calls the same execute_task tool that agents use.
        """
        input_data = ExecuteTaskInput(task_id=task_id, input_values=input_values)

        base_result = await self.execute_task_tool._execute_impl(input_data)
        # Cast to specific output type
        from tools.core.task_tools import ExecuteTaskOutput

        result = ExecuteTaskOutput.model_validate(base_result.model_dump())

        # Return the TaskExecutionRequest
        return TaskExecutionRequest(
            id=result.execution_request_id,
            task_id=task_id,
            requested_by=result.agent_id,  # TODO: Fix this field name mismatch
            execution_context={"input_values": input_values},
        )

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task definition by ID."""
        return await self.memory_manager.get_task(task_id)

    async def preview_task_execution(
        self, task_id: str, input_values: dict[str, Any]
    ) -> dict[str, str]:
        """Preview how a task would be executed with given inputs."""
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        # Apply defaults for missing optional parameters
        validated_inputs = {}
        for param in task.input_parameters:
            param_name = param.get("name", "")
            if param_name in input_values:
                validated_inputs[param_name] = input_values[param_name]
            elif not param.get("required", True) and param.get("default_value") is not None:
                validated_inputs[param_name] = param.get("default_value")

        return {
            "resolved_title": task.name,  # Task doesn't have resolve_title
            "resolved_instructions": task.resolve_instructions(validated_inputs),
            "agent_id": f"TASK_EXECUTION_{task_id}",
            "input_values": str(validated_inputs),  # Convert dict to string for type compatibility
        }
