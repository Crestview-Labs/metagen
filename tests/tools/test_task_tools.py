"""Tests for task management tools."""

from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from common.models import Parameter, TaskConfig, TaskDefinition
from common.models.enums import ParameterType
from common.types import ToolCallResult, ToolErrorType
from tools.core.task_tools import (
    CreateTaskInput,
    CreateTaskTool,
    ExecuteTaskInput,
    ExecuteTaskTool,
    ListTasksInput,
    ListTasksTool,
)


@pytest.fixture
def mock_memory_manager() -> MagicMock:
    """Create a mock memory manager."""
    memory_manager = MagicMock()
    memory_manager.storage_backend = AsyncMock()
    return memory_manager


@pytest.fixture
def sample_task_definition() -> TaskDefinition:
    """Create a sample task definition."""
    return TaskDefinition(
        name="Test Task",
        description="A test task that processes files",
        instructions="Process the input file and generate a summary",
        input_schema=[
            Parameter(
                name="file_path",
                description="Path to the input file",
                type=ParameterType.STRING,
                required=True,
            ),
            Parameter(
                name="max_length",
                description="Maximum summary length",
                type=ParameterType.INTEGER,
                required=False,
                default=100,
            ),
        ],
        output_schema=[
            Parameter(
                name="summary",
                description="Generated summary",
                type=ParameterType.STRING,
                required=True,
            )
        ],
    )


@pytest.fixture
def sample_task_config(sample_task_definition: TaskDefinition) -> TaskConfig:
    """Create a sample task config."""
    return TaskConfig(id="task-123", name="Test Task", definition=sample_task_definition)


class TestCreateTaskTool:
    """Tests for CreateTaskTool."""

    @pytest.mark.asyncio
    async def test_create_task_success(
        self, mock_memory_manager: MagicMock, sample_task_definition: TaskDefinition
    ) -> None:
        """Test successful task creation."""
        # Arrange
        tool = CreateTaskTool(memory_manager=mock_memory_manager)
        mock_memory_manager.create_task = AsyncMock()

        # Create input
        input_data = CreateTaskInput(task_definition=sample_task_definition)

        # Act
        result = await tool.execute(input_data.model_dump())

        # Assert
        assert isinstance(result, ToolCallResult)
        assert result.is_error is False
        assert result.tool_name == "create_task"

        # Parse the output from JSON
        import json

        output_data = json.loads(result.content)
        assert output_data["name"] == "Test Task"
        assert "task_id" in output_data

        mock_memory_manager.create_task.assert_called_once()
        stored_task = mock_memory_manager.create_task.call_args[0][0]
        assert isinstance(stored_task, TaskConfig)
        assert stored_task.name == "Test Task"
        assert stored_task.definition == sample_task_definition

    @pytest.mark.asyncio
    async def test_create_task_with_empty_name(self, mock_memory_manager: MagicMock) -> None:
        """Test task creation with empty name."""
        # Arrange
        tool = CreateTaskTool(memory_manager=mock_memory_manager)
        mock_memory_manager.create_task = AsyncMock()

        # Create definition with empty name
        definition = TaskDefinition(
            name="",  # Empty name
            description="Test description",
            instructions="Do something",
            input_schema=[],
            output_schema=[],
        )

        input_data = CreateTaskInput(task_definition=definition)

        # Act - Tool should still create it, validation is in the definition
        result = await tool.execute(input_data.model_dump())

        # Assert
        assert isinstance(result, ToolCallResult)
        assert result.is_error is False

        # Parse the output from JSON
        import json

        output_data = json.loads(result.content)
        assert output_data["name"] == ""
        mock_memory_manager.create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_task_storage_error(
        self, mock_memory_manager: MagicMock, sample_task_definition: TaskDefinition
    ) -> None:
        """Test task creation when storage fails."""
        # Arrange
        tool = CreateTaskTool(memory_manager=mock_memory_manager)
        mock_memory_manager.create_task = AsyncMock(side_effect=Exception("Storage error"))

        input_data = CreateTaskInput(task_definition=sample_task_definition)

        # Act
        result = await tool.execute(input_data.model_dump())

        # Assert - error is wrapped in ToolCallResult
        assert isinstance(result, ToolCallResult)
        assert result.is_error is True
        assert result.error and "Storage error" in result.error
        assert result.error_type == ToolErrorType.EXECUTION_ERROR


class TestListTasksTool:
    """Tests for ListTasksTool."""

    @pytest.mark.asyncio
    async def test_list_tasks_success(
        self, mock_memory_manager: MagicMock, sample_task_config: TaskConfig
    ) -> None:
        """Test successful task listing."""
        # Arrange
        tool = ListTasksTool(memory_manager=mock_memory_manager)
        another_task_config = TaskConfig(
            id="task-456",
            name="Another Task",
            definition=TaskDefinition(
                name="Another Task",
                description="Another test task",
                instructions="Do something else",
                input_schema=[],
                output_schema=[],
            ),
        )
        mock_memory_manager.list_tasks = AsyncMock(
            return_value=[sample_task_config, another_task_config]
        )

        input_data = ListTasksInput(limit=50)

        # Act
        result = await tool.execute(input_data.model_dump())

        # Assert
        assert isinstance(result, ToolCallResult)
        assert result.is_error is False
        assert result.tool_name == "list_tasks"

        # Parse the output from JSON
        import json

        output_data = json.loads(result.content)
        assert output_data["total_count"] == 2
        assert len(output_data["tasks"]) == 2
        assert output_data["tasks"][0]["name"] == "Test Task"
        assert output_data["tasks"][1]["name"] == "Another Task"

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, mock_memory_manager: MagicMock) -> None:
        """Test listing when no tasks exist."""
        # Arrange
        tool = ListTasksTool(memory_manager=mock_memory_manager)
        mock_memory_manager.list_tasks = AsyncMock(return_value=[])

        input_data = ListTasksInput(limit=50)

        # Act
        result = await tool.execute(input_data.model_dump())

        # Assert
        assert isinstance(result, ToolCallResult)
        assert result.is_error is False

        # Parse the output from JSON
        import json

        output_data = json.loads(result.content)
        assert output_data["total_count"] == 0
        assert len(output_data["tasks"]) == 0

    @pytest.mark.asyncio
    async def test_list_tasks_storage_error(self, mock_memory_manager: MagicMock) -> None:
        """Test task listing when storage fails."""
        # Arrange
        tool = ListTasksTool(memory_manager=mock_memory_manager)
        mock_memory_manager.list_tasks = AsyncMock(side_effect=Exception("Storage error"))

        input_data = ListTasksInput(limit=50)

        # Act
        result = await tool.execute(input_data.model_dump())

        # Assert - error is wrapped in ToolCallResult
        assert isinstance(result, ToolCallResult)
        assert result.is_error is True
        assert result.error and "Storage error" in result.error
        assert result.error_type == ToolErrorType.EXECUTION_ERROR


class TestExecuteTaskTool:
    """Tests for ExecuteTaskTool."""

    @pytest.mark.asyncio
    async def test_execute_task_not_found(self, mock_memory_manager: MagicMock) -> None:
        """Test executing a non-existent task."""
        # Arrange
        tool = ExecuteTaskTool(memory_manager=mock_memory_manager)
        mock_memory_manager.get_task = AsyncMock(return_value=None)

        input_data = ExecuteTaskInput(
            task_id="nonexistent-task", input_values={"file_path": "/tmp/test.txt"}
        )

        # Act
        result = await tool.execute(input_data.model_dump())

        # Assert - error is wrapped in ToolCallResult
        assert isinstance(result, ToolCallResult)
        assert result.is_error is True
        assert result.error and "Task definition not found: nonexistent-task" in result.error
        assert result.error_type == ToolErrorType.EXECUTION_ERROR

    @pytest.mark.asyncio
    async def test_execute_task_success(
        self, mock_memory_manager: MagicMock, sample_task_config: TaskConfig
    ) -> None:
        """Test successful task execution."""
        # Arrange
        tool = ExecuteTaskTool(memory_manager=mock_memory_manager)
        mock_memory_manager.get_task = AsyncMock(return_value=sample_task_config)

        input_data = ExecuteTaskInput(
            task_id="task-123", input_values={"file_path": "/tmp/test.txt", "max_length": 200}
        )

        # Act
        result = await tool.execute(input_data.model_dump())

        # Assert
        assert isinstance(result, ToolCallResult)
        assert result.is_error is False
        assert result.tool_name == "execute_task"

        # Parse the output from JSON
        import json

        output_data = json.loads(result.content)
        assert output_data["task_id"] == "task-123"
        assert output_data["task_name"] == "Test Task"
        assert output_data["agent_id"] == "task_execution_agent"

    @pytest.mark.asyncio
    async def test_execute_task_parameter_validation(
        self, mock_memory_manager: MagicMock, sample_task_config: TaskConfig
    ) -> None:
        """Test parameter validation during task execution."""
        # Arrange
        tool = ExecuteTaskTool(memory_manager=mock_memory_manager)
        mock_memory_manager.get_task = AsyncMock(return_value=sample_task_config)

        input_data = ExecuteTaskInput(
            task_id="task-123",
            input_values={"max_length": 50},  # Missing required file_path
        )

        # Act
        result = await tool.execute(input_data.model_dump())

        # Assert - error is wrapped in ToolCallResult
        assert isinstance(result, ToolCallResult)
        assert result.is_error is True
        assert result.error and "Missing required parameters: ['file_path']" in result.error
        assert result.error_type == ToolErrorType.EXECUTION_ERROR

    @pytest.mark.asyncio
    async def test_execute_task_with_string_number(
        self, mock_memory_manager: MagicMock, sample_task_config: TaskConfig
    ) -> None:
        """Test task execution with string number for integer parameter."""
        # Arrange
        tool = ExecuteTaskTool(memory_manager=mock_memory_manager)
        mock_memory_manager.get_task = AsyncMock(return_value=sample_task_config)

        input_data = ExecuteTaskInput(
            task_id="task-123",
            input_values={
                "file_path": "/tmp/test.txt",
                "max_length": "200",  # String that could be converted to int
            },
        )

        # Act
        result = await tool.execute(input_data.model_dump())

        # Assert
        assert isinstance(result, ToolCallResult)
        assert result.is_error is False

        # Parse the output from JSON
        import json

        output_data = json.loads(result.content)
        assert output_data["task_id"] == "task-123"

    @pytest.mark.asyncio
    async def test_execute_task_with_defaults(
        self, mock_memory_manager: MagicMock, sample_task_config: TaskConfig
    ) -> None:
        """Test task execution with default parameter values."""
        # Arrange
        tool = ExecuteTaskTool(memory_manager=mock_memory_manager)
        mock_memory_manager.get_task = AsyncMock(return_value=sample_task_config)

        input_data = ExecuteTaskInput(
            task_id="task-123",
            input_values={"file_path": "/tmp/test.txt"},  # max_length should use default
        )

        # Act
        result = await tool.execute(input_data.model_dump())

        # Assert
        assert isinstance(result, ToolCallResult)
        assert result.is_error is False

        # Parse the output from JSON
        import json

        output_data = json.loads(result.content)
        assert output_data["task_id"] == "task-123"

    @pytest.mark.asyncio
    async def test_execute_task_complex_types(self, mock_memory_manager: MagicMock) -> None:
        """Test task execution with complex parameter types."""
        # Arrange
        complex_task = TaskConfig(
            id="complex-task",
            name="Complex Task",
            definition=TaskDefinition(
                name="Complex Task",
                description="Process complex data task",
                instructions="Process complex data",
                input_schema=[
                    Parameter(
                        name="config",
                        description="Configuration object",
                        type=ParameterType.DICT,
                        required=True,
                    ),
                    Parameter(
                        name="items",
                        description="List of items",
                        type=ParameterType.LIST,
                        required=True,
                    ),
                ],
                output_schema=[],
            ),
        )
        tool = ExecuteTaskTool(memory_manager=mock_memory_manager)
        mock_memory_manager.get_task = AsyncMock(return_value=complex_task)

        input_data = ExecuteTaskInput(
            task_id="complex-task",
            input_values={
                "config": {"setting1": "value1", "setting2": 42},
                "items": ["item1", "item2", "item3"],
            },
        )

        # Act
        result = await tool.execute(input_data.model_dump())

        # Assert
        assert isinstance(result, ToolCallResult)
        assert result.is_error is False

        # Parse the output from JSON
        import json

        output_data = json.loads(result.content)
        assert output_data["task_id"] == "complex-task"
        assert output_data["task_name"] == "Complex Task"


@pytest.mark.asyncio
class TestTaskToolIntegration:
    """Integration tests for task tools working together."""

    async def test_create_list_execute_flow(
        self, mock_memory_manager: MagicMock, sample_task_definition: TaskDefinition
    ) -> None:
        """Test the full workflow of creating, listing, and executing a task."""
        # Create tools
        create_tool = CreateTaskTool(memory_manager=mock_memory_manager)
        list_tool = ListTasksTool(memory_manager=mock_memory_manager)
        execute_tool = ExecuteTaskTool(memory_manager=mock_memory_manager)

        # Mock storage behavior
        stored_tasks = []

        async def mock_create_task(task: TaskConfig) -> str:
            stored_tasks.append(task)
            return task.id

        async def mock_list_tasks(limit: Optional[int] = None) -> list[TaskConfig]:
            return stored_tasks[:limit] if limit else stored_tasks

        async def mock_get_task(task_id: str) -> Optional[TaskConfig]:
            for task in stored_tasks:
                if task.id == task_id:
                    return task
            return None

        mock_memory_manager.create_task = AsyncMock(side_effect=mock_create_task)
        mock_memory_manager.list_tasks = AsyncMock(side_effect=mock_list_tasks)
        mock_memory_manager.get_task = AsyncMock(side_effect=mock_get_task)

        # Step 1: Create a task
        create_input = CreateTaskInput(task_definition=sample_task_definition)
        create_result = await create_tool.execute(create_input.model_dump())
        assert isinstance(create_result, ToolCallResult)
        assert create_result.is_error is False

        # Parse create output
        import json

        create_output = json.loads(create_result.content)
        task_id = create_output["task_id"]

        # Step 2: List tasks
        list_input = ListTasksInput(limit=50)
        list_result = await list_tool.execute(list_input.model_dump())
        assert isinstance(list_result, ToolCallResult)
        assert list_result.is_error is False

        # Parse list output
        list_output = json.loads(list_result.content)
        assert list_output["total_count"] == 1
        assert list_output["tasks"][0]["name"] == "Test Task"

        # Step 3: Execute the task
        execute_input = ExecuteTaskInput(
            task_id=task_id, input_values={"file_path": "/tmp/test.txt", "max_length": 150}
        )
        execute_result = await execute_tool.execute(execute_input.model_dump())
        assert isinstance(execute_result, ToolCallResult)
        assert execute_result.is_error is False

        # Parse execute output
        execute_output = json.loads(execute_result.content)
        assert execute_output["task_id"] == task_id
        assert execute_output["task_name"] == "Test Task"
