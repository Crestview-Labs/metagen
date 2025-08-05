"""Integration tests for the task subsystem.

These tests verify the complete flow of task creation, storage, and execution
through the various components working together.
"""

from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import pytest

from agents.memory import MemoryManager
from common.models import Parameter, TaskDefinition
from common.models.enums import ParameterType
from common.types import ToolCall, ToolCallResult
from db.engine import DatabaseEngine
from tools.core.task_tools import CreateTaskTool, ExecuteTaskTool, ListTasksTool
from tools.registry import ToolExecutor


@pytest.fixture
async def test_db(tmp_path: Path) -> AsyncGenerator[DatabaseEngine, None]:
    """Create a test database."""
    # Create a temporary database file
    db_path = tmp_path / "test.db"
    db_engine = DatabaseEngine(db_path)
    await db_engine.initialize()
    yield db_engine
    await db_engine.close()


@pytest.fixture
async def memory_manager(test_db: DatabaseEngine) -> MemoryManager:
    """Create a memory manager with test database."""
    manager = MemoryManager(db_engine=test_db)
    await manager.initialize()
    return manager


@pytest.fixture
def tool_executor() -> ToolExecutor:
    """Create a tool executor."""
    return ToolExecutor()


@pytest.fixture
def task_tools(memory_manager: MemoryManager) -> dict[str, Any]:
    """Create task management tools."""
    return {
        "create_task": CreateTaskTool(memory_manager=memory_manager),
        "list_tasks": ListTasksTool(memory_manager=memory_manager),
        "execute_task": ExecuteTaskTool(memory_manager=memory_manager),
    }


@pytest.fixture
def sample_task_definition() -> TaskDefinition:
    """Create a sample task definition."""
    return TaskDefinition(
        name="File Processor",
        description="Process files and generate summaries",
        instructions=(
            "Read the file at {file_path} and create a summary with max {max_length} words"
        ),
        input_schema=[
            Parameter(
                name="file_path",
                description="Path to the input file",
                type=ParameterType.STRING,
                required=True,
            ),
            Parameter(
                name="max_length",
                description="Maximum summary length in words",
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
            ),
            Parameter(
                name="word_count",
                description="Actual word count",
                type=ParameterType.INTEGER,
                required=True,
            ),
        ],
    )


class TestTaskSubsystemIntegration:
    """Integration tests for the complete task subsystem."""

    @pytest.mark.asyncio
    async def test_create_and_list_tasks(
        self,
        memory_manager: MemoryManager,
        task_tools: dict[str, Any],
        sample_task_definition: TaskDefinition,
    ) -> None:
        """Test creating and listing tasks through the tools."""
        create_tool = task_tools["create_task"]
        list_tool = task_tools["list_tasks"]

        # Create a task
        create_result = await create_tool.execute(
            {"task_definition": sample_task_definition.model_dump()}
        )

        assert isinstance(create_result, ToolCallResult)
        assert create_result.is_error is False

        # List tasks
        list_result = await list_tool.execute({"limit": 10})

        assert isinstance(list_result, ToolCallResult)
        assert list_result.is_error is False

        # Parse result
        import json

        tasks = json.loads(list_result.content)["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["name"] == "File Processor"

    @pytest.mark.asyncio
    async def test_execute_task_via_interceptor(
        self,
        memory_manager: MemoryManager,
        task_tools: dict[str, Any],
        tool_executor: ToolExecutor,
        sample_task_definition: TaskDefinition,
    ) -> None:
        """Test task execution through the interceptor pattern."""
        # Create a task first
        create_tool = task_tools["create_task"]
        create_result = await create_tool.execute(
            {"task_definition": sample_task_definition.model_dump()}
        )

        import json

        task_id = json.loads(create_result.content)["task_id"]

        # Register the execute_task tool without interceptor
        # This will test the actual tool's behavior
        tool_executor.register_core_tool(task_tools["execute_task"])

        # Execute task through tool executor
        tool_call = ToolCall(
            id="test-call-1",
            name="execute_task",
            arguments={
                "task_id": task_id,
                "input_values": {"file_path": "/tmp/test.txt", "max_length": 50},
            },
        )

        result = await tool_executor.execute(tool_call)

        assert isinstance(result, ToolCallResult)
        assert result.is_error is False
        # The execute_task tool returns task metadata as JSON
        import json

        result_data = json.loads(result.content)
        assert result_data["task_id"] == task_id
        assert result_data["task_name"] == "File Processor"
        assert result_data["agent_id"] == "task_execution_agent"

    @pytest.mark.asyncio
    async def test_full_task_lifecycle(
        self, memory_manager: MemoryManager, task_tools: dict[str, Any]
    ) -> None:
        """Test the complete lifecycle: create, list, get, execute."""
        # 1. Create a task
        create_tool = task_tools["create_task"]
        task_def = TaskDefinition(
            name="Simple Task",
            description="A simple test task",
            instructions="Echo the input: {message}",
            input_schema=[
                Parameter(
                    name="message",
                    description="Message to echo",
                    type=ParameterType.STRING,
                    required=True,
                )
            ],
            output_schema=[
                Parameter(
                    name="echo",
                    description="Echoed message",
                    type=ParameterType.STRING,
                    required=True,
                )
            ],
        )

        create_result = await create_tool.execute({"task_definition": task_def.model_dump()})

        import json

        create_data = json.loads(create_result.content)
        task_id = create_data["task_id"]

        # 2. List tasks to verify it exists
        list_tool = task_tools["list_tasks"]
        list_result = await list_tool.execute({"limit": 10})

        list_data = json.loads(list_result.content)
        assert list_data["total_count"] >= 1
        assert any(t["name"] == "Simple Task" for t in list_data["tasks"])

        # 3. Get the task directly from storage
        task_config = await memory_manager.get_task(task_id)
        assert task_config is not None
        assert task_config.name == "Simple Task"
        assert task_config.definition.instructions == "Echo the input: {message}"

        # 4. Validate execute_task tool (without actual execution)
        execute_tool = task_tools["execute_task"]

        # Test validation - missing required parameter
        validation_result = await execute_tool.execute(
            {
                "task_id": task_id,
                "input_values": {},  # Missing required 'message'
            }
        )

        assert validation_result.is_error is True
        assert "Missing required parameters" in validation_result.error

    @pytest.mark.asyncio
    async def test_task_execution_interceptor_pattern(self, memory_manager: MemoryManager) -> None:
        """Test the execute_task interceptor pattern."""
        # Create a task
        task_def = TaskDefinition(
            name="Echo Task",
            description="Echo a message",
            instructions="Echo this: {message}",
            input_schema=[
                Parameter(
                    name="message",
                    description="Message to echo",
                    type=ParameterType.STRING,
                    required=True,
                )
            ],
            output_schema=[],
        )

        # Create task using memory manager's method
        create_tool = CreateTaskTool(memory_manager=memory_manager)
        create_result = await create_tool.execute({"task_definition": task_def.model_dump()})

        import json

        task_id = json.loads(create_result.content)["task_id"]

        # Create tool executor with a test interceptor
        tool_executor = ToolExecutor()

        # Create a test interceptor that simulates task execution
        async def test_interceptor(
            tool_call_id: str, tool_name: str, params: dict[str, Any]
        ) -> Optional[ToolCallResult]:
            if tool_name == "execute_task":
                # Verify we get the right parameters
                assert params["task_id"] == task_id
                assert params["input_values"]["message"] == "Hello, World!"

                # Return a simulated result
                return ToolCallResult(
                    tool_name="execute_task",
                    tool_call_id=f"task_{task_id}",
                    content="Task executed successfully: echoed Hello, World!",
                    is_error=False,
                    error=None,
                    error_type=None,
                    user_display=None,
                    metadata={"task_id": task_id, "result": "Hello, World! (echoed)"},
                )
            return None

        tool_executor.register_interceptor("execute_task", test_interceptor)

        # Register the actual tool as well
        execute_tool = ExecuteTaskTool(memory_manager=memory_manager)
        tool_executor.register_core_tool(execute_tool)

        # Execute the task
        tool_call = ToolCall(
            id="test-exec-1",
            name="execute_task",
            arguments={"task_id": task_id, "input_values": {"message": "Hello, World!"}},
        )

        result = await tool_executor.execute(tool_call)

        assert isinstance(result, ToolCallResult)
        assert result.tool_name == "execute_task"
        assert not result.is_error
        # The interceptor returns a custom message
        assert "Task executed successfully: echoed Hello, World!" == result.content
        assert result.metadata["result"] == "Hello, World! (echoed)"

    @pytest.mark.asyncio
    async def test_parameter_validation_and_defaults(
        self, memory_manager: MemoryManager, task_tools: dict[str, Any]
    ) -> None:
        """Test parameter validation and default value handling."""
        # Create a task with optional parameters
        task_def = TaskDefinition(
            name="Configurable Task",
            description="Task with optional parameters",
            instructions="Process with timeout {timeout} and retries {retries}",
            input_schema=[
                Parameter(
                    name="timeout",
                    description="Timeout in seconds",
                    type=ParameterType.INTEGER,
                    required=False,
                    default=30,
                ),
                Parameter(
                    name="retries",
                    description="Number of retries",
                    type=ParameterType.INTEGER,
                    required=False,
                    default=3,
                ),
                Parameter(
                    name="strict",
                    description="Strict mode",
                    type=ParameterType.BOOLEAN,
                    required=False,
                    default=False,
                ),
            ],
            output_schema=[],
        )

        # Create the task
        create_tool = task_tools["create_task"]
        create_result = await create_tool.execute({"task_definition": task_def.model_dump()})

        import json

        task_id = json.loads(create_result.content)["task_id"]

        # Execute with partial parameters (using defaults)
        execute_tool = task_tools["execute_task"]
        exec_result = await execute_tool.execute(
            {
                "task_id": task_id,
                "input_values": {
                    "timeout": 60  # Override default
                    # retries will use default (3)
                    # strict will use default (False)
                },
            }
        )

        # This should succeed as the tool validates the task exists
        assert exec_result.is_error is False

    @pytest.mark.asyncio
    async def test_multiple_task_types(
        self, memory_manager: MemoryManager, task_tools: dict[str, Any]
    ) -> None:
        """Test creating and managing multiple different task types."""
        create_tool = task_tools["create_task"]
        list_tool = task_tools["list_tasks"]

        # Create different types of tasks
        task_types = [
            TaskDefinition(
                name="Data Analyzer",
                description="Analyze data files",
                instructions="Analyze {data_file} and produce {report_type} report",
                input_schema=[
                    Parameter(
                        name="data_file",
                        description="Data file path",
                        type=ParameterType.STRING,
                        required=True,
                    ),
                    Parameter(
                        name="report_type",
                        description="Type of report",
                        type=ParameterType.STRING,
                        required=True,
                    ),
                ],
                output_schema=[
                    Parameter(
                        name="analysis",
                        description="Analysis results",
                        type=ParameterType.DICT,
                        required=True,
                    )
                ],
            ),
            TaskDefinition(
                name="Code Generator",
                description="Generate code from specifications",
                instructions="Generate {language} code for {specification}",
                input_schema=[
                    Parameter(
                        name="language",
                        description="Programming language",
                        type=ParameterType.STRING,
                        required=True,
                    ),
                    Parameter(
                        name="specification",
                        description="Code specification",
                        type=ParameterType.STRING,
                        required=True,
                    ),
                ],
                output_schema=[
                    Parameter(
                        name="code",
                        description="Generated code",
                        type=ParameterType.STRING,
                        required=True,
                    )
                ],
            ),
            TaskDefinition(
                name="Test Runner",
                description="Run tests on code",
                instructions="Run tests in {test_dir} with options {options}",
                input_schema=[
                    Parameter(
                        name="test_dir",
                        description="Test directory",
                        type=ParameterType.STRING,
                        required=True,
                    ),
                    Parameter(
                        name="options",
                        description="Test options",
                        type=ParameterType.LIST,
                        required=False,
                        default=[],
                    ),
                ],
                output_schema=[
                    Parameter(
                        name="results",
                        description="Test results",
                        type=ParameterType.DICT,
                        required=True,
                    )
                ],
            ),
        ]

        # Create all tasks
        created_ids = []
        for task_def in task_types:
            result = await create_tool.execute({"task_definition": task_def.model_dump()})
            import json

            task_id = json.loads(result.content)["task_id"]
            created_ids.append(task_id)

        # List all tasks
        list_result = await list_tool.execute({"limit": 50})

        import json

        list_data = json.loads(list_result.content)
        tasks = list_data["tasks"]

        # Verify all tasks were created
        assert list_data["total_count"] >= 3
        task_names = [t["name"] for t in tasks]
        assert "Data Analyzer" in task_names
        assert "Code Generator" in task_names
        assert "Test Runner" in task_names

        # Verify each task has correct structure
        for task in tasks:
            if task["name"] == "Data Analyzer":
                assert len(task["input_schema"]) == 2
                assert len(task["output_schema"]) == 1
            elif task["name"] == "Code Generator":
                assert len(task["input_schema"]) == 2
                assert len(task["output_schema"]) == 1
            elif task["name"] == "Test Runner":
                assert len(task["input_schema"]) == 2
                assert task["input_schema"][1]["required"] is False  # options is optional
                assert len(task["output_schema"]) == 1

    @pytest.mark.asyncio
    async def test_error_handling(
        self, memory_manager: MemoryManager, task_tools: dict[str, Any]
    ) -> None:
        """Test error handling in various scenarios."""
        execute_tool = task_tools["execute_task"]

        # Test 1: Execute non-existent task
        result = await execute_tool.execute(
            {"task_id": "non-existent-task-id", "input_values": {"some": "value"}}
        )

        assert result.is_error is True
        assert "Task definition not found" in result.error

        # Test 2: Create task with invalid schema
        create_tool = task_tools["create_task"]

        # Missing required fields
        invalid_task_def = {
            "name": "Invalid Task"
            # Missing description, instructions, schemas
        }

        result = await create_tool.execute({"task_definition": invalid_task_def})

        assert result.is_error is True
        assert "Field required" in result.error or "missing" in result.error

        # Test 3: Execute task with wrong parameter types
        # First create a valid task
        valid_task_def = TaskDefinition(
            name="Type Test Task",
            description="Test parameter types",
            instructions="Process {count} items",
            input_schema=[
                Parameter(
                    name="count",
                    description="Number of items",
                    type=ParameterType.INTEGER,
                    required=True,
                )
            ],
            output_schema=[],
        )

        create_result = await create_tool.execute({"task_definition": valid_task_def.model_dump()})

        import json

        task_id = json.loads(create_result.content)["task_id"]

        # Execute with wrong type (string instead of integer)
        # The execute tool should handle this gracefully
        exec_result = await execute_tool.execute(
            {
                "task_id": task_id,
                "input_values": {
                    "count": "not-a-number"  # Should be integer
                },
            }
        )

        # The tool itself doesn't do type validation, it just passes through
        # Type validation would happen in the TaskExecutionAgent
        assert exec_result.is_error is False  # Tool execution succeeds
        # Parse the output to verify task_name
        import json

        output_data = json.loads(exec_result.content)
        assert output_data["task_name"] == "Type Test Task"
