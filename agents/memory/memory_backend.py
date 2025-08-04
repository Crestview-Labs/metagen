"""Abstract storage interface for turn-based conversation storage."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from common.models import CompactMemory, ConversationTurn, TaskConfig, ToolUsage


class MemoryBackend(ABC):
    """Abstract interface for turn-based conversation memory backends."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the storage backend."""
        pass

    @abstractmethod
    async def store_turn(self, turn: ConversationTurn) -> str:
        """Store a conversation turn and return its ID."""
        pass

    @abstractmethod
    async def get_turns_by_timerange(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[ConversationTurn]:
        """Get conversation turns within a time range."""
        pass

    @abstractmethod
    async def get_turn_by_id(self, turn_id: str) -> Optional[ConversationTurn]:
        """Get a specific turn by its ID."""
        pass

    @abstractmethod
    async def get_next_turn_number(self, session_id: str) -> int:
        """Get the next turn number for a session."""
        pass

    @abstractmethod
    async def delete_all_turns(self) -> int:
        """Delete all conversation turns and return count of deleted records."""
        pass

    # Compaction support methods
    @abstractmethod
    async def mark_turns_compacted(self, turn_ids: list[str]) -> None:
        """Mark conversation turns as compacted."""
        pass

    @abstractmethod
    async def get_uncompacted_turns(
        self, token_limit: Optional[int] = None, limit: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get uncompacted conversation turns."""
        pass

    # Compact Memory operations
    @abstractmethod
    async def store_compact_memory(self, compact_memory: CompactMemory) -> str:
        """Store a compact memory and return its ID."""
        pass

    @abstractmethod
    async def get_compact_memories_by_timerange(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        processed: Optional[bool] = None,
        limit: Optional[int] = None,
    ) -> list[CompactMemory]:
        """Get compact memories within a time range."""
        pass

    @abstractmethod
    async def mark_compact_memory_processed(self, compact_id: str) -> None:
        """Mark a compact memory as processed."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close storage connections."""
        pass

    # Task management methods
    @abstractmethod
    async def store_task(self, task: TaskConfig) -> str:
        """Store a task and return its ID."""
        pass

    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[TaskConfig]:
        """Get a task by ID."""
        pass

    @abstractmethod
    async def update_task(self, task: TaskConfig) -> bool:
        """Update a task."""
        pass

    @abstractmethod
    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        pass

    @abstractmethod
    async def get_all_tasks(self, limit: int = 50) -> list[TaskConfig]:
        """Get all tasks with optional limit."""
        pass

    # Additional methods for memory manager
    @abstractmethod
    async def update_turn(self, turn_id: str, updates: dict[str, Any]) -> bool:
        """Update a conversation turn."""
        pass

    @abstractmethod
    async def get_turns_by_session(
        self, session_id: str, limit: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get turns by session ID."""
        pass

    @abstractmethod
    async def get_turns_by_agent(
        self, agent_id: str, limit: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get turns by agent ID."""
        pass

    # Tool usage methods
    @abstractmethod
    async def store_tool_usage(self, tool_usage: "ToolUsage") -> str:
        """Store a tool usage record."""
        pass

    @abstractmethod
    async def update_tool_usage(self, tool_usage_id: str, updates: dict[str, Any]) -> bool:
        """Update a tool usage record."""
        pass

    @abstractmethod
    async def get_pending_tool_approvals(self, agent_id: Optional[str] = None) -> list["ToolUsage"]:
        """Get pending tool approvals."""
        pass

    @abstractmethod
    async def get_tool_usage_by_turn(self, turn_id: str) -> list["ToolUsage"]:
        """Get tool usage records for a turn."""
        pass

    @abstractmethod
    async def get_recent_tool_usage(
        self, tool_name: Optional[str] = None, agent_id: Optional[str] = None, limit: int = 10
    ) -> list["ToolUsage"]:
        """Get recent tool usage records, optionally filtered by tool name and entity."""
        pass
