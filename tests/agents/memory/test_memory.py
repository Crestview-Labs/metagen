"""Tests for MemoryManager typed interface."""

import asyncio
from datetime import datetime

import pytest
from sqlalchemy.orm import selectinload

from agents.memory.memory_backend import MemoryBackend
from agents.memory.memory_manager import MemoryManager
from common.models import ConversationTurn, ToolUsage, ToolUsageStatus, TurnStatus
from common.types.memory import (
    ToolApprovalUpdate,
    ToolExecutionComplete,
    ToolExecutionStart,
    ToolUsageRequest,
    TurnCompletionRequest,
    TurnCreationRequest,
    TurnUpdateRequest,
)
from common.types.tools import ToolCall, ToolCallResult


class TestTurnManagement:
    """Test typed interface for turn management."""

    @pytest.mark.asyncio
    async def test_create_turn(self, memory_manager: MemoryManager) -> None:
        """Test creating a turn with typed request."""
        request = TurnCreationRequest(
            user_query="What's the weather today?",
            agent_id="test-agent",
            task_id="weather-task",
            source_entity="USER",
            target_entity="test-agent",
            conversation_type="USER_AGENT",
            user_metadata={"session": "test-session"},
        )

        turn_id = await memory_manager.create_turn(request)
        assert turn_id is not None

        # Verify turn was created
        turns = await memory_manager.get_recent_conversations(limit=1)
        assert len(turns) == 1
        assert turns[0].id == turn_id
        assert turns[0].user_query == "What's the weather today?"
        assert turns[0].agent_id == "test-agent"
        assert turns[0].task_id == "weather-task"
        assert turns[0].status == "in_progress"

    @pytest.mark.asyncio
    async def test_update_turn(self, memory_manager: MemoryManager) -> None:
        """Test updating a turn with typed request."""
        # Create a turn first
        create_request = TurnCreationRequest(user_query="Calculate 2+2", agent_id="calc-agent")
        turn_id = await memory_manager.create_turn(create_request)

        # Update it
        update_request = TurnUpdateRequest(
            turn_id=turn_id,
            agent_response="Let me calculate...",
            status=TurnStatus.IN_PROGRESS,
            llm_context={"messages": [{"role": "user", "content": "Calculate 2+2"}]},
            total_duration_ms=100,
            llm_duration_ms=50,
            agent_metadata={"model": "test-model"},
        )

        success = await memory_manager.update_turn(update_request)
        assert success

        # Verify update
        turns = await memory_manager.get_recent_conversations(limit=1)
        assert turns[0].agent_response == "Let me calculate..."
        assert turns[0].status == "in_progress"

    @pytest.mark.asyncio
    async def test_complete_turn_with_tools(self, memory_manager: MemoryManager) -> None:
        """Test completing a turn with tool usage."""
        # Create turn
        create_request = TurnCreationRequest(
            user_query="Search for Python tutorials", agent_id="search-agent"
        )
        turn_id = await memory_manager.create_turn(create_request)

        # Complete with tool usage
        tool_call = ToolCall(
            id="tool-1",
            name="web_search",
            arguments={"query": "Python tutorials"},
            agent_id="test-agent",
            session_id="test-session",
        )

        tool_result = ToolCallResult(
            tool_name="web_search",
            tool_call_id="tool-1",
            agent_id="test-agent",
            session_id="test-session",
            content="Found 10 Python tutorials",
            is_error=False,
            error=None,
            error_type=None,
            user_display=None,
        )

        complete_request = TurnCompletionRequest(
            turn_id=turn_id,
            agent_response="I found 10 Python tutorials for you.",
            tool_calls=[tool_call],
            tool_results=[tool_result],
            status=TurnStatus.COMPLETED,
            total_duration_ms=500,
            llm_duration_ms=200,
            tools_duration_ms=300,
        )

        await memory_manager.complete_turn(complete_request)

        # Verify completion
        turns = await memory_manager.get_recent_conversations(limit=1)
        assert turns[0].status == "completed"
        assert turns[0].agent_response == "I found 10 Python tutorials for you."
        assert turns[0].tools_used is True
        assert turns[0].total_duration_ms == 500
        assert turns[0].llm_duration_ms == 200
        assert turns[0].tools_duration_ms == 300

    @pytest.mark.asyncio
    async def test_complete_turn_with_error(self, memory_manager: MemoryManager) -> None:
        """Test completing a turn with error status."""
        # Create turn
        create_request = TurnCreationRequest(
            user_query="Do something impossible", agent_id="error-agent"
        )
        turn_id = await memory_manager.create_turn(create_request)

        # Complete with error
        complete_request = TurnCompletionRequest(
            turn_id=turn_id,
            agent_response="",  # No response due to error
            status=TurnStatus.ERROR,
            error_details="Failed to process request: impossible task",
        )

        await memory_manager.complete_turn(complete_request)

        # Verify error handling
        turns = await memory_manager.get_recent_conversations(limit=1)
        assert turns[0].status == "error"
        assert turns[0].error_details == {"error": "Failed to process request: impossible task"}


class TestToolUsageInterface:
    """Test typed interface for tool usage."""

    @pytest.mark.asyncio
    async def test_record_tool_usage(self, memory_manager: MemoryManager) -> None:
        """Test recording tool usage with typed request."""
        # Create turn first
        turn_id = await memory_manager.create_turn(
            TurnCreationRequest(user_query="Check my calendar", agent_id="calendar-agent")
        )

        # Record tool usage
        tool_request = ToolUsageRequest(
            tool_name="calendar_check",
            tool_args={"date": "today"},
            turn_id=turn_id,
            agent_id="calendar-agent",
            requires_approval=True,
            tool_call_id="call-123",
        )

        tool_id = await memory_manager.record_tool_use(tool_request)
        assert tool_id is not None

        # Verify tool was recorded
        tools = await memory_manager.get_tool_usage_for_turn(turn_id)
        assert len(tools) == 1
        assert tools[0].tool_name == "calendar_check"
        assert tools[0].requires_approval is True
        assert tools[0].tool_call_id == "call-123"

    @pytest.mark.asyncio
    async def test_tool_approval_flow(self, memory_manager: MemoryManager) -> None:
        """Test tool approval with typed interface."""
        # Create turn and tool
        turn_id = await memory_manager.create_turn(
            TurnCreationRequest(user_query="Delete files", agent_id="file-agent")
        )

        tool_request = ToolUsageRequest(
            tool_name="delete_files",
            tool_args={"pattern": "*.tmp"},
            turn_id=turn_id,
            agent_id="file-agent",
            requires_approval=True,
        )

        tool_id = await memory_manager.record_tool_use(tool_request)

        # Approve tool
        approval = ToolApprovalUpdate(
            tool_usage_id=tool_id, approved=True, user_feedback="OK to delete temp files"
        )

        success = await memory_manager.update_approval(approval)
        assert success

        # Verify approval
        tools = await memory_manager.get_tool_usage_for_turn(turn_id)
        assert tools[0].user_decision == "APPROVED"
        assert tools[0].user_feedback == "OK to delete temp files"

    @pytest.mark.asyncio
    async def test_tool_execution_lifecycle(self, memory_manager: MemoryManager) -> None:
        """Test complete tool execution lifecycle with typed interface."""
        # Create turn and tool
        turn_id = await memory_manager.create_turn(
            TurnCreationRequest(user_query="What time is it?", agent_id="time-agent")
        )

        tool_id = await memory_manager.record_tool_use(
            ToolUsageRequest(
                tool_name="get_time",
                tool_args={},
                turn_id=turn_id,
                agent_id="time-agent",
                requires_approval=False,
            )
        )

        # Start execution
        start_request = ToolExecutionStart(tool_usage_id=tool_id)
        await memory_manager.start_execution(start_request)

        # Complete execution
        tool_result = ToolCallResult(
            tool_name="get_time",
            tool_call_id=tool_id,
            agent_id="time-agent",
            session_id="test-session",
            content="3:45 PM PST",
            is_error=False,
            error=None,
            error_type=None,
            user_display=None,
        )

        complete_request = ToolExecutionComplete(
            tool_usage_id=tool_id, result=tool_result, duration_ms=25
        )

        await memory_manager.complete_execution(complete_request)

        # Verify execution
        tools = await memory_manager.get_tool_usage_for_turn(turn_id)
        assert tools[0].execution_status == ToolUsageStatus.SUCCESS
        assert tools[0].execution_result == tool_result.model_dump()
        assert tools[0].duration_ms == 25


class TestPerformanceMetrics:
    """Test performance metric tracking."""

    @pytest.mark.asyncio
    async def test_duration_tracking(self, memory_manager: MemoryManager) -> None:
        """Test tracking execution durations."""
        # Create and complete a turn with detailed timing
        turn_id = await memory_manager.create_turn(
            TurnCreationRequest(user_query="Complex task", agent_id="perf-agent")
        )

        # Add tool for realistic scenario
        tool_id = await memory_manager.record_tool_use(
            ToolUsageRequest(
                tool_name="complex_tool",
                tool_args={"complexity": "high"},
                turn_id=turn_id,
                agent_id="perf-agent",
                requires_approval=False,
            )
        )

        # Execute tool
        await memory_manager.start_execution(ToolExecutionStart(tool_usage_id=tool_id))

        await memory_manager.complete_execution(
            ToolExecutionComplete(
                tool_usage_id=tool_id,
                result=ToolCallResult(
                    tool_name="complex_tool",
                    tool_call_id=tool_id,
                    agent_id="approval-agent",
                    session_id="test-session",
                    content="Task completed",
                    is_error=False,
                    error=None,
                    error_type=None,
                    user_display=None,
                ),
                duration_ms=150,
            )
        )

        # Complete turn with performance data
        await memory_manager.complete_turn(
            TurnCompletionRequest(
                turn_id=turn_id,
                agent_response="Complex task completed successfully.",
                status=TurnStatus.COMPLETED,
                total_duration_ms=300,
                llm_duration_ms=100,
                tools_duration_ms=150,
            )
        )

        # Verify metrics
        turns = await memory_manager.get_recent_conversations(limit=1)
        turn = turns[0]
        assert turn.total_duration_ms == 300
        assert turn.llm_duration_ms == 100
        assert turn.tools_duration_ms == 150

        # Verify consistency
        assert turn.total_duration_ms >= turn.llm_duration_ms + turn.tools_duration_ms


class TestCriticalEdgeCases:
    """Test critical edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_concurrent_turn_updates(self, memory_manager: MemoryManager) -> None:
        """Test handling concurrent updates to the same turn."""
        # Create a turn
        request = TurnCreationRequest(user_query="Concurrent test", agent_id="concurrent-agent")
        turn_id = await memory_manager.create_turn(request)

        # Simulate concurrent updates
        update1 = TurnUpdateRequest(
            turn_id=turn_id,
            agent_response="Response 1",
            status=TurnStatus.IN_PROGRESS,
            llm_duration_ms=100,
        )

        update2 = TurnUpdateRequest(
            turn_id=turn_id,
            agent_response="Response 2",
            status=TurnStatus.IN_PROGRESS,
            llm_duration_ms=200,
        )

        # Execute updates concurrently
        results = await asyncio.gather(
            memory_manager.update_turn(update1),
            memory_manager.update_turn(update2),
            return_exceptions=True,
        )

        # Both should succeed (last write wins)
        assert all(r is True for r in results if not isinstance(r, Exception))

        # Verify final state
        turn = await memory_manager.get_turn_by_id(turn_id)
        assert turn is not None
        # One of the responses should have won
        assert turn.agent_response in ["Response 1", "Response 2"]

    @pytest.mark.asyncio
    async def test_turn_status_transitions(self, memory_manager: MemoryManager) -> None:
        """Test valid and invalid turn status transitions."""
        # Create turn
        turn_id = await memory_manager.create_turn(
            TurnCreationRequest(user_query="Status transition test", agent_id="status-agent")
        )

        # Verify initial status
        turn = await memory_manager.get_turn_by_id(turn_id)
        assert turn is not None
        assert turn.status == TurnStatus.IN_PROGRESS

        # Valid transition: IN_PROGRESS -> COMPLETED
        await memory_manager.complete_turn(
            TurnCompletionRequest(
                turn_id=turn_id, agent_response="Task completed", status=TurnStatus.COMPLETED
            )
        )

        turn = await memory_manager.get_turn_by_id(turn_id)
        assert turn is not None
        assert turn.status == TurnStatus.COMPLETED

        # Attempting to update completed turn should still work (idempotent)
        result = await memory_manager.update_turn(
            TurnUpdateRequest(
                turn_id=turn_id,
                agent_response="Modified after completion",
                status=TurnStatus.IN_PROGRESS,
            )
        )
        assert result is True  # Update succeeds

        # Status can be changed back
        turn = await memory_manager.get_turn_by_id(turn_id)
        assert turn is not None
        assert turn.status == TurnStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_invalid_turn_id_handling(self, memory_manager: MemoryManager) -> None:
        """Test handling of operations with invalid turn IDs."""
        invalid_id = "non-existent-turn-id"

        # Update non-existent turn
        result = await memory_manager.update_turn(
            TurnUpdateRequest(
                turn_id=invalid_id, agent_response="This should fail", status=TurnStatus.COMPLETED
            )
        )
        assert result is False  # Update should fail gracefully

        # Get non-existent turn
        turn = await memory_manager.get_turn_by_id(invalid_id)
        assert turn is None

        # Get tools for non-existent turn
        tools = await memory_manager.get_tool_usage_for_turn(invalid_id)
        assert tools == []

    @pytest.mark.asyncio
    async def test_large_content_handling(self, memory_manager: MemoryManager) -> None:
        """Test handling of very large content."""
        # Create large content
        large_query = "Analyze this data: " + "x" * 10000  # 10KB query
        large_response = "Analysis results: " + "y" * 50000  # 50KB response

        # Should handle large content
        turn_id = await memory_manager.record_conversation_turn(
            user_query=large_query, agent_response=large_response, agent_id="large-content-agent"
        )

        # Verify storage
        turn = await memory_manager.get_turn_by_id(turn_id)
        assert turn is not None
        assert len(turn.user_query) > 10000
        assert len(turn.agent_response) > 50000

        # Test token estimation for large content
        token_count = memory_manager.get_turn_token_count(turn)
        # Should be roughly (10000 + 50000) / 4 = 15000 tokens
        assert 12000 < token_count < 18000

    @pytest.mark.asyncio
    async def test_pagination_support(self, memory_manager: MemoryManager) -> None:
        """Test pagination for large result sets."""
        # Create many turns
        num_turns = 25
        for i in range(num_turns):
            await memory_manager.record_conversation_turn(
                user_query=f"Query {i}", agent_response=f"Response {i}", agent_id="pagination-agent"
            )

        # Test limit
        limited_turns = await memory_manager.get_all_turns(limit=10)
        assert len(limited_turns) == 10

        # Test offset
        offset_turns = await memory_manager.get_all_turns(limit=10, offset=10)
        assert len(offset_turns) == 10

        # Ensure no overlap between pages
        limited_ids = {t.id for t in limited_turns}
        offset_ids = {t.id for t in offset_turns}
        assert limited_ids.isdisjoint(offset_ids)

        # Test final page
        final_page = await memory_manager.get_all_turns(limit=10, offset=20)
        assert len(final_page) == 5  # Only 5 turns left


class TestConversationEnhancements:
    """Test conversation storage with entity tracking."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve_enhanced_turn(self, memory_manager: MemoryManager) -> None:
        """Test storing and retrieving turns with entity fields."""
        # Store a user-to-agent turn
        turn_id = await memory_manager.record_conversation_turn(
            user_query="What's the weather?",
            agent_response="Let me check the weather for you.",
            agent_id="METAGEN",
            source_entity="USER",
            target_entity="METAGEN",
            conversation_type="USER_AGENT",
        )

        # Retrieve and verify
        turns = await memory_manager.get_recent_turns(limit=1)
        assert len(turns) == 1

        turn = turns[0]
        assert turn.id == turn_id
        assert turn.source_entity == "USER"
        assert turn.target_entity == "METAGEN"
        assert turn.conversation_type == "USER_AGENT"

    @pytest.mark.asyncio
    async def test_agent_to_agent_storage(self, memory_manager: MemoryManager) -> None:
        """Test agent-to-agent conversation storage."""
        # MetaAgent delegates to TaskAgent
        turn_id = await memory_manager.record_conversation_turn(
            user_query="execute_task: Generate weekly report",
            agent_response="Starting weekly report generation...",
            agent_id="TASK_EXECUTION_report_gen",
            source_entity="METAGEN",
            target_entity="TASK_EXECUTION_report_gen",
            conversation_type="AGENT_AGENT",
            task_id="report_gen_task",
        )

        # Verify storage
        turn = await memory_manager.get_turn_by_id(turn_id)
        assert turn is not None
        assert turn.source_entity == "METAGEN"
        assert turn.target_entity == "TASK_EXECUTION_report_gen"
        assert turn.task_id == "report_gen_task"

    @pytest.mark.asyncio
    async def test_default_entity_values(self, memory_manager: MemoryManager) -> None:
        """Test default values when entity fields not specified."""
        # Store without specifying entity fields
        turn_id = await memory_manager.record_conversation_turn(
            user_query="Hello", agent_response="Hi there!", agent_id="METAGEN"
        )

        turn = await memory_manager.get_turn_by_id(turn_id)
        assert turn is not None
        assert turn.source_entity == "USER"  # Default
        assert turn.target_entity == "METAGEN"  # Defaults to agent_id
        assert turn.conversation_type == "USER_AGENT"  # Default


class TestToolUsageLifecycle:
    """Test complete tool usage lifecycle."""

    @pytest.mark.asyncio
    async def test_tool_proposal_and_approval(self, memory_manager: MemoryManager) -> None:
        """Test tool proposal and approval flow."""
        # Create conversation turn
        turn_id = await memory_manager.record_conversation_turn(
            user_query="Search my emails for urgent messages",
            agent_response="I'll search your emails for urgent messages.",
            agent_id="METAGEN",
        )

        # Record tool proposal
        tool_id = await memory_manager.record_tool_usage(
            turn_id=turn_id,
            agent_id="METAGEN",
            tool_name="gmail_search",
            tool_args={"query": "is:urgent"},
            requires_approval=True,
        )

        # Check pending status
        pending = await memory_manager.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0].id == tool_id

        # Approve tool
        success = await memory_manager.update_tool_approval(tool_id, approved=True)
        assert success

        # Verify approval
        # Get tool usage through the turn
        tools = await memory_manager.get_tool_usage_for_turn(turn_id)
        tool = next((t for t in tools if t.id == tool_id), None)
        assert tool is not None
        assert tool.user_decision == "APPROVED"
        assert tool.execution_status == ToolUsageStatus.APPROVED
        assert tool.decision_timestamp is not None

    @pytest.mark.asyncio
    async def test_tool_rejection_with_feedback(self, memory_manager: MemoryManager) -> None:
        """Test tool rejection with user feedback."""
        # Create turn
        turn_id = await memory_manager.record_conversation_turn(
            user_query="Delete all files",
            agent_response="I'll delete all files.",
            agent_id="METAGEN",
        )

        # Record dangerous tool
        tool_id = await memory_manager.record_tool_usage(
            turn_id=turn_id,
            agent_id="METAGEN",
            tool_name="delete_files",
            tool_args={"pattern": "*"},
            requires_approval=True,
        )

        # Reject with feedback
        success = await memory_manager.update_tool_approval(
            tool_id,
            approved=False,
            user_feedback="Too dangerous! Please be more specific about which files.",
        )
        assert success

        # Verify rejection
        # Get tool usage through the turn
        tools = await memory_manager.get_tool_usage_for_turn(turn_id)
        tool = next((t for t in tools if t.id == tool_id), None)
        assert tool is not None
        assert tool.user_decision == "REJECTED"
        assert tool.user_feedback == "Too dangerous! Please be more specific about which files."
        assert tool.execution_status == ToolUsageStatus.REJECTED

    @pytest.mark.asyncio
    async def test_tool_execution_tracking(self, memory_manager: MemoryManager) -> None:
        """Test tracking tool execution from start to finish."""
        # Create turn
        turn_id = await memory_manager.record_conversation_turn(
            user_query="What time is it?",
            agent_response="Let me check the time.",
            agent_id="METAGEN",
        )

        # Record tool (no approval needed)
        tool_id = await memory_manager.record_tool_usage(
            turn_id=turn_id,
            agent_id="METAGEN",
            tool_name="get_current_time",
            tool_args={},
            requires_approval=False,
        )

        # Start execution
        await memory_manager.start_tool_execution(tool_id)

        # Verify executing status
        # Get tool usage through the turn
        tools = await memory_manager.get_tool_usage_for_turn(turn_id)
        tool = next((t for t in tools if t.id == tool_id), None)
        assert tool is not None
        assert tool.execution_status == ToolUsageStatus.EXECUTING
        assert tool.execution_started_at is not None

        # Complete execution
        await memory_manager.complete_tool_execution(
            tool_id,
            success=True,
            result={"time": "3:45 PM PST", "timezone": "PST"},
            duration_ms=85.3,
            tokens_used=12,
        )

        # Verify completion

        # Get tool usage through the turn
        tools = await memory_manager.get_tool_usage_for_turn(turn_id)
        tool = next((t for t in tools if t.id == tool_id), None)
        assert tool is not None
        assert tool.execution_status == ToolUsageStatus.SUCCESS
        assert tool.execution_completed_at is not None
        assert tool.execution_result == {"time": "3:45 PM PST", "timezone": "PST"}
        assert tool.duration_ms == 85.3
        assert tool.tokens_used == 12


class TestToolUsageQueries:
    """Test querying tool usage data."""

    @pytest.mark.asyncio
    async def test_get_tools_by_turn(self, memory_manager: MemoryManager) -> None:
        """Test retrieving all tools for a turn."""
        # Create turn
        turn_id = await memory_manager.record_conversation_turn(
            user_query="Check calendar and send email",
            agent_response="I'll check your calendar and send the email.",
            agent_id="METAGEN",
        )

        # Record multiple tools
        tool1_id = await memory_manager.record_tool_usage(
            turn_id=turn_id,
            agent_id="METAGEN",
            tool_name="calendar_check",
            tool_args={"date": "today"},
        )

        tool2_id = await memory_manager.record_tool_usage(
            turn_id=turn_id,
            agent_id="METAGEN",
            tool_name="send_email",
            tool_args={"to": "test@example.com"},
        )

        # Execute first tool
        await memory_manager.start_tool_execution(tool1_id)
        await memory_manager.complete_tool_execution(tool1_id, success=True, result={"events": 3})

        # Execute second tool
        await memory_manager.start_tool_execution(tool2_id)
        await memory_manager.complete_tool_execution(tool2_id, success=True, result={"sent": True})

        # Query all tools for turn
        tools = await memory_manager.get_tool_usage_for_turn(turn_id)
        assert len(tools) == 2

        # Should be ordered by creation
        assert tools[0].tool_name == "calendar_check"
        assert tools[1].tool_name == "send_email"

        # Both should be successful
        assert all(t.execution_status == ToolUsageStatus.SUCCESS for t in tools)

    @pytest.mark.asyncio
    async def test_filter_pending_by_entity(self, memory_manager: MemoryManager) -> None:
        """Test filtering pending approvals by entity."""
        # Create turns for different entities
        turn1 = await memory_manager.record_conversation_turn(
            user_query="Meta task", agent_response="Processing...", agent_id="METAGEN"
        )

        turn2 = await memory_manager.record_conversation_turn(
            user_query="Task execution",
            agent_response="Executing...",
            agent_id="TASK_EXECUTION_123",
            source_entity="METAGEN",
            target_entity="TASK_EXECUTION_123",
            conversation_type="AGENT_AGENT",
        )

        # Create pending tools for each
        await memory_manager.record_tool_usage(
            turn_id=turn1,
            agent_id="METAGEN",
            tool_name="meta_tool",
            tool_args={},
            requires_approval=True,
        )

        await memory_manager.record_tool_usage(
            turn_id=turn2,
            agent_id="TASK_EXECUTION_123",
            tool_name="task_tool",
            tool_args={},
            requires_approval=True,
        )

        # Query by entity
        meta_pending = await memory_manager.get_pending_approvals("METAGEN")
        assert len(meta_pending) == 1
        assert meta_pending[0].tool_name == "meta_tool"

        task_pending = await memory_manager.get_pending_approvals("TASK_EXECUTION_123")
        assert len(task_pending) == 1
        assert task_pending[0].tool_name == "task_tool"

        # Query all
        all_pending = await memory_manager.get_pending_approvals()
        assert len(all_pending) == 2


class TestDatabaseConsistency:
    """Test database-level consistency and relationships."""

    @pytest.mark.asyncio
    async def test_tool_turn_relationship(self, storage_backend: MemoryBackend) -> None:
        """Test relationship between turns and tools at database level."""
        from sqlalchemy.future import select

        async with storage_backend.async_session() as session:  # type: ignore[attr-defined]
            # Create turn
            turn = ConversationTurn(
                id="test-turn",
                agent_id="METAGEN",
                turn_number=1,
                timestamp=datetime.utcnow(),
                source_entity="USER",
                target_entity="METAGEN",
                conversation_type="USER_AGENT",
                user_query="Test",
                agent_response="Testing",
            )
            session.add(turn)

            # Create multiple tools
            for i in range(3):
                tool = ToolUsage(
                    id=f"tool-{i}",
                    turn_id="test-turn",
                    agent_id="METAGEN",
                    tool_name=f"tool_{i}",
                    tool_args={"index": i},
                    execution_status="SUCCESS",
                )
                session.add(tool)

            await session.commit()

            # Query with relationship using eager loading
            stmt = (
                select(ConversationTurn)
                .where(ConversationTurn.id == "test-turn")  # type: ignore[arg-type]
                .options(selectinload(ConversationTurn.tool_usages))  # type: ignore[arg-type]
            )

            result = await session.execute(stmt)
            turn_with_tools = result.scalar_one()

            # Verify relationship works
            assert len(turn_with_tools.tool_usages) == 3
            tool_names = {t.tool_name for t in turn_with_tools.tool_usages}
            assert tool_names == {"tool_0", "tool_1", "tool_2"}
