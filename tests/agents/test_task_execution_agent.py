"""Tests for TaskExecutionAgent."""

from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.task_execution_agent import TaskExecutionAgent
from common.messages import AgentMessage, SystemMessage, ToolCallMessage, ToolCallRequest
from common.models.enums import ParameterType
from common.types import ParameterValue, TaskExecutionContext, ToolCallResult, ToolErrorType


@pytest.fixture
def mock_memory_manager() -> MagicMock:
    """Create a mock memory manager."""
    memory_manager = MagicMock()
    memory_manager.storage_backend = AsyncMock()
    return memory_manager


@pytest.fixture
def mock_llm_config() -> dict[str, Any]:
    """Create mock LLM configuration."""
    return {"model": "test-model", "temperature": 0.7}


@pytest.fixture
def sample_task_context() -> TaskExecutionContext:
    """Create a sample task execution context."""
    return TaskExecutionContext(
        task_id="task-123",
        task_name="Process File",
        instructions=(
            "Read the file at {file_path} and create a summary with max {max_length} words"
        ),
        input_values={
            "file_path": ParameterValue(value="/tmp/test.txt", parameter_type=ParameterType.STRING),
            "max_length": ParameterValue(value=100, parameter_type=ParameterType.INTEGER),
        },
    )


@pytest.fixture
def task_execution_agent(
    mock_memory_manager: MagicMock, mock_llm_config: dict[str, Any]
) -> TaskExecutionAgent:
    """Create a TaskExecutionAgent instance."""
    return TaskExecutionAgent(
        agent_id="task-agent-1",
        memory_manager=mock_memory_manager,
        llm_config=mock_llm_config,
        available_tools=[],
    )


class TestTaskExecutionAgent:
    """Tests for TaskExecutionAgent."""

    def test_initialization(self, task_execution_agent: TaskExecutionAgent) -> None:
        """Test agent initialization."""
        assert task_execution_agent.agent_id == "task-agent-1"
        assert task_execution_agent.current_task_context is None
        assert task_execution_agent.is_executing is False
        assert "TaskExecutionAgent" in task_execution_agent.instructions

    def test_set_current_task(
        self, task_execution_agent: TaskExecutionAgent, sample_task_context: TaskExecutionContext
    ) -> None:
        """Test setting current task context."""
        task_execution_agent.set_current_task(sample_task_context)
        assert task_execution_agent.current_task_context == sample_task_context
        assert task_execution_agent.is_executing is True
        assert task_execution_agent.get_current_task_id() == "task-123"

    def test_clear_current_task(
        self, task_execution_agent: TaskExecutionAgent, sample_task_context: TaskExecutionContext
    ) -> None:
        """Test clearing current task."""
        task_execution_agent.set_current_task(sample_task_context)
        task_execution_agent.clear_current_task()
        assert task_execution_agent.current_task_context is None
        assert task_execution_agent.is_executing is False
        assert task_execution_agent.get_current_task_id() is None

    def test_build_task_prompt(
        self, task_execution_agent: TaskExecutionAgent, sample_task_context: TaskExecutionContext
    ) -> None:
        """Test building task prompt from context."""
        prompt = task_execution_agent.build_task_prompt(sample_task_context)

        assert "Task: Process File" in prompt
        assert "Read the file at {file_path}" in prompt
        assert "file_path: /tmp/test.txt" in prompt
        assert "max_length: 100" in prompt
        assert "Please execute this task now using available tools" in prompt

    @pytest.mark.asyncio
    async def test_build_context(
        self, task_execution_agent: TaskExecutionAgent, sample_task_context: TaskExecutionContext
    ) -> None:
        """Test building execution context."""
        task_execution_agent.set_current_task(sample_task_context)

        context = await task_execution_agent.build_context("test query")

        assert len(context) == 2
        assert isinstance(context[0], SystemMessage)
        assert "TaskExecutionAgent" in context[0].content
        assert isinstance(context[1], SystemMessage)
        assert "Current task ID: task-123" in context[1].content

    @pytest.mark.asyncio
    async def test_execute_task_fully_success(
        self, task_execution_agent: TaskExecutionAgent, sample_task_context: TaskExecutionContext
    ) -> None:
        """Test successful task execution."""
        # Mock the stream_chat to return a successful response
        mock_messages = [
            ToolCallMessage(
                tool_calls=[
                    ToolCallRequest(
                        tool_id="1", tool_name="read_file", tool_args={"path": "/tmp/test.txt"}
                    )
                ]
            ),
            AgentMessage(content="Summary: This is a test file with sample content."),
        ]

        async def mock_stream_chat(message: Any) -> AsyncIterator[Any]:
            for msg in mock_messages:
                yield msg

        task_execution_agent.stream_chat = mock_stream_chat  # type: ignore[method-assign]

        # Execute task
        result = await task_execution_agent.execute_task_fully(sample_task_context)

        # Verify result
        assert isinstance(result, ToolCallResult)
        assert result.tool_name == "execute_task"
        assert result.tool_call_id == "task_task-123"
        assert result.is_error is False
        assert "Task executed successfully" in result.content
        assert result.metadata["task_id"] == "task-123"
        assert result.metadata["agent_id"] == "task-agent-1"
        assert result.metadata["execution_stats"]["tool_calls"] == 1
        assert result.metadata["execution_stats"]["errors"] == 0
        assert "Summary: This is a test file" in result.metadata["result"]

    @pytest.mark.asyncio
    async def test_execute_task_fully_failure(
        self, task_execution_agent: TaskExecutionAgent, sample_task_context: TaskExecutionContext
    ) -> None:
        """Test task execution failure."""

        # Mock the stream_chat to raise an exception
        async def mock_stream_chat(message: Any) -> AsyncIterator[Any]:
            raise Exception("Test execution error")
            yield  # Never reached

        task_execution_agent.stream_chat = mock_stream_chat  # type: ignore[method-assign]

        # Execute task
        result = await task_execution_agent.execute_task_fully(sample_task_context)

        # Verify error result
        assert isinstance(result, ToolCallResult)
        assert result.tool_name == "execute_task"
        assert result.is_error is True
        assert result.error == "Test execution error"
        assert result.error_type == ToolErrorType.EXECUTION_ERROR
        assert result.user_display and "Error executing task 'Process File'" in result.user_display

    @pytest.mark.asyncio
    async def test_execute_task_fully_no_result(
        self, task_execution_agent: TaskExecutionAgent, sample_task_context: TaskExecutionContext
    ) -> None:
        """Test task execution with no result."""
        # Mock the stream_chat to return no final response
        mock_messages = [
            ToolCallMessage(
                tool_calls=[
                    ToolCallRequest(
                        tool_id="1", tool_name="read_file", tool_args={"path": "/tmp/test.txt"}
                    )
                ]
            )
        ]

        async def mock_stream_chat(message: Any) -> AsyncIterator[Any]:
            for msg in mock_messages:
                yield msg

        task_execution_agent.stream_chat = mock_stream_chat  # type: ignore[method-assign]

        # Execute task
        result = await task_execution_agent.execute_task_fully(sample_task_context)

        # Verify failure result
        assert isinstance(result, ToolCallResult)
        assert result.is_error is True
        assert "Task execution failed or produced no result" in result.content

    def test_get_task_info_idle(self, task_execution_agent: TaskExecutionAgent) -> None:
        """Test getting task info when idle."""
        info = task_execution_agent.get_task_info()

        assert info["status"] == "idle"
        assert info["agent_id"] == "task-agent-1"
        assert info["current_task"] is None

    def test_get_task_info_executing(
        self, task_execution_agent: TaskExecutionAgent, sample_task_context: TaskExecutionContext
    ) -> None:
        """Test getting task info while executing."""
        task_execution_agent.set_current_task(sample_task_context)

        info = task_execution_agent.get_task_info()

        assert info["status"] == "executing"
        assert info["agent_id"] == "task-agent-1"
        assert info["current_task"]["task_id"] == "task-123"
        assert info["current_task"]["task_name"] == "Process File"
        assert "file_path" in info["current_task"]["input_values"]

    @pytest.mark.asyncio
    async def test_task_prompt_complex_inputs(
        self, task_execution_agent: TaskExecutionAgent
    ) -> None:
        """Test task prompt with complex input types."""
        complex_context = TaskExecutionContext(
            task_id="complex-task",
            task_name="Process Data",
            instructions="Process data with config {config} and items {items}",
            input_values={
                "config": ParameterValue(
                    value={"key1": "value1", "key2": 42}, parameter_type=ParameterType.DICT
                ),
                "items": ParameterValue(
                    value=["item1", "item2", "item3"], parameter_type=ParameterType.LIST
                ),
            },
        )

        prompt = task_execution_agent.build_task_prompt(complex_context)

        assert 'config: {"key1": "value1", "key2": 42}' in prompt
        assert 'items: ["item1", "item2", "item3"]' in prompt

    def test_task_state_persistence(
        self, task_execution_agent: TaskExecutionAgent, sample_task_context: TaskExecutionContext
    ) -> None:
        """Test that task state persists correctly during execution."""
        # Initially no task
        assert task_execution_agent.current_task_context is None

        # Set task
        task_execution_agent.set_current_task(sample_task_context)
        assert task_execution_agent.current_task_context is not None
        assert task_execution_agent.current_task_context.task_id == "task-123"

        # Task should persist
        assert task_execution_agent.is_executing is True
        assert task_execution_agent.get_current_task_id() == "task-123"

        # Clear task
        task_execution_agent.clear_current_task()
        assert task_execution_agent.current_task_context is None
        assert task_execution_agent.is_executing is False
