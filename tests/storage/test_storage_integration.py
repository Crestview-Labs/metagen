"""Integration tests for enhanced storage backend with tool usage."""

from datetime import datetime

import pytest

from memory.storage.api import StorageBackend
from memory.storage.manager import MemoryManager
from memory.storage.models import ToolUsageStatus
from memory.storage.sqlite_backend import SQLiteBackend


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
        turn = await memory_manager.storage.get_turn_by_id(turn_id)
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

        turn = await memory_manager.storage.get_turn_by_id(turn_id)
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
            entity_id="METAGEN",
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
        # Type assertion - we know storage is SQLiteBackend in tests
        assert isinstance(memory_manager.storage, SQLiteBackend)
        tool = await memory_manager.storage.get_tool_usage(tool_id)
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
            entity_id="METAGEN",
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
        assert isinstance(memory_manager.storage, SQLiteBackend)
        tool = await memory_manager.storage.get_tool_usage(tool_id)
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
            entity_id="METAGEN",
            tool_name="get_current_time",
            tool_args={},
            requires_approval=False,
        )

        # Start execution
        await memory_manager.start_tool_execution(tool_id)

        # Verify executing status
        assert isinstance(memory_manager.storage, SQLiteBackend)  # noqa: F823
        tool = await memory_manager.storage.get_tool_usage(tool_id)
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

        assert isinstance(memory_manager.storage, SQLiteBackend)
        tool = await memory_manager.storage.get_tool_usage(tool_id)
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
            entity_id="METAGEN",
            tool_name="calendar_check",
            tool_args={"date": "today"},
        )

        tool2_id = await memory_manager.record_tool_usage(
            turn_id=turn_id,
            entity_id="METAGEN",
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
            entity_id="METAGEN",
            tool_name="meta_tool",
            tool_args={},
            requires_approval=True,
        )

        await memory_manager.record_tool_usage(
            turn_id=turn2,
            entity_id="TASK_EXECUTION_123",
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
    async def test_tool_turn_relationship(self, storage_backend: StorageBackend) -> None:
        """Test relationship between turns and tools at database level."""
        from sqlalchemy.future import select
        from sqlalchemy.orm import selectinload

        from db.memory_models import ConversationTurnModel, ToolUsageModel

        async with storage_backend.async_session() as session:  # type: ignore[attr-defined]
            # Create turn
            turn = ConversationTurnModel(
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
                tool = ToolUsageModel(
                    id=f"tool-{i}",
                    turn_id="test-turn",
                    entity_id="METAGEN",
                    tool_name=f"tool_{i}",
                    tool_args={"index": i},
                    execution_status="SUCCESS",
                )
                session.add(tool)

            await session.commit()

            # Query with relationship using eager loading
            stmt = (
                select(ConversationTurnModel)
                .where(ConversationTurnModel.id == "test-turn")
                .options(selectinload(ConversationTurnModel.tool_usages))
            )

            result = await session.execute(stmt)
            turn_with_tools = result.scalar_one()

            # Verify relationship works
            assert len(turn_with_tools.tool_usages) == 3
            tool_names = {t.tool_name for t in turn_with_tools.tool_usages}
            assert tool_names == {"tool_0", "tool_1", "tool_2"}
