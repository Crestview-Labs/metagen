"""Tests for the ToolTracker module."""

from unittest.mock import AsyncMock

import pytest

from agents.tool_tracker import ToolExecutionStage, ToolTracker, TrackedTool
from common.types import ToolCallResult


@pytest.fixture
def mock_memory_manager() -> AsyncMock:
    """Create a mock memory manager."""
    manager = AsyncMock()
    manager.record_tool_usage = AsyncMock(return_value="tool_usage_123")
    manager.start_tool_execution = AsyncMock()
    manager.update_tool_approval = AsyncMock()
    manager.complete_tool_execution = AsyncMock()
    return manager


@pytest.fixture
def tracker(mock_memory_manager: AsyncMock) -> ToolTracker:
    """Create a ToolTracker instance with mock memory manager."""
    return ToolTracker(
        memory_manager=mock_memory_manager,
        agent_id="test_agent",
        max_tools_per_turn=10,
        max_repeated_calls=3,
    )


@pytest.fixture
def sample_tool() -> TrackedTool:
    """Create a sample TrackedTool."""
    return TrackedTool(
        tool_id="tool_123",
        tool_name="test_tool",
        tool_args={"arg1": "value1"},
        stage=ToolExecutionStage.PENDING_APPROVAL,
        agent_id="test_agent",
        turn_id="turn_123",
    )


class TestToolTracker:
    """Test suite for ToolTracker."""

    async def test_add_tool(
        self, tracker: ToolTracker, sample_tool: TrackedTool, mock_memory_manager: AsyncMock
    ) -> None:
        """Test adding a tool to the tracker."""
        await tracker.add_tool(sample_tool)

        # Verify tool is tracked
        assert tracker.get_tool("tool_123") == sample_tool

        # Verify database record was created
        mock_memory_manager.record_tool_usage.assert_called_once_with(
            turn_id="turn_123",
            agent_id="test_agent",
            tool_name="test_tool",
            tool_args={"arg1": "value1"},
            requires_approval=True,
        )

        # Verify tool_usage_id was set
        assert sample_tool.tool_usage_id == "tool_usage_123"

    async def test_add_tool_without_memory_manager(self, sample_tool: TrackedTool) -> None:
        """Test adding a tool without a memory manager."""
        tracker = ToolTracker(agent_id="test_agent")
        await tracker.add_tool(sample_tool)

        # Should still track the tool
        assert tracker.get_tool("tool_123") == sample_tool
        # But no tool_usage_id should be set
        assert sample_tool.tool_usage_id is None

    async def test_get_tool(self, tracker: ToolTracker, sample_tool: TrackedTool) -> None:
        """Test getting a tool by ID."""
        await tracker.add_tool(sample_tool)

        # Should find the tool
        retrieved = tracker.get_tool("tool_123")
        assert retrieved == sample_tool

        # Should return None for non-existent tool
        assert tracker.get_tool("non_existent") is None

    async def test_remove_tool(self, tracker: ToolTracker, sample_tool: TrackedTool) -> None:
        """Test removing a tool from tracking."""
        await tracker.add_tool(sample_tool)

        # Remove the tool
        removed = tracker.remove_tool("tool_123")
        assert removed == sample_tool

        # Tool should no longer be tracked
        assert tracker.get_tool("tool_123") is None

        # Removing non-existent tool returns None
        assert tracker.remove_tool("non_existent") is None

    async def test_update_stage_to_executing(
        self, tracker: ToolTracker, sample_tool: TrackedTool, mock_memory_manager: AsyncMock
    ) -> None:
        """Test updating tool stage to EXECUTING."""
        await tracker.add_tool(sample_tool)

        # Update to EXECUTING
        success = await tracker.update_stage("tool_123", ToolExecutionStage.EXECUTING)

        assert success
        assert sample_tool.stage == ToolExecutionStage.EXECUTING
        mock_memory_manager.start_tool_execution.assert_called_once_with("tool_usage_123")

    async def test_update_stage_to_approved(
        self, tracker: ToolTracker, sample_tool: TrackedTool, mock_memory_manager: AsyncMock
    ) -> None:
        """Test updating tool stage to APPROVED."""
        await tracker.add_tool(sample_tool)

        # Update to APPROVED
        success = await tracker.update_stage(
            "tool_123", ToolExecutionStage.APPROVED, user_feedback="Looks good"
        )

        assert success
        assert sample_tool.stage == ToolExecutionStage.APPROVED
        mock_memory_manager.update_tool_approval.assert_called_once_with(
            "tool_usage_123", approved=True, user_feedback="Looks good"
        )

    async def test_update_stage_to_rejected(
        self, tracker: ToolTracker, sample_tool: TrackedTool, mock_memory_manager: AsyncMock
    ) -> None:
        """Test updating tool stage to REJECTED."""
        await tracker.add_tool(sample_tool)

        # Update to REJECTED
        success = await tracker.update_stage(
            "tool_123", ToolExecutionStage.REJECTED, user_feedback="Not safe"
        )

        assert success
        assert sample_tool.stage == ToolExecutionStage.REJECTED
        assert sample_tool.user_feedback == "Not safe"
        mock_memory_manager.update_tool_approval.assert_called_once_with(
            "tool_usage_123", approved=False, user_feedback="Not safe"
        )

    async def test_update_stage_to_completed(
        self, tracker: ToolTracker, sample_tool: TrackedTool, mock_memory_manager: AsyncMock
    ) -> None:
        """Test updating tool stage to COMPLETED."""
        await tracker.add_tool(sample_tool)

        result = ToolCallResult(
            tool_call_id="tool_123",
            tool_name="test_tool",
            content="Success",
            is_error=False,
            error=None,
            error_type=None,
            user_display=None,
        )

        # Update to COMPLETED
        success = await tracker.update_stage(
            "tool_123", ToolExecutionStage.COMPLETED, result=result, duration_ms=100
        )

        assert success
        assert sample_tool.stage == ToolExecutionStage.COMPLETED
        assert sample_tool.result == result
        mock_memory_manager.complete_tool_execution.assert_called_once_with(
            tool_usage_id="tool_usage_123",
            success=True,
            result=result.model_dump(),  # Should be dict after conversion
            error=None,
            duration_ms=100,
        )

    async def test_update_stage_to_failed(
        self, tracker: ToolTracker, sample_tool: TrackedTool, mock_memory_manager: AsyncMock
    ) -> None:
        """Test updating tool stage to FAILED."""
        await tracker.add_tool(sample_tool)

        # Update to FAILED
        success = await tracker.update_stage(
            "tool_123", ToolExecutionStage.FAILED, error="Connection timeout", duration_ms=50
        )

        assert success
        assert sample_tool.stage == ToolExecutionStage.FAILED
        assert sample_tool.error == "Connection timeout"
        mock_memory_manager.complete_tool_execution.assert_called_once_with(
            tool_usage_id="tool_usage_123",
            success=False,
            result=None,
            error="Connection timeout",
            duration_ms=50,
        )

    async def test_update_stage_rollback_on_db_failure(
        self, tracker: ToolTracker, sample_tool: TrackedTool, mock_memory_manager: AsyncMock
    ) -> None:
        """Test that stage is rolled back if DB update fails."""
        await tracker.add_tool(sample_tool)

        # Make DB update fail
        mock_memory_manager.update_tool_approval.side_effect = Exception("DB error")

        # Try to update to APPROVED
        with pytest.raises(Exception, match="DB error"):
            await tracker.update_stage("tool_123", ToolExecutionStage.APPROVED)

        # Stage should be rolled back
        assert sample_tool.stage == ToolExecutionStage.PENDING_APPROVAL

    async def test_get_tools_by_stage(self, tracker: ToolTracker) -> None:
        """Test getting tools by stage."""
        # Add tools in different stages
        tool1 = TrackedTool(
            tool_id="tool_1",
            tool_name="tool1",
            tool_args={},
            stage=ToolExecutionStage.PENDING_APPROVAL,
        )
        tool2 = TrackedTool(
            tool_id="tool_2", tool_name="tool2", tool_args={}, stage=ToolExecutionStage.EXECUTING
        )
        tool3 = TrackedTool(
            tool_id="tool_3",
            tool_name="tool3",
            tool_args={},
            stage=ToolExecutionStage.PENDING_APPROVAL,
        )

        await tracker.add_tool(tool1)
        await tracker.add_tool(tool2)
        await tracker.add_tool(tool3)

        # Get tools by stage
        pending = tracker.get_tools_by_stage(ToolExecutionStage.PENDING_APPROVAL)
        assert len(pending) == 2
        assert tool1 in pending
        assert tool3 in pending

        executing = tracker.get_tools_by_stage(ToolExecutionStage.EXECUTING)
        assert len(executing) == 1
        assert tool2 in executing

    async def test_get_pending_approvals(
        self, tracker: ToolTracker, sample_tool: TrackedTool
    ) -> None:
        """Test getting pending approval tools."""
        await tracker.add_tool(sample_tool)

        pending = tracker.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0] == sample_tool

    async def test_count_by_stage(self, tracker: ToolTracker) -> None:
        """Test counting tools by stage."""
        # Add tools in different stages
        tools = [
            TrackedTool("t1", "tool", {}, ToolExecutionStage.PENDING_APPROVAL, AsyncMock()),
            TrackedTool("t2", "tool", {}, ToolExecutionStage.PENDING_APPROVAL, AsyncMock()),
            TrackedTool("t3", "tool", {}, ToolExecutionStage.EXECUTING, AsyncMock()),
            TrackedTool("t4", "tool", {}, ToolExecutionStage.COMPLETED, AsyncMock()),
        ]

        for tool in tools:
            await tracker.add_tool(tool)

        counts = tracker.count_by_stage()
        assert counts[ToolExecutionStage.PENDING_APPROVAL] == 2
        assert counts[ToolExecutionStage.EXECUTING] == 1
        assert counts[ToolExecutionStage.COMPLETED] == 1
        assert counts[ToolExecutionStage.FAILED] == 0

    async def test_has_pending_tools(self, tracker: ToolTracker) -> None:
        """Test checking for pending tools."""
        # No tools - should be false
        assert not tracker.has_pending_tools()

        # Add completed tool - should still be false
        completed_tool = TrackedTool("t1", "tool", {}, ToolExecutionStage.COMPLETED, AsyncMock())
        await tracker.add_tool(completed_tool)
        assert not tracker.has_pending_tools()

        # Add pending tool - should be true
        pending_tool = TrackedTool(
            "t2", "tool", {}, ToolExecutionStage.PENDING_APPROVAL, AsyncMock()
        )
        await tracker.add_tool(pending_tool)
        assert tracker.has_pending_tools()

    async def test_can_execute_tool_limits(self, tracker: ToolTracker) -> None:
        """Test tool execution limits."""
        # Should allow first execution
        can_execute, error = tracker.can_execute_tool("test_tool", {"arg": "value"})
        assert can_execute
        assert error is None

        # Add tools up to the limit
        for i in range(10):
            tool = TrackedTool(f"t{i}", "tool", {}, ToolExecutionStage.COMPLETED, AsyncMock())
            await tracker.add_tool(tool)

        # Should reject due to max tools
        can_execute, error = tracker.can_execute_tool("test_tool", {"arg": "value"})
        assert not can_execute
        assert error is not None and "Maximum tools per turn exceeded" in error

    async def test_can_execute_tool_repeated_calls(self, tracker: ToolTracker) -> None:
        """Test repeated tool call limits."""
        tool_name = "test_tool"
        tool_args = {"arg": "value"}

        # Record calls up to the limit
        for _ in range(3):
            can_execute, error = tracker.can_execute_tool(tool_name, tool_args)
            assert can_execute
            tracker.record_tool_call(tool_name, tool_args)

        # Next call should be rejected
        can_execute, error = tracker.can_execute_tool(tool_name, tool_args)
        assert not can_execute
        assert error is not None and "called too many times" in error

    async def test_tool_key_generation(self, tracker: ToolTracker) -> None:
        """Test that tool keys are generated consistently."""
        # Same args in different order should produce same key
        key1 = tracker._make_tool_key("tool", {"b": 2, "a": 1})
        key2 = tracker._make_tool_key("tool", {"a": 1, "b": 2})
        assert key1 == key2

        # Different args should produce different keys
        key3 = tracker._make_tool_key("tool", {"a": 2})
        assert key1 != key3

        # Different tool names should produce different keys
        key4 = tracker._make_tool_key("other_tool", {"a": 1, "b": 2})
        assert key1 != key4

    async def test_reset_call_history(self, tracker: ToolTracker) -> None:
        """Test resetting call history."""
        # Record some calls
        tracker.record_tool_call("tool1", {"arg": 1})
        tracker.record_tool_call("tool2", {"arg": 2})

        # Reset history
        tracker.reset_call_history()

        # Should be able to call tools again
        can_execute, _ = tracker.can_execute_tool("tool1", {"arg": 1})
        assert can_execute
