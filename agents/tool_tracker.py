"""Tool execution tracker for Agent-side tool management.

This module provides tracking capabilities for managing multiple concurrent
tool executions within an Agent, including approval states, callbacks, and
database persistence.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from common.models import ToolExecutionStage
from common.types import ToolCallResult

logger = logging.getLogger(__name__)


@dataclass
class TrackedTool:
    """Represents a tool being tracked through its execution lifecycle."""

    tool_id: str
    tool_name: str
    tool_args: dict[str, Any]
    stage: ToolExecutionStage
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Optional fields set during lifecycle
    agent_id: Optional[str] = None
    turn_id: Optional[str] = None
    tool_usage_id: Optional[str] = None  # Database record ID
    result: Optional[ToolCallResult] = None
    error: Optional[str] = None
    user_feedback: Optional[str] = None

    # Store previous stage for rollback
    _previous_stage: Optional[ToolExecutionStage] = None

    def update_stage(self, new_stage: ToolExecutionStage) -> None:
        """Update the stage and timestamp."""
        self._previous_stage = self.stage
        self.stage = new_stage
        self.updated_at = datetime.now()

    def rollback_stage(self) -> None:
        """Rollback to previous stage (used if DB update fails)."""
        if self._previous_stage:
            self.stage = self._previous_stage
            self._previous_stage = None


class ToolTracker:
    """Manages tool execution state within an Agent with database persistence.

    This tracker manages both in-memory state and database persistence for
    tool executions, ensuring consistency between the two.
    """

    def __init__(
        self,
        memory_manager: Any = None,
        agent_id: Optional[str] = None,
        max_tools_per_turn: int = 100,
        max_repeated_calls: int = 5,
    ) -> None:
        """Initialize tracker with optional database access.

        Args:
            memory_manager: Optional memory manager for database persistence
            agent_id: ID of the agent using this tracker
            max_tools_per_turn: Maximum number of tools allowed per conversation turn
            max_repeated_calls: Maximum times the same tool can be called with same args
        """
        self._tools: dict[str, TrackedTool] = {}
        self._memory_manager = memory_manager
        self._agent_id = agent_id

        # Execution limits
        self._max_tools_per_turn = max_tools_per_turn
        self._max_repeated_calls = max_repeated_calls
        self._tool_call_history: dict[str, int] = {}  # Track repeated calls

        # Event for waiting on tool approvals
        self._approval_event: asyncio.Event = asyncio.Event()
        self._pending_approval_count: int = 0  # Track number of pending approvals

    async def add_tool(self, tracked_tool: TrackedTool) -> None:
        """Add a tool to track and create database record if available.

        Args:
            tracked_tool: The tool to start tracking
        """
        # Ensure agent_id is set
        if not tracked_tool.agent_id and self._agent_id:
            tracked_tool.agent_id = self._agent_id

        # Add to in-memory tracking
        self._tools[tracked_tool.tool_id] = tracked_tool

        # Track pending approvals
        if tracked_tool.stage == ToolExecutionStage.PENDING_APPROVAL:
            self._pending_approval_count += 1
            logger.debug(
                f"Added pending approval for {tracked_tool.tool_name}, "
                f"total pending: {self._pending_approval_count}"
            )

        # Create database record
        if self._memory_manager and tracked_tool.turn_id:
            try:
                needs_approval = tracked_tool.stage == ToolExecutionStage.PENDING_APPROVAL
                tool_usage_id = await self._memory_manager.record_tool_usage(
                    turn_id=tracked_tool.turn_id,
                    agent_id=tracked_tool.agent_id or self._agent_id or "unknown",
                    tool_name=tracked_tool.tool_name,
                    tool_args=tracked_tool.tool_args,
                    requires_approval=needs_approval,
                )
                tracked_tool.tool_usage_id = tool_usage_id
                logger.debug(f"Created DB record for tool {tracked_tool.tool_id}: {tool_usage_id}")
            except Exception as e:
                logger.error(f"Failed to create DB record for tool {tracked_tool.tool_id}: {e}")
                # Continue tracking even if DB fails

    def get_tool(self, tool_id: str) -> Optional[TrackedTool]:
        """Get a tracked tool by ID."""
        return self._tools.get(tool_id)

    def remove_tool(self, tool_id: str) -> Optional[TrackedTool]:
        """Remove and return a tool from tracking."""
        return self._tools.pop(tool_id, None)

    async def update_stage(
        self, tool_id: str, new_stage: ToolExecutionStage, **kwargs: Any
    ) -> bool:
        """Update stage and persist to DB atomically.

        Args:
            tool_id: ID of the tool to update
            new_stage: New stage to transition to
            **kwargs: Additional data for specific stage transitions:
                - result: ToolCallResult (for COMPLETED stage)
                - error: str (for FAILED stage)
                - user_feedback: str (for REJECTED stage)
                - duration_ms: int (for COMPLETED stage)

        Returns:
            True if update succeeded, False if tool not found
        """
        logger.info(
            f"🔄 ToolTracker.update_stage called: tool_id={tool_id}, "
            f"new_stage={new_stage}, kwargs={kwargs}"
        )

        tool = self.get_tool(tool_id)
        if not tool:
            logger.error(f"Tool {tool_id} not found in tracker")
            return False

        # Store old stage for potential rollback
        old_stage = tool.stage

        # Update in-memory state
        tool.update_stage(new_stage)

        # Update additional fields based on stage
        if new_stage == ToolExecutionStage.COMPLETED:
            tool.result = kwargs.get("result")
        elif new_stage == ToolExecutionStage.FAILED:
            tool.error = kwargs.get("error")
        elif new_stage == ToolExecutionStage.REJECTED:
            tool.user_feedback = kwargs.get("user_feedback")

        # Persist to DB if available
        if self._memory_manager and tool.tool_usage_id:
            try:
                if new_stage == ToolExecutionStage.EXECUTING:
                    await self._memory_manager.start_tool_execution(tool.tool_usage_id)

                elif new_stage in [ToolExecutionStage.APPROVED, ToolExecutionStage.REJECTED]:
                    # Update approval decision
                    approved = new_stage == ToolExecutionStage.APPROVED
                    feedback = kwargs.get("user_feedback", "")
                    await self._memory_manager.update_tool_approval(
                        tool.tool_usage_id, approved=approved, user_feedback=feedback
                    )

                elif new_stage in [ToolExecutionStage.COMPLETED, ToolExecutionStage.FAILED]:
                    # Complete execution
                    success = new_stage == ToolExecutionStage.COMPLETED
                    result = kwargs.get("result")
                    error = kwargs.get("error")
                    duration_ms = kwargs.get("duration_ms")

                    # Convert ToolCallResult to dict for database storage
                    if result and isinstance(result, ToolCallResult):
                        result = result.model_dump()

                    await self._memory_manager.complete_tool_execution(
                        tool_usage_id=tool.tool_usage_id,
                        success=success,
                        result=result,
                        error=error,
                        duration_ms=duration_ms,
                    )

                logger.debug(f"Updated DB for tool {tool_id}: {old_stage} -> {new_stage}")

            except Exception as e:
                # Rollback in-memory state on DB failure
                logger.error(f"Failed to update DB for tool {tool_id}: {e}")
                tool.rollback_stage()
                raise

        # Check if this resolves a pending approval
        if old_stage == ToolExecutionStage.PENDING_APPROVAL:
            if new_stage in (ToolExecutionStage.APPROVED, ToolExecutionStage.REJECTED):
                self._pending_approval_count -= 1
                logger.info(
                    f"Tool {tool.tool_name} {new_stage.value}, "
                    f"remaining pending: {self._pending_approval_count}"
                )

                # Signal ONLY when ALL approvals are complete
                if self._pending_approval_count == 0:
                    logger.info("✅ All tool approvals resolved, signaling to continue execution")
                    self._approval_event.set()
                else:
                    logger.debug(f"Still waiting for {self._pending_approval_count} approvals")

        return True

    def get_tools_by_stage(self, stage: ToolExecutionStage) -> list[TrackedTool]:
        """Get all tools in a specific stage."""
        return [tool for tool in self._tools.values() if tool.stage == stage]

    def get_pending_approvals(self) -> list[TrackedTool]:
        """Get all tools waiting for approval."""
        return self.get_tools_by_stage(ToolExecutionStage.PENDING_APPROVAL)

    def get_all_tools(self) -> list[TrackedTool]:
        """Get all tracked tools."""
        return list(self._tools.values())

    def count_by_stage(self) -> dict[ToolExecutionStage, int]:
        """Get count of tools in each stage."""
        counts = {stage: 0 for stage in ToolExecutionStage}
        for tool in self._tools.values():
            counts[tool.stage] += 1
        return counts

    def has_pending_tools(self) -> bool:
        """Check if there are any tools not in a terminal state."""
        non_terminal_stages = {
            ToolExecutionStage.PENDING_APPROVAL,
            ToolExecutionStage.APPROVED,
            ToolExecutionStage.EXECUTING,
        }
        return any(tool.stage in non_terminal_stages for tool in self._tools.values())

    def get_pending_tools(self) -> list[TrackedTool]:
        """Get all tools that are not in a terminal state.

        Returns tools that are in:
        - PENDING_APPROVAL: Waiting for user approval
        - APPROVED: Approved but not yet executed
        - EXECUTING: Currently being executed

        Returns:
            List of tracked tools in non-terminal states
        """
        non_terminal_stages = {
            ToolExecutionStage.PENDING_APPROVAL,
            ToolExecutionStage.APPROVED,
            ToolExecutionStage.EXECUTING,
        }
        return [tool for tool in self._tools.values() if tool.stage in non_terminal_stages]

    def can_execute_tool(
        self, tool_name: str, tool_args: dict[str, Any]
    ) -> tuple[bool, Optional[str]]:
        """Check if a tool can be executed based on limits.

        Args:
            tool_name: Name of the tool to check
            tool_args: Arguments for the tool

        Returns:
            Tuple of (can_execute, error_message)
        """
        # Check if tool name is valid
        if not tool_name:
            return False, "Tool name is required"

        # Check total tools limit
        total_tools = len(self._tools)
        if total_tools >= self._max_tools_per_turn:
            return False, f"Maximum tools per turn exceeded ({self._max_tools_per_turn})"

        # Check repeated calls
        tool_key = self._make_tool_key(tool_name, tool_args)
        call_count = self._tool_call_history.get(tool_key, 0)
        if call_count >= self._max_repeated_calls:
            return (
                False,
                f"Tool '{tool_name}' called too many times with same arguments "
                f"({self._max_repeated_calls})",
            )

        return True, None

    def record_tool_call(self, tool_name: str, tool_args: dict[str, Any]) -> None:
        """Record a tool call for duplicate detection.

        Args:
            tool_name: Name of the tool
            tool_args: Arguments for the tool
        """
        tool_key = self._make_tool_key(tool_name, tool_args)
        self._tool_call_history[tool_key] = self._tool_call_history.get(tool_key, 0) + 1

    def _make_tool_key(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        """Create a unique key for tool deduplication.

        Args:
            tool_name: Name of the tool
            tool_args: Arguments for the tool

        Returns:
            Unique string key for this tool call
        """
        return f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"

    def reset_call_history(self) -> None:
        """Reset the tool call history. Useful between conversation turns."""
        self._tool_call_history.clear()

    def wait_for_approvals(self) -> asyncio.Event:
        """Get the event to wait on for approvals.

        The event will be set when ALL pending approvals have been resolved
        (either approved or rejected). This allows batch processing of approvals.

        Returns:
            The asyncio.Event that will be set when all approvals are processed
        """
        return self._approval_event

    def signal_approvals_complete(self) -> None:
        """Signal that all approvals have been processed.

        This will wake up any coroutine waiting on wait_for_approvals().
        """
        self._approval_event.set()

    def get_pending_approval_count(self) -> int:
        """Get the current number of pending approvals.

        Returns:
            Number of tools waiting for approval decisions
        """
        return self._pending_approval_count
