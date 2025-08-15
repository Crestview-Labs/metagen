"""Proper end-to-end tests for the task subsystem.

These tests mock only the LLM responses, allowing the rest of the system
(tool execution, message routing, database operations) to run normally.
"""

import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import patch

import pytest

from agents.agent_manager import AgentManager
from client.models import ModelID
from common.messages import (
    AgentMessage,
    ErrorMessage,
    Message,
    ThinkingMessage,
    ToolCallMessage,
    ToolCallRequest,
    ToolErrorMessage,
    ToolResultMessage,
    UserMessage,
)
from common.models import Parameter, TaskDefinition
from common.models.enums import ParameterType
from db.engine import DatabaseEngine

logger = logging.getLogger(__name__)


@pytest.fixture
async def test_db(tmp_path: Path) -> AsyncGenerator[DatabaseEngine, None]:
    """Create a test database for e2e tests."""
    db_path = tmp_path / "test_e2e.db"
    db_engine = DatabaseEngine(db_path)
    await db_engine.initialize()
    yield db_engine
    await db_engine.close()


@pytest.fixture
async def agent_manager(test_db: DatabaseEngine) -> AsyncGenerator[AgentManager, None]:
    """Create an agent manager for e2e tests."""
    manager = AgentManager(
        agent_name="TestAgent",
        db_engine=test_db,
        mcp_servers=[],  # No MCP servers for tests
        llm=ModelID.CLAUDE_SONNET_4,
    )

    yield manager

    # Cleanup
    await manager.cleanup()


class TestTaskSubsystemE2E:
    """E2E tests that mock only LLM responses, not agent behavior."""

    @pytest.mark.asyncio
    async def test_create_task_through_meta_agent(self, agent_manager: AgentManager) -> None:
        """Test task creation through the complete system flow."""
        # Initialize the agent manager
        await agent_manager.initialize()

        # Assert that agents are properly initialized
        assert agent_manager.meta_agent is not None
        assert agent_manager.meta_agent.llm_client is not None
        assert agent_manager.memory_manager is not None

        # Track the number of times generate_stream_with_tools is called
        call_count = 0

        # Mock the LLM response for MetaAgent
        async def mock_llm_stream(*args: Any, **kwargs: Any) -> AsyncGenerator[Message, None]:
            """Mock LLM to respond with task creation."""
            nonlocal call_count
            call_count += 1

            # Extract session_id from kwargs
            session_id = kwargs.get("session_id", "test-session")

            if call_count == 1:
                # First call: agent responds with text and tool call
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="I'll create a reusable task for analyzing CSV files and summaries.",
                    final=False,  # Not final yet, tool call coming
                )

                # Then it decides to call create_task tool
                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="call_001",
                            tool_name="create_task",
                            tool_args={
                                "task_definition": {
                                    "name": "CSV Analyzer",
                                    "description": "Analyze CSV files and generate summaries",
                                    "instructions": (
                                        "Read the CSV file at {file_path} and create a summary "
                                        "with max {max_words} words"
                                    ),
                                    "input_schema": [
                                        {
                                            "name": "file_path",
                                            "description": "Path to the CSV file",
                                            "type": "string",
                                            "required": True,
                                        },
                                        {
                                            "name": "max_words",
                                            "description": "Maximum words in summary",
                                            "type": "integer",
                                            "required": False,
                                            "default": 100,
                                        },
                                    ],
                                    "output_schema": [
                                        {
                                            "name": "summary",
                                            "description": "Generated summary",
                                            "type": "string",
                                            "required": True,
                                        }
                                    ],
                                    "task_type": "general",
                                }
                            },
                        )
                    ],
                )
            elif call_count == 2:
                # Second call: after tool execution, agent responds with confirmation
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content=(
                        "I've successfully created the CSV Analyzer task. This reusable task can "
                        "analyze CSV files and generate summaries with a configurable word limit."
                    ),
                    final=True,  # Final message after tool execution
                )

        # Patch the LLM client's generate_stream_with_tools method
        with patch.object(
            agent_manager.meta_agent.llm_client,
            "generate_stream_with_tools",
            side_effect=mock_llm_stream,
        ):
            # Send user message
            user_msg = UserMessage(
                session_id="test-session",
                content="I need to analyze CSV files and generate summaries",
            )

            # Collect all responses
            responses = []
            async for msg in agent_manager.chat_stream(user_msg):
                responses.append(msg)
                if isinstance(msg, ToolErrorMessage):
                    logger.debug(f"Tool Error: {msg.error}")
                elif isinstance(msg, ToolResultMessage):
                    logger.debug(f"Tool Result: {msg.result}")
                else:
                    msg_type = type(msg).__name__
                    msg_content = getattr(msg, "content", "no content")[:100]
                    logger.debug(f"Response: {msg_type} - {msg_content}")

        # Verify we got the expected message types
        message_types = [type(msg).__name__ for msg in responses]
        logger.debug(f"\nMessage types received: {message_types}")
        assert "AgentMessage" in message_types
        assert "ToolCallMessage" in message_types
        assert "ToolResultMessage" in message_types or "ToolErrorMessage" in message_types

        # Find the tool result
        tool_result = None
        for msg in responses:
            if isinstance(msg, ToolResultMessage) and msg.tool_name == "create_task":
                tool_result = msg.result
                break

        assert tool_result is not None, "Should have received create_task result"

        # Verify task was created in database
        # Tool result is a JSON string in ToolCallResult.content
        result_type = type(tool_result)
        assert isinstance(tool_result, str), f"Tool result should be string, got {result_type}"

        # Parse the JSON result
        result_data = json.loads(tool_result)
        assert isinstance(result_data, dict), "Parsed result should be a dict"

        task_id = result_data.get("task_id")
        assert task_id is not None, "Task ID should be in result"

        assert agent_manager.memory_manager is not None
        task = await agent_manager.memory_manager.get_task(task_id)
        assert task is not None
        assert task.name == "CSV Analyzer"
        assert len(task.definition.input_schema) == 2
        assert task.definition.input_schema[0].name == "file_path"

    @pytest.mark.asyncio
    async def test_execute_task_with_task_agent(self, agent_manager: AgentManager) -> None:
        """Test task execution through MetaAgent -> TaskExecutionAgent flow."""
        await agent_manager.initialize()

        # Assert that agents are properly initialized
        assert agent_manager.meta_agent is not None
        assert agent_manager.meta_agent.llm_client is not None
        assert agent_manager.task_agent is not None
        assert agent_manager.task_agent.llm_client is not None
        assert agent_manager.memory_manager is not None

        # First create a task
        from datetime import datetime

        from common.models import TaskConfig

        task_def = TaskDefinition(
            name="Test Executor",
            description="Simple test task",
            instructions="Echo the message: {message}",
            input_schema=[
                Parameter(
                    name="message",
                    description="The message to echo",
                    type=ParameterType.STRING,
                    required=True,
                )
            ],
            output_schema=[
                Parameter(
                    name="echo",
                    description="The echoed message",
                    type=ParameterType.STRING,
                    required=True,
                )
            ],
        )

        task_config = TaskConfig(
            id="test-executor-123",
            name=task_def.name,
            definition=task_def,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        assert agent_manager.memory_manager is not None
        await agent_manager.memory_manager.create_task(task_config)

        # Mock MetaAgent LLM response to execute task
        meta_call_count = 0

        async def mock_meta_llm_stream(*args: Any, **kwargs: Any) -> AsyncGenerator[Message, None]:
            nonlocal meta_call_count
            meta_call_count += 1

            # Extract session_id from kwargs
            session_id = kwargs.get("session_id", "test-session")

            if meta_call_count == 1:
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="I'll execute the Test Executor task with your message.",
                    final=False,
                )

                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="call_exec_001",
                            tool_name="execute_task",
                            tool_args={
                                "task_id": "test-executor-123",
                                "input_values": {"message": "Hello from test!"},
                            },
                        )
                    ],
                )
            elif meta_call_count == 2:
                # After task execution completes, this is called with tool results
                # The MetaAgent needs to respond after receiving the execute_task result
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content=(
                        "The Test Executor task has been executed successfully. "
                        "The task echoed your message: 'Hello from test!' as requested."
                    ),
                    final=True,
                )

        # Mock TaskExecutionAgent LLM response
        async def mock_task_llm_stream(*args: Any, **kwargs: Any) -> AsyncGenerator[Message, None]:
            yield AgentMessage(
                agent_id="TASK_EXECUTOR",
                session_id="test-session",
                content="Processing the echo task...",
                final=False,
            )

            yield AgentMessage(
                agent_id="TASK_EXECUTOR",
                session_id="test-session",
                content="Echoing message: Hello from test!",
                final=False,
            )

            # The final message content is what gets captured as the task result
            yield AgentMessage(
                agent_id="TASK_EXECUTOR",
                session_id="test-session",
                content="Task completed successfully. The echoed message is: Hello from test!",
                final=True,  # This is critical - marks the end of task execution
            )

        # Patch both agents' LLM clients
        with (
            patch.object(
                agent_manager.meta_agent.llm_client,
                "generate_stream_with_tools",
                side_effect=mock_meta_llm_stream,
            ),
            patch.object(
                agent_manager.task_agent.llm_client,
                "generate_stream_with_tools",
                side_effect=mock_task_llm_stream,
            ),
        ):
            # Send message to execute task
            user_msg = UserMessage(
                session_id="test-session",
                content="Execute the test task with message 'Hello from test!'",
            )

            responses = []
            async for msg in agent_manager.chat_stream(user_msg):
                responses.append(msg)
                if isinstance(msg, ErrorMessage):
                    logger.debug(f"Error: {msg.error}")
                elif isinstance(msg, ToolErrorMessage):
                    logger.debug(f"Tool Error: {msg.error}")
                elif isinstance(msg, ToolResultMessage):
                    logger.debug(f"Tool Result: {msg.result}")
                else:
                    msg_type = type(msg).__name__
                    msg_content = getattr(msg, "content", "no content")[:100]
                    logger.debug(f"Response: {msg_type} - {msg_content}")

        # Debug: print all messages
        logger.debug("\nAll messages:")
        for msg in responses:
            msg_type = type(msg).__name__
            agent_id = getattr(msg, "agent_id", "N/A")
            content = getattr(msg, "content", getattr(msg, "error", "no content"))[:100]
            logger.debug(f"  {msg_type}: {agent_id} - {content}")

        # Verify both agents participated
        agent_ids = set()
        for msg in responses:
            if isinstance(msg, (AgentMessage, ThinkingMessage)):
                agent_ids.add(msg.agent_id)

        assert "METAGEN" in agent_ids
        # TaskAgent's ThinkingMessage should be present (final AgentMessage is filtered by router)
        assert any(aid.startswith("TASK_AGENT") for aid in agent_ids)

        # Verify task execution happened
        assert any(
            isinstance(msg, AgentMessage) and "Hello from test!" in msg.content for msg in responses
        )

    @pytest.mark.asyncio
    async def test_task_creation_and_listing(self, agent_manager: AgentManager) -> None:
        """Test creating a task and then listing tasks."""
        await agent_manager.initialize()

        # Assert that agents are properly initialized
        assert agent_manager.meta_agent is not None
        assert agent_manager.meta_agent.llm_client is not None
        assert agent_manager.memory_manager is not None

        # Mock for task creation
        create_call_count = 0

        async def mock_create_llm_stream(
            *args: Any, **kwargs: Any
        ) -> AsyncGenerator[Message, None]:
            nonlocal create_call_count
            create_call_count += 1

            # Extract session_id from kwargs
            session_id = kwargs.get("session_id", "test-session")

            if create_call_count == 1:
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="I'll create a data processing task for you.",
                    final=False,
                )

                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="call_create",
                            tool_name="create_task",
                            tool_args={
                                "task_definition": {
                                    "name": "Data Processor",
                                    "description": "Process various data formats",
                                    "instructions": (
                                        "Process the data in {input_file} and output to "
                                        "{output_file}"
                                    ),
                                    "input_schema": [
                                        {
                                            "name": "input_file",
                                            "description": "Input file path",
                                            "type": "string",
                                            "required": True,
                                        },
                                        {
                                            "name": "output_file",
                                            "description": "Output file path",
                                            "type": "string",
                                            "required": True,
                                        },
                                    ],
                                    "output_schema": [
                                        {
                                            "name": "status",
                                            "description": "Processing status",
                                            "type": "string",
                                            "required": True,
                                        }
                                    ],
                                    "task_type": "general",
                                }
                            },
                        )
                    ],
                )
            elif create_call_count == 2:
                # After tool execution
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="I've successfully created the Data Processor task for you.",
                    final=True,
                )

        # Create task
        with patch.object(
            agent_manager.meta_agent.llm_client,
            "generate_stream_with_tools",
            side_effect=mock_create_llm_stream,
        ):
            responses = []
            async for msg in agent_manager.chat_stream(
                UserMessage(
                    session_id="test-session", content="Create a task for processing data files"
                )
            ):
                responses.append(msg)
                if isinstance(msg, ToolErrorMessage):
                    logger.debug(f"Tool Error: {msg.tool_name} - {msg.error}")
                else:
                    msg_type = type(msg).__name__
                    msg_content = getattr(msg, "content", getattr(msg, "tool_name", "no content"))[
                        :100
                    ]
                    logger.debug(f"Create Response: {msg_type} - {msg_content}")

        # Verify task was created
        task_created = False
        for msg in responses:
            if isinstance(msg, ToolResultMessage) and msg.tool_name == "create_task":
                # Parse JSON result
                import json

                result_data = json.loads(msg.result)
                if result_data.get("task_id") is not None:
                    task_created = True
                    break
        assert task_created

        # Now test listing tasks
        list_call_count = 0

        async def mock_list_llm_stream(*args: Any, **kwargs: Any) -> AsyncGenerator[Message, None]:
            nonlocal list_call_count
            list_call_count += 1

            # Extract session_id from kwargs
            session_id = kwargs.get("session_id", "test-session")

            if list_call_count == 1:
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="Let me list all available tasks for you.",
                    final=False,
                )

                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="call_list", tool_name="list_tasks", tool_args={"limit": 50}
                        )
                    ],
                )
            elif list_call_count == 2:
                # After tool execution
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content=(
                        "Here are the available tasks. I found the Data Processor task "
                        "that was just created."
                    ),
                    final=True,
                )

        # List tasks
        with patch.object(
            agent_manager.meta_agent.llm_client,
            "generate_stream_with_tools",
            side_effect=mock_list_llm_stream,
        ):
            list_responses = []
            async for msg in agent_manager.chat_stream(
                UserMessage(session_id="test-session", content="What tasks are available?")
            ):
                list_responses.append(msg)
                msg_type = type(msg).__name__
                msg_content = getattr(msg, "content", getattr(msg, "tool_name", "no content"))[:100]
                logger.debug(f"List Response: {msg_type} - {msg_content}")

        # Verify list_tasks was called and returned results
        list_result = None
        for msg in list_responses:
            if isinstance(msg, ToolResultMessage) and msg.tool_name == "list_tasks":
                list_result = msg.result
                break

        assert list_result is not None

        # Tool result is a JSON string, parse it
        import json

        result_data = json.loads(list_result)

        assert "tasks" in result_data
        assert len(result_data["tasks"]) > 0
        assert any(t["name"] == "Data Processor" for t in result_data["tasks"])

    @pytest.mark.asyncio
    async def test_task_parameter_validation(self, agent_manager: AgentManager) -> None:
        """Test parameter validation when executing tasks."""
        await agent_manager.initialize()

        # Assert that agents are properly initialized
        assert agent_manager.meta_agent is not None
        assert agent_manager.meta_agent.llm_client is not None
        assert agent_manager.memory_manager is not None

        # Create a task with required parameters
        from datetime import datetime

        from common.models import TaskConfig

        task_def = TaskDefinition(
            name="Strict Task",
            description="Task with required parameters",
            instructions="Process {required_param} with optional {optional_param}",
            input_schema=[
                Parameter(
                    name="required_param",
                    description="Required parameter",
                    type=ParameterType.STRING,
                    required=True,
                ),
                Parameter(
                    name="optional_param",
                    description="Optional parameter with default",
                    type=ParameterType.STRING,
                    required=False,
                    default="default",
                ),
            ],
            output_schema=[],
        )

        task_config = TaskConfig(
            id="strict-task-123",
            name=task_def.name,
            definition=task_def,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        assert agent_manager.memory_manager is not None
        await agent_manager.memory_manager.create_task(task_config)

        # Mock LLM to try executing without required params
        invalid_call_count = 0

        async def mock_invalid_llm_stream(
            *args: Any, **kwargs: Any
        ) -> AsyncGenerator[Message, None]:
            nonlocal invalid_call_count
            invalid_call_count += 1

            # Get session_id from kwargs if available
            session_id = kwargs.get("session_id", "test-session")

            if invalid_call_count == 1:
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="I'll execute the Strict Task.",
                    final=False,
                )

                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="call_invalid",
                            tool_name="execute_task",
                            tool_args={
                                "task_id": "strict-task-123",
                                "input_values": {},  # Missing required parameter
                            },
                        )
                    ],
                )
            else:
                # After getting error about missing params - always provide final message
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content=(
                        "I see that the Strict Task requires a 'required_param' parameter "
                        "that wasn't "
                        "provided. The task execution failed due to missing required parameters."
                    ),
                    final=True,
                )

        with patch.object(
            agent_manager.meta_agent.llm_client,
            "generate_stream_with_tools",
            side_effect=mock_invalid_llm_stream,
        ):
            responses = []
            async for msg in agent_manager.chat_stream(
                UserMessage(session_id="test-session", content="Execute the strict task")
            ):
                responses.append(msg)

        # Verify we got an error about missing parameters
        # Check for either ToolResultMessage or ToolErrorMessage for execute_task
        tool_error_messages = [
            msg
            for msg in responses
            if isinstance(msg, (ToolResultMessage, ToolErrorMessage))
            and getattr(msg, "tool_name", None) == "execute_task"
        ]

        assert len(tool_error_messages) > 0, (
            f"Expected ToolResultMessage or ToolErrorMessage for execute_task, got: "
            f"{[type(m).__name__ for m in responses]}"
        )

        # Verify the error mentions the missing parameter
        error_msg = tool_error_messages[0]
        if isinstance(error_msg, ToolErrorMessage):
            assert "required_param" in error_msg.error or "required" in error_msg.error.lower(), (
                f"Expected error to mention missing required parameter, got: {error_msg.error}"
            )

    @pytest.mark.asyncio
    async def test_concurrent_task_execution(self, agent_manager: AgentManager) -> None:
        """Test handling multiple task executions in sequence."""
        await agent_manager.initialize()

        # Assert that agents are properly initialized
        assert agent_manager.meta_agent is not None
        assert agent_manager.meta_agent.llm_client is not None
        assert agent_manager.task_agent is not None
        assert agent_manager.task_agent.llm_client is not None
        assert agent_manager.memory_manager is not None

        # Create multiple tasks
        from datetime import datetime

        from common.models import TaskConfig

        task_ids = []
        for i in range(3):
            task_def = TaskDefinition(
                name=f"Task {i + 1}",
                description=f"Test task {i + 1}",
                instructions=f"Process item {{item}} for task {i + 1}",
                input_schema=[
                    Parameter(
                        name="item",
                        description="Item to process",
                        type=ParameterType.STRING,
                        required=True,
                    )
                ],
                output_schema=[
                    Parameter(
                        name="result",
                        description="Processing result",
                        type=ParameterType.STRING,
                        required=True,
                    )
                ],
            )

            task_config = TaskConfig(
                id=f"task-{i + 1}",
                name=task_def.name,
                definition=task_def,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            assert agent_manager.memory_manager is not None
            await agent_manager.memory_manager.create_task(task_config)
            task_ids.append(task_config.id)

        # Mock MetaAgent to execute multiple tasks
        meta_multi_call_count = 0

        async def mock_multi_llm_stream(*args: Any, **kwargs: Any) -> AsyncGenerator[Message, None]:
            nonlocal meta_multi_call_count
            meta_multi_call_count += 1

            # Get session_id from kwargs if available
            session_id = kwargs.get("session_id", "test-session")

            logger.debug(f"DEBUG: meta_multi_call_count={meta_multi_call_count}")

            # Log what messages the LLM received
            messages = args[0] if args else kwargs.get("messages", [])
            logger.debug(f"DEBUG: MetaAgent LLM received {len(messages)} messages")
            for i, msg in enumerate(messages[-3:]):  # Show last 3 messages
                if hasattr(msg, "type"):
                    logger.debug(
                        f"  Message[{i}]: type={msg.type}, "
                        f"content={getattr(msg, 'content', 'N/A')[:50]}"
                    )

            if meta_multi_call_count == 1:
                # First call: execute first task
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="I'll execute all three tasks for you in order.",
                    final=False,
                )

                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="call_task_0",
                            tool_name="execute_task",
                            tool_args={"task_id": task_ids[0], "input_values": {"item": "Item 1"}},
                        )
                    ],
                )
            elif meta_multi_call_count == 2:
                # After first task result, execute second task
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="Task 1 completed. Now executing Task 2.",
                    final=False,
                )

                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="call_task_1",
                            tool_name="execute_task",
                            tool_args={"task_id": task_ids[1], "input_values": {"item": "Item 2"}},
                        )
                    ],
                )
            elif meta_multi_call_count == 3:
                # After second task result, execute third task
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="Task 2 completed. Now executing Task 3.",
                    final=False,
                )

                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="call_task_2",
                            tool_name="execute_task",
                            tool_args={"task_id": task_ids[2], "input_values": {"item": "Item 3"}},
                        )
                    ],
                )
            else:
                # After all tasks complete or any other call, send final summary
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content=(
                        f"Completed {meta_multi_call_count - 1} task(s). "
                        "All requested tasks have been processed."
                    ),
                    final=True,
                )

        # Mock TaskExecutionAgent responses
        task_execution_count = 0

        async def mock_task_exec_llm_stream(
            *args: Any, **kwargs: Any
        ) -> AsyncGenerator[Message, None]:
            nonlocal task_execution_count
            task_execution_count += 1
            current_task = task_execution_count

            # Get session_id from kwargs if available
            session_id = kwargs.get("session_id", "test-session")

            logger.debug(f"DEBUG: task_execution_count={task_execution_count}")

            yield AgentMessage(
                agent_id="TASK_EXECUTOR",
                session_id=session_id,
                content=f"Executing Task {current_task}...",
                final=False,
            )

            yield AgentMessage(
                agent_id="TASK_EXECUTOR",
                session_id=session_id,
                content=f"Processing Item {current_task} for Task {current_task}",
                final=False,
            )

            yield AgentMessage(
                agent_id="TASK_EXECUTOR",
                session_id=session_id,
                content=(
                    f"Task {current_task} completed successfully! "
                    f"Result: Processed Item {current_task}"
                ),
                final=True,  # Mark as final for proper task completion
            )

        with (
            patch.object(
                agent_manager.meta_agent.llm_client,
                "generate_stream_with_tools",
                side_effect=mock_multi_llm_stream,
            ),
            patch.object(
                agent_manager.task_agent.llm_client,
                "generate_stream_with_tools",
                side_effect=mock_task_exec_llm_stream,
            ),
        ):
            responses = []
            async for msg in agent_manager.chat_stream(
                UserMessage(session_id="test-session", content="Execute all three tasks")
            ):
                responses.append(msg)
                msg_type = type(msg).__name__
                agent_id = getattr(msg, "agent_id", "N/A")
                is_final = getattr(msg, "final", "N/A")
                tool_name = getattr(msg, "tool_name", "N/A")

                if msg_type in ["ToolResultMessage", "ToolErrorMessage", "ToolStartedMessage"]:
                    logger.debug(f"DEBUG: {msg_type}, agent_id={agent_id}, tool={tool_name}")
                elif msg_type == "AgentMessage" and is_final:
                    logger.debug(f"DEBUG: FINAL {msg_type}, agent_id={agent_id}")
                elif msg_type == "ToolCallMessage":
                    tool_calls = getattr(msg, "tool_calls", [])
                    logger.debug(
                        f"DEBUG: {msg_type}, agent_id={agent_id}, num_tools={len(tool_calls)}"
                    )

        # Verify all tasks were executed
        assert task_execution_count == 3

        # Verify we got responses from task execution (now as ToolResultMessages)
        tool_result_messages = [
            msg
            for msg in responses
            if isinstance(msg, ToolResultMessage) and msg.tool_name == "execute_task"
        ]

        # Debug: print all tool result messages
        logger.debug(f"\nDEBUG: Found {len(tool_result_messages)} ToolResultMessages:")
        for idx, msg in enumerate(tool_result_messages):
            logger.debug(f"  [{idx}] tool_id={msg.tool_id}, result={msg.result[:100]}...")

        assert len(tool_result_messages) >= 3, (
            f"Expected at least 3 ToolResultMessages, got {len(tool_result_messages)}"
        )

        # Verify FIFO order (tasks completed in order)
        # Check that we have results from all 3 tasks
        all_results = " ".join(msg.result for msg in tool_result_messages)
        for i in range(1, 4):
            assert f"Task {i}" in all_results, (
                f"Task {i} not found in combined results: {all_results}"
            )


class TestTaskSubsystemRealLLM:
    """E2E tests with real LLM for true end-to-end validation."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_task_through_meta_agent_real_llm(
        self, agent_manager: AgentManager
    ) -> None:
        """Test task creation through the complete system flow with real LLM."""
        # Skip if no API key
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")

        await agent_manager.initialize()

        # Send user message asking to create a task
        user_msg = UserMessage(
            session_id="test-session",
            content=(
                "Create a reusable task called 'CSV Analyzer' that takes a file_path parameter "
                "(required) and max_words parameter (optional, default 100). It should analyze "
                "CSV files and generate summaries."
            ),
        )

        # Collect all responses
        responses = []
        async for msg in agent_manager.chat_stream(user_msg):
            responses.append(msg)

        # Verify task creation happened
        tool_result = None
        for msg in responses:
            if isinstance(msg, ToolResultMessage) and msg.tool_name == "create_task":
                tool_result = msg.result
                break

        assert tool_result is not None, "Should have received create_task result"

        # Parse the JSON result
        result_data = json.loads(tool_result)
        task_id = result_data.get("task_id")
        assert task_id is not None, "Task ID should be in result"

        # Verify task was created in database
        assert agent_manager.memory_manager is not None
        task = await agent_manager.memory_manager.get_task(task_id)
        assert task is not None
        assert task.name == "CSV Analyzer"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_execute_task_with_task_agent_real_llm(self, agent_manager: AgentManager) -> None:
        """Test task execution through MetaAgent -> TaskExecutionAgent flow with real LLM."""
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")

        await agent_manager.initialize()

        # First, ask LLM to create an echo task
        create_responses = []
        async for msg in agent_manager.chat_stream(
            UserMessage(
                session_id="test-session",
                content=(
                    "Create a task called 'Echo Task' that takes a message parameter and "
                    "echoes it back. The task should simply repeat whatever message is provided."
                ),
            )
        ):
            create_responses.append(msg)
            msg_type = type(msg).__name__
            msg_content = getattr(msg, "content", "no content")[:100]
            logger.debug(f"Create Response: {msg_type} - {msg_content}")

        # Verify task was created
        task_created = False
        for msg in create_responses:
            if isinstance(msg, ToolResultMessage) and msg.tool_name == "create_task":
                task_created = True
                break
        assert task_created, "Echo Task should have been created"

        # Now ask LLM to execute the task
        exec_responses = []
        async for msg in agent_manager.chat_stream(
            UserMessage(
                agent_id="METAGEN",
                session_id="test-session",
                content="Execute the Echo Task with the message 'Hello from real LLM test!'",
            )
        ):
            exec_responses.append(msg)
            msg_type = type(msg).__name__
            msg_content = getattr(msg, "content", "no content")[:100]
            logger.debug(f"Exec Response: {msg_type} - {msg_content}")

        # Verify task was executed
        assert any(
            isinstance(msg, ToolCallMessage)
            and any(tc.tool_name == "execute_task" for tc in msg.tool_calls)
            for msg in exec_responses
        )

        # Verify both agents participated
        agent_ids = set()
        for msg in exec_responses:
            if isinstance(msg, AgentMessage):
                agent_ids.add(msg.agent_id)

        assert "METAGEN" in agent_ids
        assert any(aid.startswith("TASK_AGENT") for aid in agent_ids)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_task_creation_and_listing_real_llm(self, agent_manager: AgentManager) -> None:
        """Test creating a task and then listing tasks with real LLM."""
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")

        await agent_manager.initialize()

        # Create task
        create_responses = []
        async for msg in agent_manager.chat_stream(
            UserMessage(
                session_id="test-session",
                content=(
                    "Create a task called 'Data Processor' that processes data files. "
                    "It should take input_file and output_file parameters (both required strings) "
                    "and return a status string."
                ),
            )
        ):
            create_responses.append(msg)
            msg_type = type(msg).__name__
            msg_content = getattr(msg, "content", "no content")[:100]
            logger.debug(f"Create Response: {msg_type} - {msg_content}")

        # Verify task was created
        task_created = False
        for msg in create_responses:
            if isinstance(msg, ToolResultMessage) and msg.tool_name == "create_task":
                task_created = True
                break
        assert task_created

        # Now list tasks
        list_responses = []
        async for msg in agent_manager.chat_stream(
            UserMessage(session_id="test-session", content="List all available tasks")
        ):
            list_responses.append(msg)
            msg_type = type(msg).__name__
            msg_content = getattr(msg, "content", "no content")[:100]
            logger.debug(f"List Response: {msg_type} - {msg_content}")

        # Verify list_tasks was called
        list_result = None
        for msg in list_responses:
            if isinstance(msg, ToolResultMessage) and msg.tool_name == "list_tasks":
                list_result = msg.result
                break

        assert list_result is not None

        # Parse and verify results
        result_data = json.loads(list_result)
        assert "tasks" in result_data
        assert len(result_data["tasks"]) > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_task_parameter_validation_real_llm(self, agent_manager: AgentManager) -> None:
        """Test parameter validation when executing tasks with real LLM."""
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")

        await agent_manager.initialize()

        # First create a task with required parameters
        create_responses = []
        async for msg in agent_manager.chat_stream(
            UserMessage(
                session_id="test-session",
                content=(
                    "Create a task called 'Validation Test Task' that requires a 'required_param' "
                    "parameter and has an optional 'optional_param' parameter with default value "
                    "'default_value'."
                ),
            )
        ):
            create_responses.append(msg)
            msg_type = type(msg).__name__
            msg_content = getattr(msg, "content", "no content")[:100]
            logger.debug(f"Create Response: {msg_type} - {msg_content}")

        # Verify task was created
        task_created = False
        for msg in create_responses:
            if isinstance(msg, ToolResultMessage) and msg.tool_name == "create_task":
                task_created = True
                break
        assert task_created

        # Try to execute without providing required params
        exec_responses = []
        async for msg in agent_manager.chat_stream(
            UserMessage(session_id="test-session", content="Execute the Validation Test Task")
        ):
            exec_responses.append(msg)
            msg_type = type(msg).__name__
            msg_content = getattr(msg, "content", "no content")[:100]
            logger.debug(f"Response: {msg_type} - {msg_content}")

        # Check if the agent recognized the missing parameter
        # The agent should either:
        # 1. Ask for the missing parameter
        # 2. Get an error from the tool about missing parameters
        agent_messages = [msg for msg in exec_responses if isinstance(msg, AgentMessage)]
        assert any(
            "required_param" in msg.content.lower()
            or "required parameter" in msg.content.lower()
            or "missing" in msg.content.lower()
            or "need" in msg.content.lower()
            for msg in agent_messages
        )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_task_execution_real_llm(self, agent_manager: AgentManager) -> None:
        """Test handling multiple task executions in sequence with real LLM."""
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")

        await agent_manager.initialize()

        # Create multiple simple tasks via chat
        for i in range(3):
            create_responses = []
            async for msg in agent_manager.chat_stream(
                UserMessage(
                    agent_id="METAGEN",
                    session_id="test-session",
                    content=(
                        f"Create a task called 'Simple Task {i + 1}' that processes an item "
                        f"parameter and responds with 'Processed [item] in task {i + 1}'."
                    ),
                )
            ):
                create_responses.append(msg)

            # Verify task was created
            assert any(
                isinstance(msg, ToolResultMessage) and msg.tool_name == "create_task"
                for msg in create_responses
            )

        # Execute all tasks
        exec_responses = []
        async for msg in agent_manager.chat_stream(
            UserMessage(
                session_id="test-session",
                content=(
                    "Execute all three Simple Tasks in order. For Simple Task 1 use item='Apple', "
                    "for Simple Task 2 use item='Banana', and for Simple Task 3 use item='Cherry'."
                ),
            )
        ):
            exec_responses.append(msg)
            msg_type = type(msg).__name__
            msg_content = getattr(msg, "content", "no content")[:100]
            logger.debug(f"Response: {msg_type} - {msg_content}")

        # Count execute_task tool calls
        tool_calls = []
        for msg in exec_responses:
            if isinstance(msg, ToolCallMessage):
                for tc in msg.tool_calls:
                    if tc.tool_name == "execute_task":
                        tool_calls.append(tc)

        # Should have at least 3 execute_task calls
        tool_call_count = len(tool_calls)
        assert tool_call_count >= 3, (
            f"Expected at least 3 execute_task calls, got {tool_call_count}"
        )

        # Verify we got responses from task execution
        task_agent_messages = [
            msg
            for msg in exec_responses
            if isinstance(msg, AgentMessage) and msg.agent_id.startswith("TASK_AGENT")
        ]
        assert len(task_agent_messages) > 0

        # Check that items were processed
        all_content = " ".join(
            msg.content for msg in exec_responses if isinstance(msg, AgentMessage)
        )
        assert "Apple" in all_content
        assert "Banana" in all_content
        assert "Cherry" in all_content

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_complete_flow_with_real_llm(self, agent_manager: AgentManager) -> None:
        """Test complete task flow with real LLM decisions - create and execute complex task."""
        # Skip if no API key
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")

        await agent_manager.initialize()

        # First, create a task
        responses = []
        async for msg in agent_manager.chat_stream(
            UserMessage(
                session_id="test-session",
                content=(
                    "Create a task called 'Code Analyzer' that takes a file_path parameter "
                    "and returns code metrics like lines of code, number of functions, "
                    "and complexity"
                ),
            )
        ):
            responses.append(msg)
            logger.debug(f"Response: {type(msg).__name__} - {getattr(msg, 'content', '')[:100]}")

        # Find the created task ID
        task_id = None
        for msg in responses:
            if isinstance(msg, ToolResultMessage) and msg.tool_name == "create_task":
                # Parse JSON result
                import json

                result_data = json.loads(msg.result)
                task_id = result_data.get("task_id")
                break

        assert task_id is not None, "Task should have been created"

        # Now execute the task
        exec_responses = []
        async for msg in agent_manager.chat_stream(
            UserMessage(
                session_id="test-session",
                content="Use the Code Analyzer task to analyze a file at /example/test.py",
            )
        ):
            exec_responses.append(msg)
            msg_type = type(msg).__name__
            msg_content = getattr(msg, "content", "")[:100]
            logger.debug(f"Exec Response: {msg_type} - {msg_content}")

        # Verify task was executed
        assert any(
            isinstance(msg, ToolCallMessage)
            and any(tc.tool_name == "execute_task" for tc in msg.tool_calls)
            for msg in exec_responses
        )

        # Verify both agents participated
        agent_ids = set()
        for msg in exec_responses:
            if isinstance(msg, AgentMessage):
                agent_ids.add(msg.agent_id)

        assert "METAGEN" in agent_ids
        assert any(aid.startswith("TASK_AGENT") for aid in agent_ids)
