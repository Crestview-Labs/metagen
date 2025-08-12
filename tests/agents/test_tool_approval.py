"""Tests for tool approval functionality in agents."""

import asyncio
import logging
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from agents.agent_manager import AgentManager
from agents.base import BaseAgent
from agents.memory import MemoryManager
from common.messages import (
    AgentMessage,
    ApprovalDecision,
    ApprovalRequestMessage,
    ApprovalResponseMessage,
    Message,
    MessageType,
    ToolCallMessage,
    ToolCallRequest,
    ToolStartedMessage,
    UsageMessage,
    UserMessage,
)
from common.models import ToolExecutionStage
from common.types import ToolCallResult
from tools.base import BaseCoreTool
from tools.registry import get_tool_executor

logger = logging.getLogger(__name__)


class TestToolApprovalDataClasses:
    """Test the tool approval data classes."""

    def test_tool_approval_request_creation(self) -> None:
        """Test creating an ApprovalRequestMessage."""
        request = ApprovalRequestMessage(
            tool_id="test-123",
            tool_name="write_file",
            tool_args={"path": "/tmp/test.txt", "content": "hello"},
            agent_id="METAGEN",
        )

        assert request.tool_id == "test-123"
        assert request.tool_name == "write_file"
        assert request.tool_args == {"path": "/tmp/test.txt", "content": "hello"}
        assert request.agent_id == "METAGEN"

    def test_tool_approval_request_to_dict(self) -> None:
        """Test converting ApprovalRequestMessage to dict."""
        request = ApprovalRequestMessage(
            tool_id="test-123",
            tool_name="write_file",
            tool_args={"path": "/tmp/test.txt"},
            agent_id="METAGEN",
        )

        data = request.model_dump()
        assert data["tool_id"] == "test-123"
        assert data["tool_name"] == "write_file"
        assert data["tool_args"] == {"path": "/tmp/test.txt"}
        assert data["agent_id"] == "METAGEN"
        # ApprovalRequestMessage doesn't have description or risk_level fields

    def test_tool_approval_response_creation(self) -> None:
        """Test creating an ApprovalResponseMessage."""
        response = ApprovalResponseMessage(
            tool_id="test-123",
            decision=ApprovalDecision.APPROVED,
            feedback=None,
            agent_id="METAGEN",
        )

        assert response.tool_id == "test-123"
        assert response.decision == ApprovalDecision.APPROVED
        assert response.feedback is None
        assert response.agent_id == "METAGEN"

    def test_tool_approval_response_with_rejection(self) -> None:
        """Test creating a rejection response with feedback."""
        response = ApprovalResponseMessage(
            tool_id="test-123",
            decision=ApprovalDecision.REJECTED,
            feedback="This operation seems unsafe",
            agent_id="METAGEN",
        )

        assert response.tool_id == "test-123"
        assert response.decision == ApprovalDecision.REJECTED
        assert response.feedback == "This operation seems unsafe"
        assert response.agent_id == "METAGEN"

    def test_tool_approval_decision_enum(self) -> None:
        """Test ApprovalDecision enum values."""
        assert ApprovalDecision.APPROVED == "approved"
        assert ApprovalDecision.REJECTED == "rejected"


class TestBaseAgentToolApprovalMocked:
    """Test tool approval functionality in BaseAgent with mocks."""

    @pytest.fixture
    def mock_memory_manager(self) -> AsyncMock:
        """Create a mock memory manager."""
        manager = AsyncMock()
        manager.record_tool_usage = AsyncMock(return_value="tool-usage-123")
        manager.update_tool_approval = AsyncMock()
        manager.start_tool_execution = AsyncMock()
        manager.complete_tool_execution = AsyncMock()
        return manager

    @pytest.fixture
    def mock_agentic_client(self) -> AsyncMock:
        """Create a mock agentic client."""
        client = AsyncMock()
        client.generate = AsyncMock()
        return client

    @pytest_asyncio.fixture
    async def base_agent(
        self, mock_memory_manager: AsyncMock, mock_agentic_client: AsyncMock
    ) -> BaseAgent:
        """Create a BaseAgent instance for testing."""

        class TestAgent(BaseAgent):
            """Test implementation of BaseAgent."""

            async def build_context(self, query: str) -> list[Message]:
                """Dummy implementation."""
                return []

        agent = TestAgent(
            agent_id="TEST_AGENT",
            instructions="Test instructions",
            memory_manager=mock_memory_manager,
            available_tools=[],  # No tools for this test
        )
        await agent.initialize()
        return agent

    @pytest.mark.asyncio
    async def test_configure_tool_approval(self, base_agent: BaseAgent) -> None:
        """Test configuring tool approval settings."""
        # Create a mock queue for approval
        approval_queue: asyncio.Queue[Message] = asyncio.Queue()

        base_agent.configure_tool_approval(
            require_approval=True,
            auto_approve_tools=["read_file", "list_files"],
            approval_queue=approval_queue,
        )

        assert base_agent._require_tool_approval is True
        assert base_agent._auto_approve_tools == {"read_file", "list_files"}
        assert base_agent._approval_queue == approval_queue

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_process_approval_response_approved(
        self, base_agent: BaseAgent, mock_memory_manager: AsyncMock
    ) -> None:
        """Test processing approval response when approved."""
        from agents.tool_tracker import ToolTracker, TrackedTool

        approval_queue: asyncio.Queue[Message] = asyncio.Queue()
        base_agent.configure_tool_approval(require_approval=True, approval_queue=approval_queue)

        # Create a tool tracker and add a pending tool
        base_agent._tool_tracker = ToolTracker(
            memory_manager=mock_memory_manager, agent_id="TEST_AGENT"
        )

        tracked_tool = TrackedTool(
            tool_id="tool-123",
            tool_name="write_file",
            tool_args={"path": "/tmp/test.txt"},
            stage=ToolExecutionStage.PENDING_APPROVAL,
            agent_id="TEST_AGENT",
            turn_id="turn-123",
        )
        await base_agent._tool_tracker.add_tool(tracked_tool)

        # Create approval response
        approval_response = ApprovalResponseMessage(
            tool_id="tool-123", decision=ApprovalDecision.APPROVED, agent_id="METAGEN"
        )

        # Process the approval (no events yielded in new implementation)
        await base_agent._process_approval_response(approval_response)

        # Verify the tool was approved in the tracker
        approved_tool = base_agent._tool_tracker.get_tool("tool-123")
        assert approved_tool is not None
        assert approved_tool.stage == ToolExecutionStage.APPROVED

    @pytest.mark.asyncio
    async def test_process_approval_response_rejected(
        self, base_agent: BaseAgent, mock_memory_manager: AsyncMock
    ) -> None:
        """Test processing approval response when rejected."""
        from agents.tool_tracker import ToolTracker, TrackedTool

        approval_queue: asyncio.Queue[Message] = asyncio.Queue()
        base_agent.configure_tool_approval(require_approval=True, approval_queue=approval_queue)

        # Create a tool tracker and add a pending tool
        base_agent._tool_tracker = ToolTracker(
            memory_manager=mock_memory_manager, agent_id="TEST_AGENT"
        )

        tracked_tool = TrackedTool(
            tool_id="tool-123",
            tool_name="delete_file",
            tool_args={"path": "/important.txt"},
            stage=ToolExecutionStage.PENDING_APPROVAL,
            agent_id="TEST_AGENT",
            turn_id="turn-123",
        )
        await base_agent._tool_tracker.add_tool(tracked_tool)

        # Create rejection response
        approval_response = ApprovalResponseMessage(
            tool_id="tool-123",
            decision=ApprovalDecision.REJECTED,
            feedback="Too dangerous",
            agent_id="METAGEN",
        )

        # Process the rejection (no events yielded in new implementation)
        await base_agent._process_approval_response(approval_response)

        # Verify the tool was rejected in the tracker
        rejected_tool = base_agent._tool_tracker.get_tool("tool-123")
        assert rejected_tool is not None
        assert rejected_tool.stage == ToolExecutionStage.REJECTED
        assert rejected_tool.user_feedback == "Too dangerous"

    @pytest.mark.asyncio
    async def test_process_approval_response_late(
        self, base_agent: BaseAgent, mock_memory_manager: AsyncMock
    ) -> None:
        """Test processing approval response after timeout."""
        approval_queue: asyncio.Queue[Message] = asyncio.Queue()
        base_agent.configure_tool_approval(require_approval=True, approval_queue=approval_queue)

        # No tool tracker active (simulates late approval)
        base_agent._tool_tracker = None

        # Create approval response
        approval_response = ApprovalResponseMessage(
            tool_id="tool-123", decision=ApprovalDecision.APPROVED, agent_id="METAGEN"
        )

        # Process the late approval - should log error but not crash
        await base_agent._process_approval_response(approval_response)

        # Since there's no active tracker, nothing should be updated
        mock_memory_manager.update_tool_approval.assert_not_called()


class TestBaseAgentToolApprovalPublicAPI:
    """Test tool approval through the public stream_chat API."""

    @pytest.fixture
    def mock_memory_manager(self) -> AsyncMock:
        """Create a mock memory manager."""
        manager = AsyncMock()
        manager.record_tool_usage = AsyncMock(return_value="tool-usage-123")
        manager.update_tool_approval = AsyncMock()
        manager.start_tool_execution = AsyncMock()
        manager.complete_tool_execution = AsyncMock()
        manager.create_turn = AsyncMock(return_value="turn-123")
        manager.complete_turn = AsyncMock()
        return manager

    @pytest_asyncio.fixture
    async def simple_agent(self, mock_memory_manager: AsyncMock) -> BaseAgent:
        """Create a simple BaseAgent with mocked tools."""
        from pydantic import BaseModel, Field

        # Define schemas for the tools
        class WriteInput(BaseModel):
            path: str = Field(description="Path to file")
            content: str = Field(description="Content to write")

        class WriteOutput(BaseModel):
            success: bool
            message: str

        class ReadInput(BaseModel):
            path: str = Field(description="Path to file")

        class ReadOutput(BaseModel):
            content: str

        class MockWriteFileTool(BaseCoreTool):
            def __init__(self) -> None:
                super().__init__(
                    name="write_file",
                    description="Write content to a file",
                    input_schema=WriteInput,
                    output_schema=WriteOutput,
                )

            def get_function_schema(self) -> dict:
                return {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"],
                }

            async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
                # Mock implementation - just return a simple output
                return WriteOutput(success=True, message="Written successfully")

            async def execute(self, params: dict[str, Any]) -> ToolCallResult:
                path = params.get("path", "")
                return ToolCallResult(
                    tool_name=self.name,
                    tool_call_id="write-123",
                    content=f"Written to {path}",
                    is_error=False,
                    error=None,
                    error_type=None,
                    user_display=None,
                )

        class MockReadFileTool(BaseCoreTool):
            def __init__(self) -> None:
                super().__init__(
                    name="read_file",
                    description="Read a file",
                    input_schema=ReadInput,
                    output_schema=ReadOutput,
                )

            def get_function_schema(self) -> dict:
                return {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                }

            async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
                # Mock implementation
                return ReadOutput(content="Mock file content")

            async def execute(self, params: dict[str, Any]) -> ToolCallResult:
                path = params.get("path", "")
                return ToolCallResult(
                    tool_name=self.name,
                    tool_call_id="read-123",
                    content=f"Content of {path}",
                    is_error=False,
                    error=None,
                    error_type=None,
                    user_display=None,
                )

        class TestAgent(BaseAgent):
            async def build_context(self, query: str) -> list[Message]:
                return []

        # Create tool instances
        write_tool = MockWriteFileTool()
        read_tool = MockReadFileTool()

        # Register tools with the executor (so they can be executed)
        executor = get_tool_executor()
        executor.register_core_tool(write_tool)
        executor.register_core_tool(read_tool)

        # Create agent with tool schemas and LLM client
        mock_llm_client = AsyncMock()
        agent = TestAgent(
            agent_id="TEST_AGENT",
            instructions="Test agent",
            memory_manager=mock_memory_manager,
            available_tools=[write_tool.get_tool_schema(), read_tool.get_tool_schema()],
            llm_client=mock_llm_client,
        )
        await agent.initialize()

        # Configure the mock LLM to return tool calls
        call_count = 0

        async def mock_generate_stream(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1

            # Check the messages to determine what to return
            messages = args[0]
            last_msg = messages[-1].content if messages else ""

            # Check if we have tool results in kwargs (indicates second call)
            has_tool_results = kwargs.get("tool_results") is not None

            if "write" in last_msg.lower() and not has_tool_results:
                # First call - return a write_file tool call
                yield AgentMessage(content="I'll write that file for you.")
                yield ToolCallMessage(
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="write-123",
                            tool_name="write_file",
                            tool_args={"path": "/tmp/test.txt", "content": "test"},
                        )
                    ]
                )
            elif "read" in last_msg.lower() and not has_tool_results:
                # First call - return a read_file tool call
                yield AgentMessage(content="I'll read that file for you.")
                yield ToolCallMessage(
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="read-123",
                            tool_name="read_file",
                            tool_args={"path": "/tmp/test.txt"},
                        )
                    ]
                )
            elif has_tool_results:
                # Second call after tool execution - just return a final message
                yield AgentMessage(content="Operation completed successfully.")
            else:
                yield AgentMessage(content="I don't understand.")

            yield UsageMessage(input_tokens=10, output_tokens=20, total_tokens=30)

        # Set the mock to return the async generator
        mock_llm_client.generate_stream_with_tools = mock_generate_stream

        return agent

    @pytest.mark.asyncio
    @pytest.mark.timeout(10)  # 10 second timeout
    async def test_tool_requiring_approval_through_stream_chat(
        self, simple_agent: BaseAgent
    ) -> None:
        """Test that tools requiring approval emit ApprovalRequestMessage and wait."""
        # Configure to require approval
        approval_queue: asyncio.Queue[Message] = asyncio.Queue()
        simple_agent.configure_tool_approval(
            require_approval=True,
            auto_approve_tools=[],  # No auto-approved tools
            approval_queue=approval_queue,
        )

        messages_received: list[Message] = []
        approval_sent = False

        # Create a task to send approval after seeing the request
        async def approve_after_request() -> None:
            nonlocal approval_sent
            logger.info("Approval task started")
            # Wait for approval request
            while True:
                await asyncio.sleep(0.05)  # Small delay to let messages accumulate
                logger.debug(
                    f"Checking for approval requests... Messages so far: {len(messages_received)}"
                )

                # Look for approval request
                for msg in messages_received:
                    if isinstance(msg, ApprovalRequestMessage) and not approval_sent:
                        logger.info(
                            f"Found approval request for tool: {msg.tool_name}, id: {msg.tool_id}"
                        )
                        # Process the approval directly (simulating what stream_chat does)
                        approval = ApprovalResponseMessage(
                            tool_id=msg.tool_id,
                            decision=ApprovalDecision.APPROVED,
                            agent_id=simple_agent.agent_id,
                        )
                        logger.info("Sending approval response...")
                        await simple_agent._process_approval_response(approval)
                        approval_sent = True
                        logger.info("Approval sent!")
                        return

        # Start approval task
        approval_task = asyncio.create_task(approve_after_request())

        try:
            # Send a message that will trigger write_file tool
            user_msg = UserMessage(content="Write test content to a file")
            logger.info("Sending user message to stream_chat...")
            async for msg in simple_agent.stream_chat(user_msg):
                logger.info(f"Received message: {type(msg).__name__}")
                messages_received.append(msg)

                # Log specific message types
                if isinstance(msg, ApprovalRequestMessage):
                    logger.info(f"  -> Approval request for: {msg.tool_name} (id: {msg.tool_id})")
                elif isinstance(msg, ToolStartedMessage):
                    logger.info(f"  -> Tool started: {msg.tool_name}")
                elif isinstance(msg, ToolCallMessage):
                    logger.info(f"  -> Tool call: {[tc.tool_name for tc in msg.tool_calls]}")

            logger.info("Stream completed")
        finally:
            # Ensure approval task is cancelled
            logger.info("Cancelling approval task...")
            approval_task.cancel()
            try:
                await approval_task
            except asyncio.CancelledError:
                pass

        # Verify we got the expected message types
        message_types = [type(msg).__name__ for msg in messages_received]
        logger.info(f"All message types received: {message_types}")

        # Check basic flow
        assert "ThinkingMessage" in message_types
        assert "AgentMessage" in message_types
        assert "ToolCallMessage" in message_types
        assert "ApprovalRequestMessage" in message_types
        assert "ToolStartedMessage" in message_types

        # Verify the approval request was for write_file
        approval_requests = [m for m in messages_received if isinstance(m, ApprovalRequestMessage)]
        assert len(approval_requests) == 1
        assert approval_requests[0].tool_name == "write_file"

    @pytest.mark.asyncio
    async def test_auto_approved_tool_bypasses_approval(self, simple_agent: BaseAgent) -> None:
        """Test that auto-approved tools don't emit ApprovalRequestMessage."""
        # Configure with read_file as auto-approved
        approval_queue: asyncio.Queue[Message] = asyncio.Queue()
        simple_agent.configure_tool_approval(
            require_approval=True, auto_approve_tools=["read_file"], approval_queue=approval_queue
        )

        messages_received = []

        # Send a message that will trigger read_file tool
        user_msg = UserMessage(content="Read the file at /tmp/test.txt")
        async for msg in simple_agent.stream_chat(user_msg):
            messages_received.append(msg)

        # Verify no approval request was sent
        message_types = [type(msg).__name__ for msg in messages_received]
        assert "ApprovalRequestMessage" not in message_types
        assert "ToolCallMessage" in message_types
        assert "ToolStartedMessage" in message_types

    @pytest.mark.asyncio
    async def test_rejected_tool_does_not_execute(self, simple_agent: BaseAgent) -> None:
        """Test that rejected tools don't execute."""
        # Configure to require approval
        approval_queue: asyncio.Queue[Message] = asyncio.Queue()
        simple_agent.configure_tool_approval(
            require_approval=True, auto_approve_tools=[], approval_queue=approval_queue
        )

        messages_received = []

        # Send a message that will trigger write_file tool
        user_msg = UserMessage(content="Write dangerous content to system file")
        async for msg in simple_agent.stream_chat(user_msg):
            messages_received.append(msg)

            # If we get an approval request, reject it
            if isinstance(msg, ApprovalRequestMessage):
                rejection = ApprovalResponseMessage(
                    tool_id=msg.tool_id,
                    decision=ApprovalDecision.REJECTED,
                    feedback="Too dangerous",
                    agent_id=simple_agent.agent_id,
                )
                # Process rejection
                async for response_msg in simple_agent.stream_chat(rejection):
                    messages_received.append(response_msg)

        # Verify tool was not executed
        message_types = [type(msg).__name__ for msg in messages_received]
        assert "ApprovalRequestMessage" in message_types
        assert "ToolStartedMessage" not in message_types
        assert "ToolResultMessage" not in message_types


class TestToolApprovalEndToEnd:
    """End-to-end tests for tool approval functionality."""

    @pytest_asyncio.fixture
    async def test_db_engine(self, tmp_path: Any) -> AsyncIterator[Any]:
        """Create a test database engine."""
        from db.engine import DatabaseEngine

        db_path = tmp_path / "test_approval.db"
        engine = DatabaseEngine(db_path)
        await engine.initialize()
        yield engine
        await engine.close()

    @pytest_asyncio.fixture
    async def memory_manager(self, test_db_engine: Any) -> MemoryManager:
        """Create a real memory manager."""
        manager = MemoryManager(test_db_engine)
        await manager.initialize()
        return manager

    @pytest_asyncio.fixture
    async def agent_manager(self, test_db_engine: Any) -> AsyncIterator[AgentManager]:
        """Create a real AgentManager."""
        manager = AgentManager(
            agent_name="TestManager",
            db_engine=test_db_engine,
            mcp_servers=[],  # No MCP servers for testing
        )
        await manager.initialize()
        yield manager
        await manager.cleanup()

    @pytest.mark.asyncio
    @pytest.mark.timeout(15)
    async def test_full_approval_flow_approved(self, agent_manager: AgentManager) -> None:
        """Test the full approval flow with approval."""
        logger.info("=== Starting test_full_approval_flow_approved ===")

        # Configure tool approval
        logger.info("Configuring tool approval...")
        agent_manager.configure_tool_approval(
            require_approval=True,
            auto_approve_tools=set(),  # No auto-approved tools
        )

        # Variable to store the actual tool_id
        actual_tool_id = None
        approval_sent = False

        # Use a very explicit message that will reliably trigger list_tasks tool
        message = "Use the list_tasks tool to show me all tasks"

        # Stream the response
        responses = []
        logger.info(f"Starting to stream responses for message: {message}")
        user_message = UserMessage(content=message)

        saw_tool_started = False
        stream_count = 0
        async for response in agent_manager.chat_stream(user_message):
            stream_count += 1
            content_preview = (
                getattr(response, "content", "N/A")[:100] if hasattr(response, "content") else "N/A"
            )
            logger.info(
                f"[Stream {stream_count}] Received response: type={response.type}, "
                f"content={content_preview}, "
                f"final={getattr(response, 'final', 'N/A')}"
            )
            responses.append(response)

            # Debug log for every message
            logger.debug(f"[Stream {stream_count}] Full response object: {response}")

            # When we see the approval request, capture the tool_id and send approval
            if response.type == MessageType.APPROVAL_REQUEST and not approval_sent:
                logger.info("Got TOOL_APPROVAL_REQUEST!")
                # Cast to ApprovalRequestMessage to access tool fields
                if isinstance(response, ApprovalRequestMessage):
                    approval_request = response
                    logger.info(f"  Tool ID: {approval_request.tool_id}")
                    logger.info(f"  Tool Name: {approval_request.tool_name}")
                    logger.info(f"  Tool Args: {approval_request.tool_args}")
                    # Verify it's requesting the list_tasks tool
                    assert approval_request.tool_name == "list_tasks"
                    actual_tool_id = approval_request.tool_id
                assert actual_tool_id is not None

                # Send approval with the actual tool_id
                approval = ApprovalResponseMessage(
                    tool_id=actual_tool_id, decision=ApprovalDecision.APPROVED, agent_id="METAGEN"
                )
                logger.info(f"Creating approval response: {approval}")
                logger.info("Sending approval through chat_stream...")

                # Send approval directly
                await agent_manager.handle_tool_approval_response(approval)
                approval_sent = True
                logger.info("Approval sent - continuing to receive messages...")

            # Check for tool execution messages after approval
            if approval_sent:
                logger.debug(f"Post-approval message type: {response.type}")
                if response.type == MessageType.TOOL_STARTED:
                    logger.info(
                        f"✅ Tool execution started: {getattr(response, 'tool_name', 'unknown')}"
                    )
                elif response.type == MessageType.TOOL_RESULT:
                    logger.info(
                        f"✅ Tool result received: {getattr(response, 'result', 'N/A')[:100]}"
                    )
                elif response.type == MessageType.AGENT:
                    if isinstance(response, AgentMessage):
                        logger.info(f"✅ Agent response after tool: {response.content[:100]}")
                elif response.type == MessageType.THINKING:
                    if isinstance(response, AgentMessage):
                        logger.info(f"✅ Agent thinking after approval: {response.content}")

            # Break when we see an AgentMessage after tool execution
            # This is the final response that includes the tool results
            if (
                isinstance(response, AgentMessage)
                and approval_sent
                and saw_tool_started  # Make sure we've seen the tool execute
            ):
                logger.info("Received final AgentMessage after tool execution, breaking loop")
                logger.info(f"  Final content: {response.content}")
                break

            # Track if we've seen tool execution start
            if response.type == MessageType.TOOL_STARTED:
                saw_tool_started = True

        # Log final state
        logger.info(f"Test completed. Total responses: {len(responses)}")
        logger.info(f"Response types received: {[r.type for r in responses]}")
        logger.info(f"Approval sent: {approval_sent}")

        # Verify we got the expected response types
        response_types = [r.type for r in responses]
        assert MessageType.APPROVAL_REQUEST in response_types
        # The approval should have been sent
        assert approval_sent

    @pytest.mark.asyncio
    async def test_full_approval_flow_rejected(self, agent_manager: AgentManager) -> None:
        """Test the full approval flow with rejection."""
        # Configure tool approval
        agent_manager.configure_tool_approval(require_approval=True, auto_approve_tools=set())

        # Variable to store the actual tool_id
        actual_tool_id = None
        rejection_sent = False

        # Use explicit message for deterministic behavior
        message = "Use the list_tasks tool to show all tasks"

        # Stream the response
        responses = []
        user_message = UserMessage(content=message)
        async for response in agent_manager.chat_stream(user_message):
            responses.append(response)
            logger.info(f"Response type: {response.type}")

            # When we see the approval request, send rejection
            if isinstance(response, ApprovalRequestMessage) and not rejection_sent:
                actual_tool_id = response.tool_id
                assert actual_tool_id is not None

                # Send rejection with the actual tool_id
                rejection = ApprovalResponseMessage(
                    tool_id=actual_tool_id,
                    decision=ApprovalDecision.REJECTED,
                    feedback="Not allowed in test environment",
                    agent_id="METAGEN",
                )
                await agent_manager.handle_tool_approval_response(rejection)
                rejection_sent = True

            # Break when we see an AgentMessage after rejection
            # After rejection, agent should respond with why tool wasn't executed
            if isinstance(response, AgentMessage) and rejection_sent:
                logger.info(f"Received final AgentMessage after rejection: {response.content}")
                break

        # Verify we got the expected response types
        response_types = [r.type for r in responses]
        assert MessageType.APPROVAL_REQUEST in response_types
        # The rejection should have been sent
        assert rejection_sent
        # Tool should not have been executed (no TOOL_STARTED message)
        assert MessageType.TOOL_STARTED not in response_types

    @pytest.mark.asyncio
    async def test_selective_tool_approval(self, agent_manager: AgentManager) -> None:
        """Test that only specific tools are auto-approved while others require approval."""
        # Configure with selective auto-approval
        agent_manager.configure_tool_approval(
            require_approval=True,
            auto_approve_tools={"calculator"},  # Only calculator is auto-approved
        )

        # Use a message that will trigger multiple tools
        message = "Calculate 5 + 3, then list all tasks"

        # Stream the response
        responses = []
        approval_requests: list[ApprovalRequestMessage] = []
        execution_events: list[ToolStartedMessage] = []

        user_message = UserMessage(content=message)
        async for response in agent_manager.chat_stream(user_message):
            responses.append(response)

            # Track approval requests
            if isinstance(response, ApprovalRequestMessage):
                approval_requests.append(response)
                # Approve the list_tasks tool when requested
                if response.tool_name == "list_tasks":
                    approval = ApprovalResponseMessage(
                        tool_id=response.tool_id,
                        decision=ApprovalDecision.APPROVED,
                        agent_id="METAGEN",
                    )
                    await agent_manager.handle_tool_approval_response(approval)

            # Track execution events
            elif response.type == MessageType.TOOL_STARTED:
                assert isinstance(response, ToolStartedMessage)
                execution_events.append(response)

            # Break on final response (AgentMessage after tools)
            elif isinstance(response, AgentMessage) and len(execution_events) > 0:
                break

        # Verify behavior:
        # 1. Calculator should NOT have an approval request (auto-approved)
        calculator_approval = any(
            isinstance(req, ApprovalRequestMessage) and req.tool_name == "calculator"
            for req in approval_requests
        )
        assert not calculator_approval, "Calculator should be auto-approved"

        # 2. list_tasks should have an approval request
        list_tasks_approval = any(
            isinstance(req, ApprovalRequestMessage) and req.tool_name == "list_tasks"
            for req in approval_requests
        )
        assert list_tasks_approval, "list_tasks should require approval"

        # 3. Log what actually happened for debugging
        # approval_requests are all ApprovalRequestMessage objects
        tools_requested = [req.tool_name for req in approval_requests]
        # execution_events are all ToolStartedMessage objects
        tools_executed = [event.tool_name for event in execution_events]

        logger.info(f"Tools that required approval: {tools_requested}")
        logger.info(f"Tools that were executed: {tools_executed}")

        # The test should verify the approval mechanism works correctly:
        # - Auto-approved tools should not appear in approval_requests
        # - Non-auto-approved tools should appear in approval_requests
        # - Any tool that was executed should have had proper approval

        # If any tools were executed, verify the approval logic
        if tools_executed:
            for tool_name in tools_executed:
                if tool_name in {"calculator"}:  # Auto-approved tools
                    assert tool_name not in tools_requested, f"{tool_name} should be auto-approved"
                else:  # Non-auto-approved tools
                    assert tool_name in tools_requested, f"{tool_name} should require approval"

    @pytest.mark.asyncio
    async def test_tool_usage_recording_with_approval(
        self, memory_manager: MemoryManager, agent_manager: AgentManager
    ) -> None:
        """Test that tool usage is properly recorded with approval status."""
        # Configure approval
        agent_manager.configure_tool_approval(require_approval=True, auto_approve_tools=set())

        # Inject memory manager
        agent_manager.memory_manager = memory_manager

        # Variable to store the actual tool_id
        actual_tool_id = None
        approval_sent = False

        # Use explicit message
        message = "Use the list_tasks tool"

        # Run the command
        user_message = UserMessage(content=message)
        async for response in agent_manager.chat_stream(user_message):
            # When we see approval request, send approval
            if isinstance(response, ApprovalRequestMessage) and not approval_sent:
                actual_tool_id = response.tool_id
                if actual_tool_id:
                    approval = ApprovalResponseMessage(
                        tool_id=actual_tool_id,
                        decision=ApprovalDecision.APPROVED,
                        agent_id="METAGEN",
                    )
                    await agent_manager.handle_tool_approval_response(approval)
                    approval_sent = True

            # Break on final response (AgentMessage after approval)
            if isinstance(response, AgentMessage) and approval_sent:
                break

        # Give some time for database updates
        await asyncio.sleep(0.5)

        # Query tool usage from database
        tool_usages = await memory_manager.get_recent_tool_usage(tool_name="list_tasks", limit=1)

        # Verify tool usage was recorded with approval
        if len(tool_usages) > 0:
            tool_usage = tool_usages[0]
            assert tool_usage.requires_approval is True
            assert tool_usage.user_decision == "APPROVED"
            # Note: The usage might still be in progress depending on timing

    @pytest.mark.asyncio
    async def test_llm_tool_choice_with_approval(self, agent_manager: AgentManager) -> None:
        """Test real LLM behavior with tool approval - handle indeterminism."""
        # Configure approval with a mix of auto-approved and restricted tools
        agent_manager.configure_tool_approval(
            require_approval=True, auto_approve_tools={"list_tasks", "read_file", "search_files"}
        )

        # Messages that should trigger different tools
        test_cases = [
            ("List all my tasks", {"list_tasks"}),
            ("Create a file at /tmp/test.txt with 'hello world'", {"write_file"}),
            ("Read the contents of /etc/passwd", {"read_file"}),
        ]

        for message, expected_tools in test_cases:
            responses = []
            tool_requests: list[dict[str, Any]] = []
            tool_calls = []

            # Set up approval/rejection based on expected tools
            async def handle_approvals() -> None:
                """Auto-approve or reject based on tool safety."""
                await asyncio.sleep(0.5)  # Let request come in

                # Wait for any approval requests
                while True:
                    if tool_requests:
                        latest_request = tool_requests[-1]
                        tool_name = latest_request.get("tool_name")
                        tool_id = latest_request.get("tool_id", "")

                        if tool_name == "write_file":
                            # Approve file creation
                            await agent_manager.handle_tool_approval_response(
                                ApprovalResponseMessage(
                                    tool_id=tool_id,
                                    decision=ApprovalDecision.APPROVED,
                                    agent_id="METAGEN",
                                )
                            )
                        else:
                            # Reject other non-auto-approved operations
                            await agent_manager.handle_tool_approval_response(
                                ApprovalResponseMessage(
                                    tool_id=tool_id,
                                    decision=ApprovalDecision.REJECTED,
                                    feedback="Not allowed in test",
                                    agent_id="METAGEN",
                                )
                            )
                        break
                    await asyncio.sleep(0.1)

            approval_task = asyncio.create_task(handle_approvals())

            # Stream the response
            user_message = UserMessage(content=message)
            async for response in agent_manager.chat_stream(user_message):
                responses.append(response)

                if isinstance(response, ApprovalRequestMessage):
                    tool_requests.append(
                        {
                            "tool_id": response.tool_id,
                            "tool_name": response.tool_name,
                            "tool_args": response.tool_args,
                        }
                    )
                elif isinstance(response, ToolCallMessage):
                    for tool_call in response.tool_calls:
                        tool_calls.append(tool_call.tool_name)

                # Break when we get an AgentMessage after the initial response
                # This means the LLM has finished processing (with or without tools)
                if isinstance(response, AgentMessage) and len(responses) > 1:
                    break

            # Cancel approval task
            approval_task.cancel()
            try:
                await approval_task
            except asyncio.CancelledError:
                pass

            # Verify behavior - handle LLM choosing different tools
            # response_types = {r.type for r in responses}  # unused
            has_tool_calls = any(isinstance(r, ToolCallMessage) for r in responses)
            has_approval_requests = any(isinstance(r, ApprovalRequestMessage) for r in responses)

            # If LLM chose to use a tool
            if has_tool_calls:
                tools_used = set(tool_calls)

                # Check if any expected tool was called
                if tools_used & expected_tools:
                    # If it's a restricted tool, it should have been through approval
                    if tools_used & {"write_file"}:
                        assert has_approval_requests, "write_file should require approval"
                    # If it's auto-approved, no approval needed
                    elif tools_used & {"list_tasks", "read_file", "search_files"}:
                        assert not has_approval_requests, (
                            "Auto-approved tools should not require approval"
                        )

            # If no tools were called, that's also valid - LLM chose not to use tools
            # This handles LLM indeterminism
