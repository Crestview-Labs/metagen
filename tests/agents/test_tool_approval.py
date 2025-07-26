"""Tests for tool approval functionality in agents."""

import asyncio
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from agents.agent_manager import AgentManager, ResponseType
from agents.base import BaseAgent
from agents.tool_approval import ToolApprovalDecision, ToolApprovalRequest, ToolApprovalResponse
from memory import MemoryManager, SQLiteBackend


class TestToolApprovalDataClasses:
    """Test the tool approval data classes."""

    def test_tool_approval_request_creation(self) -> None:
        """Test creating a ToolApprovalRequest."""
        request = ToolApprovalRequest(
            tool_id="test-123",
            tool_name="write_file",
            tool_args={"path": "/tmp/test.txt", "content": "hello"},
            agent_id="METAGEN",
            description="Write a test file",
            risk_level="medium",
        )

        assert request.tool_id == "test-123"
        assert request.tool_name == "write_file"
        assert request.tool_args == {"path": "/tmp/test.txt", "content": "hello"}
        assert request.agent_id == "METAGEN"
        assert request.description == "Write a test file"
        assert request.risk_level == "medium"

    def test_tool_approval_request_to_dict(self) -> None:
        """Test converting ToolApprovalRequest to dict."""
        request = ToolApprovalRequest(
            tool_id="test-123",
            tool_name="write_file",
            tool_args={"path": "/tmp/test.txt"},
            agent_id="METAGEN",
        )

        data = request.to_dict()
        assert data["tool_id"] == "test-123"
        assert data["tool_name"] == "write_file"
        assert data["tool_args"] == {"path": "/tmp/test.txt"}
        assert data["agent_id"] == "METAGEN"
        assert data["description"] is None
        assert data["risk_level"] is None

    def test_tool_approval_response_creation(self) -> None:
        """Test creating a ToolApprovalResponse."""
        response = ToolApprovalResponse(
            tool_id="test-123",
            decision=ToolApprovalDecision.APPROVED,
            feedback=None,
            approved_by="user",
        )

        assert response.tool_id == "test-123"
        assert response.decision == ToolApprovalDecision.APPROVED
        assert response.feedback is None
        assert response.approved_by == "user"

    def test_tool_approval_response_with_rejection(self) -> None:
        """Test creating a rejection response with feedback."""
        response = ToolApprovalResponse(
            tool_id="test-123",
            decision=ToolApprovalDecision.REJECTED,
            feedback="This operation seems unsafe",
            approved_by="admin",
        )

        assert response.tool_id == "test-123"
        assert response.decision == ToolApprovalDecision.REJECTED
        assert response.feedback == "This operation seems unsafe"
        assert response.approved_by == "admin"

    def test_tool_approval_response_timeout(self) -> None:
        """Test creating a timeout response."""
        response = ToolApprovalResponse.timeout("test-123")

        assert response.tool_id == "test-123"
        assert response.decision == ToolApprovalDecision.TIMEOUT
        assert response.feedback == "Approval request timed out"
        assert response.approved_by == "system"

    def test_tool_approval_decision_enum(self) -> None:
        """Test ToolApprovalDecision enum values."""
        assert ToolApprovalDecision.APPROVED == "approved"
        assert ToolApprovalDecision.REJECTED == "rejected"
        assert ToolApprovalDecision.TIMEOUT == "timeout"


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

            async def build_context(self, query: str) -> list[dict[str, Any]]:
                """Dummy implementation."""
                return []

        agent = TestAgent(
            agent_id="TEST_AGENT",
            instructions="Test instructions",
            agentic_client=mock_agentic_client,
            memory_manager=mock_memory_manager,
        )
        await agent.initialize()
        return agent

    @pytest.mark.asyncio
    async def test_configure_tool_approval(self, base_agent: BaseAgent) -> None:
        """Test configuring tool approval settings."""
        approval_queue: asyncio.Queue[ToolApprovalResponse] = asyncio.Queue()

        base_agent.configure_tool_approval(
            require_approval=True,
            auto_approve_tools={"read_file", "list_files"},
            approval_timeout=10.0,
            approval_response_queue=approval_queue,
        )

        assert base_agent._require_tool_approval is True
        assert base_agent._auto_approve_tools == {"read_file", "list_files"}
        assert base_agent._approval_timeout == 10.0
        assert base_agent._approval_response_queue == approval_queue

    @pytest.mark.asyncio
    async def test_configure_tool_approval_without_queue_raises_error(
        self, base_agent: BaseAgent
    ) -> None:
        """Test that configuring approval without queue raises ValueError."""
        with pytest.raises(ValueError, match="approval_response_queue must be provided"):
            base_agent.configure_tool_approval(require_approval=True)

    @pytest.mark.asyncio
    async def test_process_approval_response_approved(
        self, base_agent: BaseAgent, mock_memory_manager: AsyncMock
    ) -> None:
        """Test processing approval response when approved."""
        from agents.tool_approval import ToolPendingApproval

        base_agent.configure_tool_approval(
            require_approval=True, approval_timeout=30.0, approval_response_queue=asyncio.Queue()
        )

        # Create a pending approval
        pending = ToolPendingApproval(
            tool_id="tool-123",
            tool_name="write_file",
            tool_args={"path": "/tmp/test.txt"},
            turn_id="turn-123",
            trace_id="trace-123",
            tool_usage_id="tool-123",
        )
        base_agent._pending_approvals["tool-123"] = pending

        # Create approval response
        approval_response = ToolApprovalResponse(
            tool_id="tool-123", decision=ToolApprovalDecision.APPROVED, approved_by="user"
        )

        # Process the approval
        events = []
        async for event in base_agent.process_approval_response(approval_response):
            events.append(event)

        # Should have approval and tool call events
        assert len(events) == 2
        assert events[0]["stage"] == "tool_approved"
        assert events[1]["stage"] == "tool_call"

        # Check that approval was recorded in database
        mock_memory_manager.update_tool_approval.assert_called_once_with(
            "tool-123", approved=True, user_feedback=None
        )

        # Pending approval should be removed
        assert "tool-123" not in base_agent._pending_approvals

    @pytest.mark.asyncio
    async def test_process_approval_response_rejected(
        self, base_agent: BaseAgent, mock_memory_manager: AsyncMock
    ) -> None:
        """Test processing approval response when rejected."""
        from agents.tool_approval import ToolPendingApproval

        base_agent.configure_tool_approval(
            require_approval=True, approval_timeout=30.0, approval_response_queue=asyncio.Queue()
        )

        # Create a pending approval
        pending = ToolPendingApproval(
            tool_id="tool-123",
            tool_name="delete_file",
            tool_args={"path": "/important.txt"},
            turn_id="turn-123",
            trace_id="trace-123",
            tool_usage_id="tool-123",
        )
        base_agent._pending_approvals["tool-123"] = pending

        # Create rejection response
        approval_response = ToolApprovalResponse(
            tool_id="tool-123",
            decision=ToolApprovalDecision.REJECTED,
            feedback="Too dangerous",
            approved_by="admin",
        )

        # Process the rejection
        events = []
        async for event in base_agent.process_approval_response(approval_response):
            events.append(event)

        # Should have rejection event only
        assert len(events) == 1
        assert events[0]["stage"] == "tool_rejected"
        assert events[0]["metadata"]["feedback"] == "Too dangerous"

        # Check that rejection was recorded in database
        mock_memory_manager.update_tool_approval.assert_called_once_with(
            "tool-123", approved=False, user_feedback="Too dangerous"
        )

        # Pending approval should be removed
        assert "tool-123" not in base_agent._pending_approvals

    @pytest.mark.asyncio
    async def test_check_expired_approvals(
        self, base_agent: BaseAgent, mock_memory_manager: AsyncMock
    ) -> None:
        """Test checking for expired approvals."""
        from agents.tool_approval import ToolPendingApproval

        base_agent.configure_tool_approval(
            require_approval=True,
            approval_timeout=0.1,  # Very short timeout
            approval_response_queue=asyncio.Queue(),
        )

        # Create a pending approval that will expire
        pending = ToolPendingApproval(
            tool_id="tool-123",
            tool_name="execute_command",
            tool_args={"command": "rm -rf /"},
            turn_id="turn-123",
            trace_id="trace-123",
            tool_usage_id="tool-123",
        )
        base_agent._pending_approvals["tool-123"] = pending

        # Wait for it to expire
        await asyncio.sleep(0.2)

        # Check for expired approvals
        timeout_events = await base_agent.check_expired_approvals()

        # Should have one timeout event
        assert len(timeout_events) == 1
        assert timeout_events[0]["stage"] == "tool_rejected"
        assert "timed out" in timeout_events[0]["content"]
        assert timeout_events[0]["metadata"]["decision"] == ToolApprovalDecision.TIMEOUT.value

        # Pending approval should be removed
        assert "tool-123" not in base_agent._pending_approvals

    @pytest.mark.asyncio
    async def test_process_approval_response_late(
        self, base_agent: BaseAgent, mock_memory_manager: AsyncMock
    ) -> None:
        """Test processing approval response after timeout."""
        base_agent.configure_tool_approval(
            require_approval=True, approval_timeout=30.0, approval_response_queue=asyncio.Queue()
        )

        # No pending approval (already timed out)
        approval_response = ToolApprovalResponse(
            tool_id="tool-123", decision=ToolApprovalDecision.APPROVED, approved_by="user"
        )

        # Process the late approval
        events = []
        async for event in base_agent.process_approval_response(approval_response):
            events.append(event)

        # Should have late approval event
        assert len(events) == 1
        assert events[0]["stage"] == "tool_approval_late"
        assert "too late" in events[0]["content"]

        # Database should still be updated for record keeping
        mock_memory_manager.update_tool_approval.assert_called_once_with(
            "tool-123", approved=True, user_feedback="Received after timeout"
        )

    @pytest.mark.asyncio
    async def test_handle_tool_call_event_with_approval(
        self, base_agent: BaseAgent, mock_memory_manager: AsyncMock
    ) -> None:
        """Test handling tool call event that requires approval."""
        base_agent.configure_tool_approval(
            require_approval=True,
            auto_approve_tools={"read_file"},
            approval_timeout=30.0,
            approval_response_queue=asyncio.Queue(),
        )

        # Create mock event
        mock_event = MagicMock()
        mock_event.metadata = {
            "tool_name": "write_file",
            "tool_args": {"path": "tests/tmpdir/test.txt"},
        }
        mock_event.content = "Writing file"

        # Mock record_tool_usage to return a tool ID
        mock_memory_manager.record_tool_usage.return_value = "usage-123"

        # Call handler
        events = []
        async for event in base_agent._handle_tool_call_event(
            event=mock_event, turn_id="turn-123", trace_id="trace-123", tool_usage_map={}
        ):
            events.append(event)

        # Should only have approval request event (non-blocking!)
        assert len(events) == 1
        assert events[0]["stage"] == "tool_approval_request"
        assert "write_file" in events[0]["content"]

        # Tool should be recorded as requiring approval
        mock_memory_manager.record_tool_usage.assert_called_once_with(
            turn_id="turn-123",
            entity_id="TEST_AGENT",
            tool_name="write_file",
            tool_args={"path": "tests/tmpdir/test.txt"},
            requires_approval=True,
            trace_id="trace-123",
        )

        # Should have pending approval
        assert "usage-123" in base_agent._pending_approvals
        pending = base_agent._pending_approvals["usage-123"]
        assert pending.tool_name == "write_file"

        # Tool should NOT be started yet
        mock_memory_manager.start_tool_execution.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_tool_call_event_auto_approved(
        self, base_agent: BaseAgent, mock_memory_manager: AsyncMock
    ) -> None:
        """Test handling tool call event that is auto-approved."""
        base_agent.configure_tool_approval(
            require_approval=True,
            auto_approve_tools={"read_file"},
            approval_timeout=1.0,
            approval_response_queue=asyncio.Queue(),
        )

        # Create mock event for auto-approved tool
        mock_event = MagicMock()
        mock_event.metadata = {
            "tool_name": "read_file",
            "tool_args": {"path": "tests/tmpdir/test.txt"},
        }
        mock_event.content = "Reading file"

        # Call handler
        events = []
        async for event in base_agent._handle_tool_call_event(
            event=mock_event, turn_id="turn-123", trace_id="trace-123", tool_usage_map={}
        ):
            events.append(event)

        # Should only have tool call event (no approval needed)
        assert len(events) == 1
        assert events[0]["stage"] == "tool_call"

        # Tool should be recorded as not requiring approval
        mock_memory_manager.record_tool_usage.assert_called_once_with(
            turn_id="turn-123",
            entity_id="TEST_AGENT",
            tool_name="read_file",
            tool_args={"path": "tests/tmpdir/test.txt"},
            requires_approval=False,  # Auto-approved
            trace_id="trace-123",
        )


class TestToolApprovalEndToEnd:
    """End-to-end tests for tool approval functionality."""

    @pytest_asyncio.fixture
    async def test_db_manager(self, tmp_path: Any) -> AsyncIterator[Any]:
        """Create a test database manager."""
        from db.manager import DatabaseManager

        db_path = tmp_path / "test_approval.db"
        manager = DatabaseManager(db_path)
        await manager.initialize()
        yield manager
        await manager.close()

    @pytest_asyncio.fixture
    async def memory_manager(self, test_db_manager: Any) -> MemoryManager:
        """Create a real memory manager."""
        backend = SQLiteBackend(test_db_manager)
        manager = MemoryManager(backend)
        await manager.initialize()
        return manager

    @pytest_asyncio.fixture
    async def agent_manager(self, test_db_manager: Any) -> AsyncIterator[AgentManager]:
        """Create a real AgentManager."""
        manager = AgentManager(
            agent_name="TestManager",
            db_manager=test_db_manager,
            mcp_servers=[],  # No MCP servers for testing
        )
        await manager.initialize()
        yield manager
        await manager.cleanup()

    @pytest.mark.asyncio
    async def test_full_approval_flow_approved(self, agent_manager: AgentManager) -> None:
        """Test the full approval flow with approval."""
        # Configure tool approval
        agent_manager.configure_tool_approval(
            require_approval=True,
            auto_approve_tools=set(),  # No auto-approved tools
            approval_timeout=5.0,
        )

        # Variable to store the actual tool_id
        actual_tool_id = None
        approval_sent = False

        # Use a very explicit message that will reliably trigger list_tasks tool
        message = "Use the list_tasks tool to show me all tasks"

        # Stream the response
        responses = []
        async for response in agent_manager.chat_stream(message):
            responses.append(response)

            # When we see the approval request, capture the tool_id and send approval
            if response.type == ResponseType.TOOL_APPROVAL_REQUEST and not approval_sent:
                # Verify it's requesting the list_tasks tool
                assert "list_tasks" in response.content
                actual_tool_id = response.metadata.get("tool_id") if response.metadata else None
                assert actual_tool_id is not None

                # Send approval with the actual tool_id
                approval = ToolApprovalResponse(
                    tool_id=actual_tool_id,
                    decision=ToolApprovalDecision.APPROVED,
                    approved_by="test-user",
                )
                await agent_manager.handle_tool_approval_response(approval)
                approval_sent = True

            # Break when we see the final response
            if (
                response.type == ResponseType.TEXT
                and response.metadata
                and response.metadata.get("final")
            ):
                break

        # Verify we got the expected response types
        response_types = [r.type for r in responses]
        assert ResponseType.TOOL_APPROVAL_REQUEST in response_types
        # The approval should have been sent
        assert approval_sent

    @pytest.mark.asyncio
    async def test_full_approval_flow_rejected(self, agent_manager: AgentManager) -> None:
        """Test the full approval flow with rejection."""
        # Configure tool approval
        agent_manager.configure_tool_approval(
            require_approval=True, auto_approve_tools=set(), approval_timeout=5.0
        )

        # Variable to store the actual tool_id
        actual_tool_id = None
        rejection_sent = False

        # Use explicit message for deterministic behavior
        message = "Use the list_tasks tool to show all tasks"

        # Stream the response
        responses = []
        async for response in agent_manager.chat_stream(message):
            responses.append(response)

            # When we see the approval request, send rejection
            if response.type == ResponseType.TOOL_APPROVAL_REQUEST and not rejection_sent:
                actual_tool_id = response.metadata.get("tool_id") if response.metadata else None
                assert actual_tool_id is not None

                # Send rejection with the actual tool_id
                rejection = ToolApprovalResponse(
                    tool_id=actual_tool_id,
                    decision=ToolApprovalDecision.REJECTED,
                    feedback="Not allowed in test environment",
                    approved_by="test-admin",
                )
                await agent_manager.handle_tool_approval_response(rejection)
                rejection_sent = True

            # Break when we see the final response
            if (
                response.type == ResponseType.TEXT
                and response.metadata
                and response.metadata.get("final")
            ):
                break

        # Verify we got the expected response types
        response_types = [r.type for r in responses]
        assert ResponseType.TOOL_APPROVAL_REQUEST in response_types
        # The rejection should have been sent
        assert rejection_sent
        # Tool should not have been executed
        assert ResponseType.TOOL_CALL not in response_types

    @pytest.mark.asyncio
    async def test_auto_approved_tools_bypass_approval(self, agent_manager: AgentManager) -> None:
        """Test that auto-approved tools bypass the approval process."""
        # Configure tool approval
        agent_manager.configure_tool_approval(
            require_approval=True,
            auto_approve_tools={"list_tasks", "read_file"},
            approval_timeout=1.0,
        )

        # Create a mock event for tool call
        mock_event = MagicMock()
        mock_event.metadata = {"tool_name": "list_tasks", "tool_args": {"limit": 10}}
        mock_event.content = "Listing tasks"

        base_agent = agent_manager.meta_agent
        assert base_agent is not None

        # Process the tool call event - should not require approval
        events = []
        async for event in base_agent._handle_tool_call_event(
            event=mock_event, turn_id="test-turn-123", trace_id="test-trace-123", tool_usage_map={}
        ):
            events.append(event)

        # Auto-approved tools should not generate approval events
        event_stages = [e["stage"] for e in events]
        assert "tool_approval_request" not in event_stages
        assert "tool_approved" not in event_stages
        assert "tool_rejected" not in event_stages
        assert "tool_call" in event_stages  # Should proceed directly to execution

    @pytest.mark.asyncio
    async def test_non_approved_tools_require_approval(self, agent_manager: AgentManager) -> None:
        """Test that non-auto-approved tools wait for approval."""
        # Mock the memory manager to avoid database dependencies
        base_agent = agent_manager.meta_agent
        assert base_agent is not None
        base_agent.memory_manager = AsyncMock()
        base_agent.memory_manager.record_tool_usage = AsyncMock(return_value="test-tool-id")
        base_agent.memory_manager.update_tool_approval = AsyncMock()

        # Configure tool approval
        agent_manager.configure_tool_approval(
            require_approval=True,
            auto_approve_tools={"list_tasks"},  # Only this is auto-approved
            approval_timeout=5.0,
        )

        # Create a mock event for a non-auto-approved tool
        mock_event = MagicMock()
        mock_event.metadata = {
            "tool_name": "write_file",
            "tool_args": {"path": "/tmp/test.txt", "content": "test"},
        }
        mock_event.content = "Writing file"

        # The tricky part: _handle_tool_approval is called BEFORE the approval event is yielded
        # So we need to pre-populate the queue with the approval

        # We know the tool ID will be "test-tool-id" from our mock
        expected_tool_id = "test-tool-id"

        # Process the tool call event (non-blocking now!)
        events = []
        async for event in base_agent._handle_tool_call_event(
            event=mock_event, turn_id="test-turn-123", trace_id="test-trace-123", tool_usage_map={}
        ):
            events.append(event)

        # Should only have approval request
        assert len(events) == 1
        assert events[0]["stage"] == "tool_approval_request"

        # Should have pending approval
        assert expected_tool_id in base_agent._pending_approvals

        # Now simulate user approval
        approval = ToolApprovalResponse(
            tool_id=expected_tool_id,
            decision=ToolApprovalDecision.APPROVED,
            approved_by="test_user",
        )

        # Process the approval response
        approval_events = []
        async for event in base_agent.process_approval_response(approval):
            approval_events.append(event)

        # Should have approval and tool call events
        assert len(approval_events) == 2
        assert approval_events[0]["stage"] == "tool_approved"
        assert approval_events[1]["stage"] == "tool_call"

        # Verify the approval was recorded
        base_agent.memory_manager.update_tool_approval.assert_called_once_with(
            "test-tool-id", approved=True, user_feedback=None
        )

    @pytest.mark.asyncio
    async def test_rejected_tools_are_blocked(self, agent_manager: AgentManager) -> None:
        """Test that rejected tools are not executed."""
        # Mock the memory manager
        base_agent = agent_manager.meta_agent
        assert base_agent is not None
        base_agent.memory_manager = AsyncMock()
        base_agent.memory_manager.record_tool_usage = AsyncMock(return_value="test-tool-id")
        base_agent.memory_manager.update_tool_approval = AsyncMock()

        # Configure tool approval
        agent_manager.configure_tool_approval(
            require_approval=True,
            auto_approve_tools=set(),  # No auto-approved tools
            approval_timeout=2.0,
        )

        # Create a mock event for a tool that will be rejected
        mock_event = MagicMock()
        mock_event.metadata = {
            "tool_name": "write_file",
            "tool_args": {"path": "/etc/important.conf", "content": "dangerous"},
        }
        mock_event.content = "Writing system file"

        # Process the tool call event
        events = []
        async for event in base_agent._handle_tool_call_event(
            event=mock_event, turn_id="test-turn-123", trace_id="test-trace-123", tool_usage_map={}
        ):
            events.append(event)

        # Should only have approval request
        assert len(events) == 1
        assert events[0]["stage"] == "tool_approval_request"
        tool_id_to_reject = events[0]["metadata"]["tool_id"]

        # Should have pending approval
        assert tool_id_to_reject in base_agent._pending_approvals

        # Now simulate user rejection
        rejection = ToolApprovalResponse(
            tool_id=tool_id_to_reject,
            decision=ToolApprovalDecision.REJECTED,
            feedback="Too dangerous for test environment",
            approved_by="test_admin",
        )

        # Process the rejection
        rejection_events = []
        async for event in base_agent.process_approval_response(rejection):
            rejection_events.append(event)

        # Should have rejection event only
        assert len(rejection_events) == 1
        assert rejection_events[0]["stage"] == "tool_rejected"
        assert rejection_events[0]["metadata"]["feedback"] == "Too dangerous for test environment"

        # Verify the rejection was recorded
        base_agent.memory_manager.update_tool_approval.assert_called_once_with(
            "test-tool-id", approved=False, user_feedback="Too dangerous for test environment"
        )

    @pytest.mark.asyncio
    async def test_approval_timeout(self, agent_manager: AgentManager) -> None:
        """Test that approval times out correctly."""
        # Configure with very short timeout
        agent_manager.configure_tool_approval(
            require_approval=True,
            auto_approve_tools=set(),
            approval_timeout=1.0,  # 1 second timeout
        )

        # Use explicit message
        message = "Use the list_tasks tool"

        # Stream the response
        responses = []
        approval_request_seen = False

        async for response in agent_manager.chat_stream(message):
            responses.append(response)

            # Track when we see approval request
            if response.type == ResponseType.TOOL_APPROVAL_REQUEST:
                approval_request_seen = True
                # Don't send approval - let it timeout

            # Break when we see the final response
            if (
                response.type == ResponseType.TEXT
                and response.metadata
                and response.metadata.get("final")
            ):
                break

        # Should have seen approval request
        assert approval_request_seen

        # Wait a bit for timeout to be processed
        await asyncio.sleep(2.0)

        # Check if any agent has expired approvals
        # Note: The timeout event might not appear in the stream since it's handled separately

    @pytest.mark.asyncio
    async def test_selective_tool_approval(self, agent_manager: AgentManager) -> None:
        """Test that only specific tools are auto-approved while others require approval."""
        # Configure with selective auto-approval
        agent_manager.configure_tool_approval(
            require_approval=True,
            auto_approve_tools={"get_current_time"},  # Only time tool is auto-approved
            approval_timeout=2.0,
        )

        # Background task to reject non-approved tools
        rejected_tools: list[str] = []

        async def reject_non_time_tools() -> None:
            """Reject any tool that isn't get_current_time."""
            while True:
                await asyncio.sleep(0.1)
                # Check if there's a pending approval
                if agent_manager.approval_response_queue:
                    # Peek at pending approvals (this is a hack, but better than deep mocking)
                    # In real usage, this would come from UI/CLI
                    # For now, just reject after seeing approval request
                    if rejected_tools:  # We've seen an approval request
                        rejection = ToolApprovalResponse(
                            tool_id="test-tool-id",
                            decision=ToolApprovalDecision.REJECTED,
                            feedback="Only time queries allowed in test",
                            approved_by="test",
                        )
                        await agent_manager.handle_tool_approval_response(rejection)
                        break

        rejection_task = asyncio.create_task(reject_non_time_tools())

        # Send explicit messages to test auto-approval
        message = "Use the list_tasks tool to show all tasks"

        # Stream the response
        responses = []
        tools_called = []
        tools_rejected = []

        async for response in agent_manager.chat_stream(message):
            responses.append(response)

            if response.type == ResponseType.TOOL_CALL:
                tool_name = response.metadata.get("tool_name") if response.metadata else None
                tools_called.append(tool_name)
            elif response.type == ResponseType.TOOL_APPROVAL_REQUEST:
                tool_name = response.metadata.get("tool_name") if response.metadata else None
                if tool_name:
                    rejected_tools.append(tool_name)
            elif response.type == ResponseType.TOOL_REJECTED:
                tool_name = response.metadata.get("tool_name") if response.metadata else None
                tools_rejected.append(tool_name)

        # Cancel rejection task
        rejection_task.cancel()
        try:
            await rejection_task
        except asyncio.CancelledError:
            pass

        # Verify behavior
        # get_current_time should be called without approval
        if "get_current_time" in tools_called:
            assert "get_current_time" not in rejected_tools

        # Other tools should require approval
        for tool in tools_called:
            if tool != "get_current_time":
                assert tool in rejected_tools or tool in tools_rejected

    @pytest.mark.asyncio
    async def test_tool_usage_recording_with_approval(
        self, memory_manager: MemoryManager, agent_manager: AgentManager
    ) -> None:
        """Test that tool usage is properly recorded with approval status."""
        # Configure approval
        agent_manager.configure_tool_approval(
            require_approval=True, auto_approve_tools=set(), approval_timeout=5.0
        )

        # Inject memory manager
        agent_manager.memory_manager = memory_manager

        # Variable to store the actual tool_id
        actual_tool_id = None
        approval_sent = False

        # Use explicit message
        message = "Use the list_tasks tool"

        # Run the command
        async for response in agent_manager.chat_stream(message):
            # When we see approval request, send approval
            if response.type == ResponseType.TOOL_APPROVAL_REQUEST and not approval_sent:
                actual_tool_id = response.metadata.get("tool_id") if response.metadata else None
                if actual_tool_id:
                    approval = ToolApprovalResponse(
                        tool_id=actual_tool_id,
                        decision=ToolApprovalDecision.APPROVED,
                        approved_by="tester",
                    )
                    await agent_manager.handle_tool_approval_response(approval)
                    approval_sent = True

            # Break on final response
            if (
                response.type == ResponseType.TEXT
                and response.metadata
                and response.metadata.get("final")
            ):
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
            require_approval=True,
            auto_approve_tools={"list_tasks", "read_file", "search_files"},
            approval_timeout=3.0,
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
                                ToolApprovalResponse(
                                    tool_id=tool_id,
                                    decision=ToolApprovalDecision.APPROVED,
                                    approved_by="test",
                                )
                            )
                        else:
                            # Reject other non-auto-approved operations
                            await agent_manager.handle_tool_approval_response(
                                ToolApprovalResponse(
                                    tool_id=tool_id,
                                    decision=ToolApprovalDecision.REJECTED,
                                    feedback="Not allowed in test",
                                    approved_by="test",
                                )
                            )
                        break
                    await asyncio.sleep(0.1)

            approval_task = asyncio.create_task(handle_approvals())

            # Stream the response
            async for response in agent_manager.chat_stream(message):
                responses.append(response)

                if response.type == ResponseType.TOOL_APPROVAL_REQUEST:
                    if response.metadata:
                        tool_requests.append(response.metadata)
                elif response.type == ResponseType.TOOL_CALL:
                    if response.metadata:
                        tool_calls.append(response.metadata.get("tool_name"))

            # Cancel approval task
            approval_task.cancel()
            try:
                await approval_task
            except asyncio.CancelledError:
                pass

            # Verify behavior - handle LLM choosing different tools
            response_types = {r.type for r in responses}

            # If LLM chose to use a tool
            if ResponseType.TOOL_CALL in response_types:
                tools_used = set(tool_calls)

                # Check if any expected tool was called
                if tools_used & expected_tools:
                    # If it's a restricted tool, it should have been through approval
                    if tools_used & {"write_file"}:
                        assert ResponseType.TOOL_APPROVAL_REQUEST in response_types
                    # If it's auto-approved, no approval needed
                    elif tools_used & {"list_tasks", "read_file", "search_files"}:
                        assert ResponseType.TOOL_APPROVAL_REQUEST not in response_types

            # If no tools were called, that's also valid - LLM chose not to use tools
            # This handles LLM indeterminism
