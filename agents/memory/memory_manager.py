"""Turn-based memory manager for conversation storage and retrieval."""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from common.models import (
    CompactMemory,
    ConversationTurn,
    TaskConfig,
    ToolUsage,
    ToolUsageStatus,
    TurnStatus,
)
from common.types import (
    ToolApprovalUpdate,
    ToolExecutionComplete,
    ToolExecutionStart,
    ToolUsageRequest,
    TurnCompletionRequest,
    TurnCreationRequest,
    TurnUpdateRequest,
)
from db.engine import DatabaseEngine

from .memory_backend import MemoryBackend
from .sqlite_backend import SQLiteBackend

logger = logging.getLogger(__name__)


class MemoryManager:
    """High-level interface for managing turn-based conversation memory."""

    def __init__(self, db_engine: DatabaseEngine):
        """Initialize with a database engine.

        Args:
            db_engine: Database engine instance
        """
        logger.debug("🔍 MemoryManager.__init__() called with db_engine")
        self.db_engine = db_engine
        self._storage: MemoryBackend = SQLiteBackend(db_engine)  # Make it private
        self._current_session_id: Optional[str] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the storage backend."""
        logger.debug("🔍 MemoryManager.initialize() called")
        await self._storage.initialize()

        self._initialized = True
        logger.debug("🔍 MemoryManager initialized successfully")

    async def close(self) -> None:
        """Close storage connections."""
        await self._storage.close()

    @property
    def db_path(self) -> str:
        """Get the database path."""
        return str(self.db_engine.db_path)

    # Turn recording interface
    async def create_in_progress_turn(
        self,
        user_query: str,
        agent_id: str,
        session_id: str,
        source_entity: str = "USER",
        target_entity: Optional[str] = None,
        conversation_type: str = "USER_AGENT",
        task_id: Optional[str] = None,
        user_metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Create a conversation turn in IN_PROGRESS status.

        This is called at the start of streaming to capture the initial state.
        The turn will be updated as execution progresses.

        Returns:
            Turn ID for updating later
        """
        turn_id = str(uuid.uuid4())
        turn_number = await self._storage.get_next_turn_number(agent_id)

        # Default target_entity to agent_id if not specified
        if target_entity is None:
            target_entity = agent_id

        turn = ConversationTurn(
            id=turn_id,
            agent_id=agent_id,
            session_id=session_id,
            turn_number=turn_number,
            timestamp=datetime.utcnow(),
            source_entity=source_entity,
            target_entity=target_entity,
            conversation_type=conversation_type,
            user_query=user_query,
            agent_response="",  # Will be filled in later
            task_id=task_id,
            llm_context=None,
            total_duration_ms=None,
            llm_duration_ms=None,
            tools_duration_ms=None,
            error_details=None,
            compacted=False,
            user_metadata=user_metadata or {},
            agent_metadata={},
            status=TurnStatus.IN_PROGRESS,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        logger.debug(
            f"💾 Creating in-progress turn: id={turn_id}, agent={agent_id}, turn={turn_number}"
        )
        result = await self._storage.store_turn(turn)
        logger.debug(f"✅ In-progress turn created: {result}")
        return turn_id

    async def update_turn_completion(
        self,
        turn_id: str,
        agent_response: str,
        llm_context: Optional[dict[str, Any]] = None,
        tools_used: Optional[list[dict[str, Any]]] = None,
        tool_results: Optional[list[dict[str, Any]]] = None,
        total_duration_ms: Optional[int] = None,
        llm_duration_ms: Optional[int] = None,
        tools_duration_ms: Optional[int] = None,
        agent_metadata: Optional[dict[str, Any]] = None,
        status: TurnStatus = TurnStatus.COMPLETED,
        error_details: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Update a turn when streaming completes.

        Returns:
            True if update successful
        """
        # Set tools_used to True if any tools were used
        has_tools = bool(tools_used)

        updates = {
            "agent_response": agent_response,
            "llm_context": llm_context,
            "tools_used": has_tools,
            "total_duration_ms": total_duration_ms,
            "llm_duration_ms": llm_duration_ms,
            "tools_duration_ms": tools_duration_ms,
            "agent_metadata": agent_metadata or {},
            "status": status,
            "error_details": error_details,
            "updated_at": datetime.utcnow(),
        }

        # Remove None values
        updates = {k: v for k, v in updates.items() if v is not None}

        logger.debug(f"💾 Updating turn completion: id={turn_id}, status={status}")
        result = await self._storage.update_turn(turn_id, updates)
        logger.debug(f"✅ Turn updated: {result}")
        return result

    async def record_conversation_turn(
        self,
        user_query: str,
        agent_response: str,
        agent_id: str,
        session_id: str = "",  # Default to empty string for backwards compatibility
        source_entity: str = "USER",
        target_entity: Optional[str] = None,
        conversation_type: str = "USER_AGENT",
        task_id: Optional[str] = None,
        llm_context: Optional[dict[str, Any]] = None,
        tools_used: Optional[list[dict[str, Any]]] = None,
        tool_results: Optional[list[dict[str, Any]]] = None,
        total_duration_ms: Optional[int] = None,
        llm_duration_ms: Optional[int] = None,
        tools_duration_ms: Optional[int] = None,
        user_metadata: Optional[dict[str, Any]] = None,
        agent_metadata: Optional[dict[str, Any]] = None,
        status: TurnStatus = TurnStatus.COMPLETED,
        error_details: Optional[dict[str, Any]] = None,
    ) -> str:
        """Record a complete conversation turn.

        Args:
            user_query: User's question/request
            agent_response: Agent's final response
            agent_id: Agent identifier (METAGEN, TASK_EXECUTION_123, etc.)
            source_entity: Who initiated this turn (default: USER)
            target_entity: Who receives/processes this turn (default: agent_id)
            conversation_type: Type of conversation (USER_AGENT, AGENT_AGENT, etc.)
            task_id: Task ID if this turn is part of task execution
            llm_context: Full conversation context sent to LLM
            tools_used: List of tools invoked during this turn
            tool_results: List of tool execution results
            total_duration_ms: Total duration in milliseconds
            llm_duration_ms: LLM processing duration in milliseconds
            tools_duration_ms: Tools execution duration in milliseconds
            user_metadata: User-specific metadata
            agent_metadata: Agent-specific metadata
            status: Turn completion status
            error_details: Error information if status != completed

        Returns:
            Turn ID
        """
        turn_id = str(uuid.uuid4())
        turn_number = await self._storage.get_next_turn_number(agent_id)

        # Set tools_used to True if any tools were used
        has_tools = bool(tools_used)

        # Default target_entity to agent_id if not specified
        if target_entity is None:
            target_entity = agent_id

        turn = ConversationTurn(
            id=turn_id,
            agent_id=agent_id,
            session_id=session_id,
            turn_number=turn_number,
            timestamp=datetime.utcnow(),
            source_entity=source_entity,
            target_entity=target_entity,
            conversation_type=conversation_type,
            user_query=user_query,
            agent_response=agent_response,
            task_id=task_id,
            llm_context=llm_context,
            tools_used=has_tools,
            total_duration_ms=total_duration_ms,
            llm_duration_ms=llm_duration_ms,
            tools_duration_ms=tools_duration_ms,
            user_metadata=user_metadata or {},
            agent_metadata=agent_metadata or {},
            status=status,
            error_details=error_details,
            compacted=False,
        )

        logger.debug(
            f"💾 Recording conversation turn: id={turn_id}, agent={agent_id}, turn={turn_number}"
        )
        logger.debug(f"   User query: {user_query[:50]}...")
        logger.debug(f"   Agent response: {agent_response[:50]}...")

        result = await self._storage.store_turn(turn)
        logger.debug(f"✅ Turn saved to database: {result}")
        return result

    # Query interfaces
    async def get_session_history(
        self, session_id: str, limit: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get conversation history for a session.

        Args:
            session_id: Session to retrieve
            limit: Maximum number of turns to return

        Returns:
            List of conversation turns ordered by turn_number ascending
        """
        return await self._storage.get_turns_by_session(session_id, limit)

    async def get_recent_turns(
        self, days: int = 7, limit: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get recent conversation turns from the last N days.

        Args:
            days: Number of days to look back
            limit: Maximum number of turns to return

        Returns:
            List of recent conversation turns
        """
        start_time = datetime.utcnow() - timedelta(days=days)
        return await self._storage.get_turns_by_timerange(start_time=start_time, limit=limit)

    async def get_all_turns(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get all conversation turns.

        Args:
            limit: Maximum number of turns to return
            offset: Number of turns to skip

        Returns:
            List of all conversation turns
        """
        logger.debug(f"🗄️ Getting all turns: limit={limit}, offset={offset}")
        turns = await self._storage.get_turns_by_timerange(
            start_time=None, end_time=None, limit=limit, offset=offset
        )
        logger.debug(f"📊 Retrieved {len(turns)} turns from storage")
        return turns

    async def get_today_turns(self) -> list[ConversationTurn]:
        """Get today's conversation turns.

        Returns:
            List of today's conversation turns
        """
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return await self._storage.get_turns_by_timerange(start_time=today_start)

    async def get_turn_by_id(self, turn_id: str) -> Optional[ConversationTurn]:
        """Get a specific turn by its ID.

        Args:
            turn_id: Turn ID to retrieve

        Returns:
            Conversation turn if found, None otherwise
        """
        return await self._storage.get_turn_by_id(turn_id)

    # Session management
    def set_current_session(self, session_id: str) -> None:
        """Set the current session ID for convenience methods."""
        self._current_session_id = session_id

    def get_current_session(self) -> Optional[str]:
        """Get the current session ID."""
        return self._current_session_id

    def create_new_session(self) -> str:
        """Create a new session ID."""
        session_id = str(uuid.uuid4())
        self._current_session_id = session_id
        return session_id

    # Cleanup methods
    async def clear_all_conversations(self) -> int:
        """Clear all conversation history from storage.

        Returns:
            Number of turns deleted
        """
        if not self._initialized:
            raise RuntimeError("MemoryManager not initialized. Call initialize() first.")

        deleted_count = await self._storage.delete_all_turns()
        logger.info(f"🗄️ Cleared {deleted_count} conversation turns from storage")
        return deleted_count

    # Convenience methods for backward compatibility
    async def get_recent_conversations(
        self, days: float = 7, limit: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get recent conversation turns (compatibility method).

        Args:
            days: Number of days to look back (can be fractional)
            limit: Maximum number of turns to return

        Returns:
            List of recent conversation turns
        """
        start_time = datetime.utcnow() - timedelta(days=days)
        return await self._storage.get_turns_by_timerange(start_time=start_time, limit=limit)

    async def get_all_conversations(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get all conversation turns (compatibility method)."""
        return await self.get_all_turns(limit=limit, offset=offset)

    # Token management utilities
    def get_turn_token_count(self, turn: ConversationTurn) -> int:
        """Get actual token count from turn metadata or estimate."""
        # First try to get actual token count from LLM response metadata
        if turn.agent_metadata and "token_usage" in turn.agent_metadata:
            usage = turn.agent_metadata["token_usage"]
            if isinstance(usage, dict) and "total_tokens" in usage:
                return int(usage["total_tokens"])

        # Fallback to fast approximation
        char_count = len(turn.user_query) + len(turn.agent_response)

        # Add rough estimate for tool content
        # Note: tools_used is a boolean flag, not a list
        # Tool results are not stored in ConversationTurn model
        if turn.tools_used:
            # Add a rough estimate for tool overhead
            char_count += 500  # Approximate overhead for tool usage

        # ~4 chars per token for English text
        return max(1, char_count // 4)

    def store_token_usage_in_turn(
        self,
        turn: ConversationTurn,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        cached_tokens: Optional[int] = None,
    ) -> None:
        """Store actual token usage in turn metadata."""
        if not turn.agent_metadata:
            turn.agent_metadata = {}

        turn.agent_metadata["token_usage"] = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cached_tokens": cached_tokens,
            "recorded_at": datetime.utcnow().isoformat(),
        }

    # Compaction support methods
    async def get_uncompacted_turns(
        self, token_limit: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get uncompacted conversation turns up to token limit."""
        # Use storage backend's efficient query for uncompacted turns
        uncompacted = await self._storage.get_uncompacted_turns(token_limit=token_limit)

        if token_limit:
            # Apply token limit filtering if storage backend doesn't handle it
            selected_turns = []
            total_tokens = 0

            for turn in uncompacted:
                turn_tokens = self.get_turn_token_count(turn)
                if total_tokens + turn_tokens > token_limit:
                    break
                selected_turns.append(turn)
                total_tokens += turn_tokens

            logger.debug(
                f"Selected {len(selected_turns)} turns with {total_tokens} tokens "
                f"(limit: {token_limit})"
            )
            return selected_turns

        return uncompacted

    async def get_uncompacted_token_count(self) -> int:
        """Get total token count of uncompacted turns."""
        uncompacted_turns = await self.get_uncompacted_turns()
        total_tokens = sum(self.get_turn_token_count(turn) for turn in uncompacted_turns)
        logger.debug(
            f"Uncompacted turns total: {total_tokens} tokens across {len(uncompacted_turns)} turns"
        )
        return total_tokens

    async def get_uncompacted_turn_count(self) -> int:
        """Get count of uncompacted turns."""
        uncompacted_turns = await self.get_uncompacted_turns()
        return len(uncompacted_turns)

    async def mark_turns_compacted(self, turn_ids: list[str]) -> None:
        """Mark conversation turns as compacted using database column."""
        logger.info(f"Marking {len(turn_ids)} turns as compacted")
        await self._storage.mark_turns_compacted(turn_ids)

    async def get_turns_by_timerange(
        self, start_time: datetime, end_time: datetime, compacted: Optional[bool] = None
    ) -> list[ConversationTurn]:
        """Get turns within a time range, optionally filtered by compaction status."""
        # This will need storage backend support for compacted filter
        # For now, get all and filter (inefficient but functional)
        turns = await self._storage.get_turns_by_timerange(start_time=start_time, end_time=end_time)

        if compacted is not None:
            turns = [turn for turn in turns if getattr(turn, "compacted", False) == compacted]

        return turns

    # Compact Memory CRUD operations
    async def store_compact_memory(
        self,
        summary: str,
        key_points: list[str],
        entities: dict[str, list[str]],
        semantic_labels: list[str],
        session_ids: list[str],
        start_time: datetime,
        end_time: datetime,
        turn_count: int,
        token_count: int,
        compressed_token_count: int,
    ) -> CompactMemory:
        """Store a new compact memory."""
        compact_id = str(uuid.uuid4())

        compact_memory = CompactMemory(
            id=compact_id,
            created_at=datetime.utcnow(),
            start_time=start_time,
            end_time=end_time,
            task_ids=session_ids,  # TODO: rename parameter to task_ids
            summary=summary,
            key_points=key_points,
            entities=entities,
            semantic_labels=semantic_labels,
            turn_count=turn_count,
            token_count=token_count,
            compressed_token_count=compressed_token_count,
            processed=False,
        )

        logger.info(
            f"Storing compact memory {compact_id} covering {turn_count} turns "
            f"({token_count} → {compressed_token_count} tokens)"
        )
        await self._storage.store_compact_memory(compact_memory)
        return compact_memory

    async def get_compact_memories_by_timerange(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> list[CompactMemory]:
        """Get compact memories within a time range."""
        logger.debug(f"Getting compact memories from {start_time} to {end_time}")
        return await self._storage.get_compact_memories_by_timerange(
            start_time=start_time, end_time=end_time, limit=limit
        )

    async def get_recent_compact_memories(self, limit: int = 5) -> list[CompactMemory]:
        """Get recent compact memories."""
        return await self._storage.get_compact_memories_by_timerange(limit=limit)

    async def get_unprocessed_compact_memories(self) -> list[CompactMemory]:
        """Get compact memories that haven't been processed into semantic memories."""
        return await self._storage.get_compact_memories_by_timerange(processed=False)

    async def mark_compact_memory_processed(self, compact_id: str) -> None:
        """Mark a compact memory as processed."""
        logger.info(f"Marking compact memory {compact_id} as processed")
        await self._storage.mark_compact_memory_processed(compact_id)

    # Tool Usage Methods

    async def record_tool_usage(
        self,
        turn_id: str,
        agent_id: str,
        tool_name: str,
        tool_args: dict[str, Any],
        requires_approval: bool = False,
        tool_call_id: Optional[str] = None,
    ) -> str:
        """Record a tool usage (initially as pending)."""
        from common.models import ToolUsage

        tool_usage = ToolUsage(
            id=str(uuid.uuid4()),
            turn_id=turn_id,
            agent_id=agent_id,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_call_id=tool_call_id,
            requires_approval=requires_approval,
            execution_status=ToolUsageStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            # Optional fields with defaults
            user_decision=None,
            user_feedback=None,
            decision_timestamp=None,
            execution_started_at=None,
            execution_completed_at=None,
            execution_result=None,
            execution_error=None,
            duration_ms=None,
            tokens_used=None,
        )

        return await self._storage.store_tool_usage(tool_usage)

    async def update_tool_approval(
        self, tool_usage_id: str, approved: bool, user_feedback: Optional[str] = None
    ) -> bool:
        """Update tool usage with user approval decision."""
        updates = {
            "user_decision": "APPROVED" if approved else "REJECTED",
            "decision_timestamp": datetime.utcnow(),
            "execution_status": "APPROVED" if approved else "REJECTED",
        }

        if user_feedback:
            updates["user_feedback"] = user_feedback

        return await self._storage.update_tool_usage(tool_usage_id, updates)

    async def start_tool_execution(self, tool_usage_id: str) -> bool:
        """Mark tool as executing."""
        return await self._storage.update_tool_usage(
            tool_usage_id,
            {"execution_started_at": datetime.utcnow(), "execution_status": "EXECUTING"},
        )

    async def complete_tool_execution(
        self,
        tool_usage_id: str,
        success: bool,
        result: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None,
        tokens_used: Optional[int] = None,
    ) -> bool:
        """Mark tool execution as complete."""
        updates: dict[str, Any] = {
            "execution_completed_at": datetime.utcnow(),
            "execution_status": "SUCCESS" if success else "FAILURE",
            "duration_ms": duration_ms,
            "tokens_used": tokens_used,
        }

        if result is not None:
            updates["execution_result"] = result

        if error:
            updates["execution_error"] = error

        return await self._storage.update_tool_usage(tool_usage_id, updates)

    async def get_pending_approvals(self, agent_id: Optional[str] = None) -> list["ToolUsage"]:
        """Get tools pending user approval."""
        return await self._storage.get_pending_tool_approvals(agent_id)

    async def get_tool_usage_for_turn(self, turn_id: str) -> list["ToolUsage"]:
        """Get all tool usage for a conversation turn."""
        return await self._storage.get_tool_usage_by_turn(turn_id)

    async def get_recent_tool_usage(
        self, tool_name: Optional[str] = None, agent_id: Optional[str] = None, limit: int = 10
    ) -> list["ToolUsage"]:
        """Get recent tool usage records, optionally filtered by tool name and entity."""
        return await self._storage.get_recent_tool_usage(tool_name, agent_id, limit)

    async def get_agent_memory_stats(self, agent_id: str) -> dict[str, Any]:
        """Get memory statistics for an agent.

        Returns:
            Dictionary with memory statistics including:
            - conversation_count: Number of conversation turns
            - compact_count: Number of compact memories
            - long_term_count: Number of long-term memories
            - last_compaction: Timestamp of last compaction
            - last_long_term_build: Timestamp of last long-term memory build
        """
        # TODO: Implement full statistics gathering
        # For now, return empty stats
        return {
            "conversation_count": 0,
            "compact_count": 0,
            "long_term_count": 0,
            "last_compaction": None,
            "last_long_term_build": None,
        }

    # NEW TYPED INTERFACE METHODS

    async def create_turn(self, request: TurnCreationRequest) -> str:
        """Create a new conversation turn with typed interface."""
        return await self.create_in_progress_turn(
            user_query=request.user_query,
            agent_id=request.agent_id,
            session_id=request.session_id,
            task_id=request.task_id,
            source_entity=request.source_entity,
            target_entity=request.target_entity,
            conversation_type=request.conversation_type,
            user_metadata=request.user_metadata,
        )

    async def update_turn(self, request: TurnUpdateRequest) -> bool:
        """Update an existing turn with typed interface."""
        return await self.update_turn_completion(
            turn_id=request.turn_id,
            agent_response=request.agent_response or "",
            status=request.status or TurnStatus.COMPLETED,
            llm_context=request.llm_context,
            total_duration_ms=request.total_duration_ms,
            llm_duration_ms=request.llm_duration_ms,
            tools_duration_ms=request.tools_duration_ms,
            error_details=request.error_details,
            agent_metadata=request.agent_metadata,
        )

    async def complete_turn(self, request: TurnCompletionRequest) -> None:
        """Complete a conversation turn with typed interface."""
        # Convert tool data
        tools_used = [tc.model_dump() for tc in request.tool_calls] if request.tool_calls else None
        tool_results = (
            [tr.model_dump() for tr in request.tool_results] if request.tool_results else None
        )

        await self.update_turn_completion(
            turn_id=request.turn_id,
            agent_response=request.agent_response,
            status=request.status,
            tools_used=tools_used,
            tool_results=tool_results,
            total_duration_ms=request.total_duration_ms,
            llm_duration_ms=request.llm_duration_ms,
            tools_duration_ms=request.tools_duration_ms,
            error_details={"error": request.error_details} if request.error_details else None,
        )

    async def record_tool_use(self, request: ToolUsageRequest) -> str:
        """Record tool usage with typed interface."""
        return await self.record_tool_usage(
            tool_name=request.tool_name,
            tool_args=request.tool_args,
            turn_id=request.turn_id,
            agent_id=request.agent_id,
            requires_approval=request.requires_approval,
            tool_call_id=request.tool_call_id,
        )

    async def update_approval(self, update: ToolApprovalUpdate) -> bool:
        """Update tool approval with typed interface."""
        return await self.update_tool_approval(
            tool_usage_id=update.tool_usage_id,
            approved=update.approved,
            user_feedback=update.user_feedback,
        )

    async def start_execution(self, start: ToolExecutionStart) -> bool:
        """Start tool execution with typed interface."""
        return await self.start_tool_execution(start.tool_usage_id)

    async def complete_execution(self, complete: ToolExecutionComplete) -> bool:
        """Complete tool execution with typed interface."""
        return await self.complete_tool_execution(
            tool_usage_id=complete.tool_usage_id,
            success=not complete.result.is_error,
            result=complete.result.model_dump(),
            error=complete.result.error if complete.result.is_error else None,
            duration_ms=complete.duration_ms,
        )

    async def get_turns_by_agent(
        self, agent_id: str, limit: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get conversation turns for a specific agent.

        Args:
            agent_id: Agent identifier
            limit: Maximum number of turns to return

        Returns:
            List of conversation turns for the agent
        """
        return await self._storage.get_turns_by_agent(agent_id, limit=limit)

    # Task Management Methods

    async def create_task(self, task: "TaskConfig") -> str:
        """Create a new task definition.

        Args:
            task: TaskConfig object to store

        Returns:
            Task ID
        """
        return await self._storage.store_task(task)

    async def list_tasks(self, limit: int = 50) -> list["TaskConfig"]:
        """List all available tasks.

        Args:
            limit: Maximum number of tasks to return

        Returns:
            List of TaskConfig objects
        """
        return await self._storage.get_all_tasks(limit)

    async def get_task(self, task_id: str) -> Optional["TaskConfig"]:
        """Get a specific task by ID.

        Args:
            task_id: Task identifier

        Returns:
            TaskConfig object if found, None otherwise
        """
        return await self._storage.get_task(task_id)

    async def update_task(self, task: "TaskConfig") -> bool:
        """Update an existing task.

        Args:
            task: Updated task object

        Returns:
            True if successful, False otherwise
        """
        return await self._storage.update_task(task)

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task.

        Args:
            task_id: Task identifier

        Returns:
            True if successful, False otherwise
        """
        return await self._storage.delete_task(task_id)
