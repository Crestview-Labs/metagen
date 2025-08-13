"""Tests for TaskExecutionAgent."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.task_execution_agent import TaskExecutionAgent
from common.messages import (
    AgentMessage,
    SystemMessage,
    ToolCallMessage,
    ToolCallRequest,
    ToolResultMessage,
    UserMessage,
)
from common.models.enums import ParameterType
from common.types import ParameterValue, TaskExecutionContext


@pytest.fixture
def mock_memory_manager() -> MagicMock:
    """Create a mock memory manager."""
    memory_manager = MagicMock()
    memory_manager.storage_backend = AsyncMock()
    memory_manager.create_turn = AsyncMock(return_value="turn-123")
    memory_manager.update_turn = AsyncMock()
    memory_manager.complete_turn = AsyncMock()
    memory_manager.record_tool_usage = AsyncMock()
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
        tool_call_id="test-tool-call-123",
    )


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create a mock LLM client."""
    return MagicMock()


@pytest.fixture
def task_execution_agent(
    mock_memory_manager: MagicMock, mock_llm_config: dict[str, Any], mock_llm_client: MagicMock
) -> TaskExecutionAgent:
    """Create a TaskExecutionAgent instance."""
    agent = TaskExecutionAgent(
        agent_id="task-agent-1",
        memory_manager=mock_memory_manager,
        llm_config=mock_llm_config,
        llm_client=mock_llm_client,
        available_tools=[],
    )

    return agent


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
    async def test_stream_chat_with_task_context(
        self,
        task_execution_agent: TaskExecutionAgent,
        sample_task_context: TaskExecutionContext,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test stream_chat behavior when task context is set."""
        # Mock the LLM client
        mock_response = AgentMessage(
            agent_id="TASK_AGENT",
            session_id="test-session",
            content="Task processing initiated",
            final=True,
        )

        async def mock_generate_stream(*args: Any, **kwargs: Any) -> Any:
            yield mock_response

        mock_llm_client.generate_stream_with_tools = mock_generate_stream

        # Set the task context
        task_execution_agent.set_current_task(sample_task_context)

        # Create a user message
        user_msg = UserMessage(session_id="test-session", content="Please execute the current task")

        # Collect messages from stream_chat
        messages = []
        async for msg in task_execution_agent.stream_chat(user_msg):
            messages.append(msg)

        # Verify we got at least one message
        assert len(messages) > 0
        # The agent should respond with some message
        agent_messages = [m for m in messages if isinstance(m, AgentMessage)]
        assert len(agent_messages) > 0

    @pytest.mark.asyncio
    async def test_stream_chat_task_execution_with_tools(
        self,
        task_execution_agent: TaskExecutionAgent,
        sample_task_context: TaskExecutionContext,
        mock_llm_client: MagicMock,
    ) -> None:
        """Test that stream_chat properly yields tool messages during task execution."""
        # The agent uses get_tool_executor() internally, we don't need to mock it for this test
        # since we're mocking the LLM responses directly

        # Mock the LLM response with tool calls
        mock_messages = [
            ToolCallMessage(
                agent_id="TASK_AGENT",
                session_id="test-session",
                tool_calls=[
                    ToolCallRequest(
                        tool_id="1", tool_name="read_file", tool_args={"path": "/tmp/test.txt"}
                    )
                ],
            ),
            AgentMessage(
                agent_id="TASK_AGENT",
                session_id="test-session",
                content="Task completed",
                final=True,
            ),
        ]

        async def mock_generate_stream(*args: Any, **kwargs: Any) -> Any:
            for msg in mock_messages:
                yield msg

        mock_llm_client.generate_stream_with_tools = mock_generate_stream

        # Set the task context
        task_execution_agent.set_current_task(sample_task_context)

        # Create a user message
        user_msg = UserMessage(session_id="test-session", content="Execute task")

        # Collect all messages
        messages = []
        async for msg in task_execution_agent.stream_chat(user_msg):
            messages.append(msg)

        # Verify message types
        assert any(isinstance(m, ToolCallMessage) for m in messages)
        assert any(isinstance(m, ToolResultMessage) for m in messages)
        assert any(isinstance(m, AgentMessage) for m in messages)

    @pytest.mark.asyncio
    async def test_task_prompt_substitution(
        self, task_execution_agent: TaskExecutionAgent, sample_task_context: TaskExecutionContext
    ) -> None:
        """Test that task prompts are properly substituted with parameter values."""
        # Set the task context
        task_execution_agent.set_current_task(sample_task_context)

        # Build the task prompt
        prompt = task_execution_agent.build_task_prompt(sample_task_context)

        # Verify the prompt contains the task info and values
        assert "Process File" in prompt  # task name
        assert "Read the file at {file_path}" in prompt  # original instructions
        assert "file_path: /tmp/test.txt" in prompt  # parameter value shown
        assert "max_length: 100" in prompt  # parameter value shown

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
            tool_call_id="test-complex-call-456",
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
