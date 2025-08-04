"""SQLite implementation of turn-based conversation storage."""

import asyncio
import logging
import uuid
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Coroutine, Optional, TypeVar

from sqlalchemy import and_, asc, delete, desc, func, text
from sqlalchemy.engine.cursor import CursorResult
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.future import select
from sqlmodel import col

from common.models import (
    CompactMemory,
    ConversationTurn,
    TaskConfig,
    ToolUsage,
    ToolUsageStatus,
    TurnStatus,
)

from .memory_backend import MemoryBackend

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_retry(
    max_attempts: int = 3, backoff_factor: float = 0.1
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    """Decorator to retry database operations on transient failures."""

    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except OperationalError as e:
                    last_exception = e
                    if "database is locked" in str(e) or "database disk image is malformed" in str(
                        e
                    ):
                        # Database locked or corrupted - retry with exponential backoff
                        wait_time = min(5.0, backoff_factor * (2**attempt))  # Cap at 5 seconds
                        logger.warning(
                            f"Database locked, retrying in {wait_time}s "
                            f"(attempt {attempt + 1}/{max_attempts})"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        # Other operational errors - don't retry
                        raise
                except IntegrityError:
                    # Integrity errors should not be retried
                    raise
                except Exception as e:
                    # Unexpected errors - log and raise
                    logger.error(f"Unexpected error in {func.__name__}: {e}")
                    raise

            # All retries exhausted
            logger.error(f"All {max_attempts} attempts failed for {func.__name__}")
            if last_exception:
                raise last_exception
            raise RuntimeError("No exception saved but all retries failed")

        return wrapper

    return decorator


class SQLiteBackend(MemoryBackend):
    """SQLite storage backend for turn-based conversations."""

    def __init__(self, db_engine: Any):
        """Initialize SQLite backend.

        Args:
            db_engine: DatabaseEngine instance
        """
        self.db_engine = db_engine
        self.async_session: Optional[async_sessionmaker[AsyncSession]] = None
        self._initialization_lock = asyncio.Lock()
        self._is_initialized = False

    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        async with self._initialization_lock:
            if self._is_initialized:
                logger.debug("SQLiteBackend already initialized, skipping")
                return

            logger.debug("🔍 SQLiteBackend.initialize() called")

            # Get session factory from DatabaseEngine
            logger.debug("🔍 Getting session factory from DatabaseEngine...")
            self.async_session = self.db_engine.get_session_factory()
            logger.debug("🔍 Session factory obtained from DatabaseEngine")

            # DatabaseEngine handles all schema creation, pragma settings, and integrity checks
            logger.debug("🔍 Schema initialization handled by DatabaseEngine")

            # Clean up any abandoned operations from improper shutdown
            await self._cleanup_abandoned_operations()

            self._is_initialized = True
            logger.info("SQLite backend initialized")

    async def _cleanup_abandoned_operations(self) -> None:
        """Clean up any in-flight operations from improper shutdown."""
        try:
            logger.info("🧹 Cleaning up abandoned operations from previous session...")

            async with self.async_session() as session:  # type: ignore[misc]
                # Update any PENDING, PENDING_APPROVAL or EXECUTING tools to ABANDONED
                result = await session.execute(
                    text("""
                    UPDATE tool_usage 
                    SET execution_status = :abandoned_status,
                        execution_error = 'Tool execution was abandoned (system shutdown)',
                        execution_completed_at = CURRENT_TIMESTAMP
                    WHERE execution_status IN (
                        :pending_status, :pending_approval_status, :executing_status
                    )
                    """),
                    {
                        "abandoned_status": ToolUsageStatus.ABANDONED.value,
                        "pending_status": ToolUsageStatus.PENDING.value,
                        "pending_approval_status": ToolUsageStatus.PENDING_APPROVAL.value,
                        "executing_status": ToolUsageStatus.EXECUTING.value,
                    },
                )

                if result.rowcount > 0:  # type: ignore[union-attr]
                    logger.warning(f"🧹 Marked {result.rowcount} abandoned tool executions")  # type: ignore[union-attr]

                # Also mark any IN_PROGRESS conversations as ABANDONED
                result = await session.execute(
                    text("""
                    UPDATE conversation_turns
                    SET status = :abandoned_status,
                        error_details = '{"error": "Conversation was abandoned (system shutdown)"}',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE LOWER(status) = LOWER(:in_progress_status)
                    """),
                    {
                        "abandoned_status": TurnStatus.ABANDONED.value,
                        "in_progress_status": TurnStatus.IN_PROGRESS.value,
                    },
                )

                if result.rowcount > 0:  # type: ignore[union-attr]
                    logger.warning(f"🧹 Marked {result.rowcount} abandoned conversations")  # type: ignore[union-attr]

                # Commit the changes
                await session.commit()

        except Exception as e:
            logger.error(f"Failed to cleanup abandoned operations: {e}")
            # Don't fail initialization if cleanup fails

    @with_retry(max_attempts=3, backoff_factor=0.1)
    async def store_turn(self, turn: ConversationTurn) -> str:
        """Store a conversation turn."""
        if not turn.id:
            turn.id = str(uuid.uuid4())

        logger.debug(
            f"💾 Storing turn: id={turn.id}, agent={turn.agent_id}, turn_number={turn.turn_number}"
        )
        logger.debug(f"   User query: {turn.user_query[:50]}...")
        logger.debug(f"   Agent response: {turn.agent_response[:50]}...")

        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            db_turn = ConversationTurn(
                id=turn.id,
                agent_id=turn.agent_id,
                turn_number=turn.turn_number,
                timestamp=turn.timestamp,
                source_entity=turn.source_entity,
                target_entity=turn.target_entity,
                conversation_type=turn.conversation_type,
                user_query=turn.user_query,
                agent_response=turn.agent_response,
                task_id=turn.task_id,
                llm_context=turn.llm_context,
                tools_used=turn.tools_used,
                total_duration_ms=turn.total_duration_ms,
                llm_duration_ms=turn.llm_duration_ms,
                tools_duration_ms=turn.tools_duration_ms,
                user_metadata=turn.user_metadata,
                agent_metadata=turn.agent_metadata,
                status=turn.status.value if hasattr(turn.status, "value") else turn.status,
                error_details=turn.error_details,
                created_at=turn.created_at,
                updated_at=turn.updated_at,
            )
            session.add(db_turn)
            await session.commit()
            logger.debug(f"✅ Turn {turn.id} committed to SQLite database")
            return turn.id

    @with_retry(max_attempts=3, backoff_factor=0.1)
    async def update_turn(self, turn_id: str, updates: dict[str, Any]) -> bool:
        """Update a conversation turn with new data."""
        logger.debug(f"💾 Updating turn: id={turn_id} with {len(updates)} fields")

        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            from sqlalchemy import update

            # Update the turn
            stmt = (
                update(ConversationTurn)
                .where(col(ConversationTurn.id) == turn_id)
                .values(**updates)
            )

            result: CursorResult = await session.execute(stmt)
            await session.commit()

            success = result.rowcount > 0
            logger.debug(f"✅ Turn {turn_id} update {'successful' if success else 'failed'}")
            return success

    async def get_turns_by_agent(
        self, agent_id: str, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get conversation turns for a specific agent."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            query = (
                select(ConversationTurn)
                .where(col(ConversationTurn.agent_id) == agent_id)
                .order_by(asc(col(ConversationTurn.turn_number)))
            )

            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            db_turns = result.scalars().all()

            return list(db_turns)

    async def get_turns_by_timerange(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[ConversationTurn]:
        """Get conversation turns within a time range."""
        logger.debug(
            f"🔍 SQLite query: start={start_time}, end={end_time}, limit={limit}, offset={offset}"
        )
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            query = select(ConversationTurn)

            conditions = []
            if start_time:
                conditions.append(col(ConversationTurn.timestamp) >= start_time)
            if end_time:
                conditions.append(col(ConversationTurn.timestamp) <= end_time)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.order_by(desc(col(ConversationTurn.timestamp)))

            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            db_turns = result.scalars().all()

            logger.debug(f"📊 SQLite returned {len(db_turns)} turns from timerange query")
            turns = list(db_turns)
            return turns

    async def get_turn_by_id(self, turn_id: str) -> Optional[ConversationTurn]:
        """Get a specific turn by its ID."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            query = select(ConversationTurn).where(col(ConversationTurn.id) == turn_id)
            result = await session.execute(query)
            db_turn = result.scalar_one_or_none()

            if db_turn:
                return db_turn
            return None

    async def get_next_turn_number(self, agent_id: str) -> int:
        """Get the next turn number for an agent."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            query = select(func.max(col(ConversationTurn.turn_number))).where(
                col(ConversationTurn.agent_id) == agent_id
            )
            result = await session.execute(query)
            max_turn = result.scalar()

            return (max_turn or 0) + 1

    async def delete_all_turns(self) -> int:
        """Delete all conversation turns and return the number of deleted records."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            # Count rows before deletion for return value
            count_result = await session.execute(select(func.count(col(ConversationTurn.id))))
            total_count = count_result.scalar()

            # Delete all turns
            delete_stmt = delete(ConversationTurn)
            await session.execute(delete_stmt)
            await session.commit()

            return total_count or 0

    # Compaction support methods
    async def mark_turns_compacted(self, turn_ids: list[str]) -> None:
        """Mark conversation turns as compacted."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            from sqlalchemy import update

            stmt = (
                update(ConversationTurn)
                .where(col(ConversationTurn.id).in_(turn_ids))
                .values(compacted=True)
            )

            await session.execute(stmt)
            await session.commit()
            logger.debug(f"Marked {len(turn_ids)} turns as compacted")

    async def get_uncompacted_turns(
        self, token_limit: Optional[int] = None, limit: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get uncompacted conversation turns."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            query = (
                select(ConversationTurn)
                .where(col(ConversationTurn.compacted).is_(False))
                .order_by(col(ConversationTurn.timestamp).asc())
            )

            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            db_turns = result.scalars().all()

            turns = list(db_turns)

            # Apply token limit if specified (this would ideally be done in SQL)
            if token_limit and turns:
                # For now, return all and let the manager handle token filtering
                pass

            return turns

    # Compact Memory operations
    async def store_compact_memory(self, compact_memory: CompactMemory) -> str:
        """Store a compact memory and return its ID."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            db_compact = CompactMemory(
                id=compact_memory.id,
                created_at=compact_memory.created_at,
                start_time=compact_memory.start_time,
                end_time=compact_memory.end_time,
                session_ids=compact_memory.task_ids,  # Using task_ids from CompactMemory model
                summary=compact_memory.summary,
                key_points=compact_memory.key_points,
                entities=compact_memory.entities,
                semantic_labels=compact_memory.semantic_labels,
                turn_count=compact_memory.turn_count,
                token_count=compact_memory.token_count,
                compressed_token_count=compact_memory.compressed_token_count,
                processed=compact_memory.processed,
            )

            session.add(db_compact)
            await session.commit()
            logger.debug(f"Stored compact memory {compact_memory.id}")

            return compact_memory.id

    async def get_compact_memories_by_timerange(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        processed: Optional[bool] = None,
        limit: Optional[int] = None,
    ) -> list[CompactMemory]:
        """Get compact memories within a time range."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            query = select(CompactMemory)

            conditions = []
            if start_time:
                conditions.append(col(CompactMemory.created_at) >= start_time)
            if end_time:
                conditions.append(col(CompactMemory.created_at) <= end_time)
            if processed is not None:
                conditions.append(col(CompactMemory.processed) == processed)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.order_by(desc(col(CompactMemory.created_at)))

            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            db_compacts = result.scalars().all()

            return list(db_compacts)

    async def mark_compact_memory_processed(self, compact_id: str) -> None:
        """Mark a compact memory as processed."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            from sqlalchemy import update

            stmt = (
                update(CompactMemory)
                .where(col(CompactMemory.id) == compact_id)
                .values(processed=True)
            )

            await session.execute(stmt)
            await session.commit()
            logger.debug(f"Marked compact memory {compact_id} as processed")

    async def get_all_tasks(self, limit: int = 50) -> list[TaskConfig]:
        """Get all tasks with optional limit."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            query = select(TaskConfig).order_by(desc(col(TaskConfig.created_at)))
            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            db_tasks = result.scalars().all()

            return list(db_tasks)

    async def vacuum(self) -> None:
        """Vacuum the database to reclaim space and optimize performance."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        logger.info("Starting database vacuum operation")
        async with self.async_session() as session:
            await session.execute(text("VACUUM"))
            await session.commit()
        logger.info("Database vacuum completed")

    async def checkpoint(self, mode: str = "PASSIVE") -> dict:
        """Perform WAL checkpoint.

        Args:
            mode: Checkpoint mode - PASSIVE, FULL, RESTART, or TRUNCATE

        Returns:
            Dict with checkpoint statistics
        """
        valid_modes = ["PASSIVE", "FULL", "RESTART", "TRUNCATE"]
        if mode not in valid_modes:
            raise ValueError(f"Invalid checkpoint mode: {mode}")

        logger.info(f"Starting WAL checkpoint ({mode} mode)")
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            result = await session.execute(text(f"PRAGMA wal_checkpoint({mode})"))
            row = result.first()

            stats = {
                "busy": bool(row[0]) if row and len(row) >= 3 else False,
                "pages_written": row[1] if row and len(row) >= 3 else 0,
                "pages_in_wal": row[2] if row and len(row) >= 3 else 0,
            }

        logger.info(f"Checkpoint completed: {stats}")
        return stats

    async def get_database_stats(self) -> dict:
        """Get database statistics for monitoring."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            # Get page statistics
            page_count = await session.execute(text("PRAGMA page_count"))
            page_size = await session.execute(text("PRAGMA page_size"))
            freelist_count = await session.execute(text("PRAGMA freelist_count"))

            # Get cache statistics
            cache_size = await session.execute(text("PRAGMA cache_size"))
            cache_spill = await session.execute(text("PRAGMA cache_spill"))

            # Get WAL statistics
            wal_checkpoint = await session.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))
            wal_row = wal_checkpoint.first()

            stats = {
                "page_count": page_count.scalar(),
                "page_size": page_size.scalar(),
                "freelist_count": freelist_count.scalar(),
                "total_size_bytes": (page_count.scalar() or 0) * (page_size.scalar() or 0),
                "cache_size": cache_size.scalar(),
                "cache_spill": cache_spill.scalar(),
                "wal_pages": wal_row[2] if wal_row and len(wal_row) >= 3 else 0,
                "wal_size_bytes": (
                    (wal_row[2] * (page_size.scalar() or 0))
                    if wal_row and len(wal_row) >= 3 and page_size.scalar()
                    else 0
                ),
            }

            # Get table statistics
            tables_result = await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            tables = [row[0] for row in tables_result]

            table_stats = {}
            for table in tables:
                if not table.startswith("sqlite_"):
                    count_result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    table_stats[table] = count_result.scalar()

            stats["tables"] = table_stats

        return stats

    async def close(self) -> None:
        """Close database connections with cleanup."""
        if self._is_initialized:
            # Perform final checkpoint
            try:
                await self.checkpoint("TRUNCATE")
            except Exception as e:
                logger.warning(f"Error during final checkpoint: {e}")

            # Note: We don't dispose the engine as it's managed by DatabaseEngine
            self._is_initialized = False
            logger.info("SQLite backend closed")

    # Task Management Methods
    async def store_task(self, task: TaskConfig) -> str:
        """Store a task and return its ID."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            # Parameters are already JSON dicts in the model

            db_task = TaskConfig(
                id=task.id,
                name=task.name,
                definition=task.definition,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )

            session.add(db_task)
            await session.commit()
            logger.info(f"Stored task {task.id}: {task.name}")

            return task.id

    async def get_task(self, task_id: str) -> Optional[TaskConfig]:
        """Get a task by ID."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            query = select(TaskConfig).where(col(TaskConfig.id) == task_id)
            result = await session.execute(query)
            db_task = result.scalar_one_or_none()

            if db_task:
                return db_task
            return None

    async def update_task(self, task: TaskConfig) -> bool:
        """Update a task."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            from sqlalchemy import update

            # Parameters are already JSON dicts in the model

            stmt = (
                update(TaskConfig)
                .where(col(TaskConfig.id) == task.id)
                .values(name=task.name, definition=task.definition, updated_at=task.updated_at)
            )
            result = await session.execute(stmt)
            await session.commit()

            return result.rowcount > 0

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            from sqlalchemy import delete

            stmt = delete(TaskConfig).where(col(TaskConfig.id) == task_id)
            result = await session.execute(stmt)
            await session.commit()

            return result.rowcount > 0

    # Tool Usage Methods

    @with_retry(max_attempts=3, backoff_factor=0.1)
    async def store_tool_usage(self, tool_usage: ToolUsage) -> str:
        """Store a tool usage record."""
        if not tool_usage.id:
            tool_usage.id = str(uuid.uuid4())

        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            db_tool_usage = ToolUsage(
                id=tool_usage.id,
                turn_id=tool_usage.turn_id,
                agent_id=tool_usage.agent_id,
                tool_name=tool_usage.tool_name,
                tool_args=tool_usage.tool_args,
                tool_call_id=tool_usage.tool_call_id,
                requires_approval=tool_usage.requires_approval,
                user_decision=tool_usage.user_decision,
                user_feedback=tool_usage.user_feedback,
                decision_timestamp=tool_usage.decision_timestamp,
                execution_started_at=tool_usage.execution_started_at,
                execution_completed_at=tool_usage.execution_completed_at,
                execution_status=tool_usage.execution_status,
                execution_result=tool_usage.execution_result,
                execution_error=tool_usage.execution_error,
                duration_ms=tool_usage.duration_ms,
                tokens_used=tool_usage.tokens_used,
                created_at=tool_usage.created_at,
                updated_at=tool_usage.updated_at,
            )
            session.add(db_tool_usage)
            await session.commit()
            return tool_usage.id

    async def get_tool_usage(self, tool_usage_id: str) -> Optional[ToolUsage]:
        """Get a tool usage record by ID."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            stmt = select(ToolUsage).where(col(ToolUsage.id) == tool_usage_id)
            result = await session.execute(stmt)
            db_model = result.scalar_one_or_none()

            if db_model:
                return db_model
            return None

    @with_retry(max_attempts=3, backoff_factor=0.1)
    async def update_tool_usage(self, tool_usage_id: str, updates: dict[str, Any]) -> bool:
        """Update a tool usage record."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            from sqlalchemy import update

            # Add updated_at timestamp
            updates["updated_at"] = datetime.utcnow()

            stmt = update(ToolUsage).where(col(ToolUsage.id) == tool_usage_id).values(**updates)
            result = await session.execute(stmt)
            await session.commit()

            return result.rowcount > 0

    async def get_tool_usage_by_turn(self, turn_id: str) -> list[ToolUsage]:
        """Get all tool usage records for a conversation turn."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            stmt = (
                select(ToolUsage)
                .where(col(ToolUsage.turn_id) == turn_id)
                .order_by(col(ToolUsage.created_at))
            )

            result = await session.execute(stmt)
            db_models = result.scalars().all()

            return list(db_models)

    async def get_pending_tool_approvals(self, agent_id: Optional[str] = None) -> list[ToolUsage]:
        """Get tool usage records pending user approval."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            stmt = select(ToolUsage).where(
                and_(
                    col(ToolUsage.execution_status) == "PENDING",
                    col(ToolUsage.requires_approval).is_(True),
                )
            )

            if agent_id:
                stmt = stmt.where(col(ToolUsage.agent_id) == agent_id)

            stmt = stmt.order_by(col(ToolUsage.created_at))

            result = await session.execute(stmt)
            db_models = result.scalars().all()

            return list(db_models)

    async def get_recent_tool_usage(
        self, tool_name: Optional[str] = None, agent_id: Optional[str] = None, limit: int = 10
    ) -> list[ToolUsage]:
        """Get recent tool usage records."""
        if not self.async_session:
            raise RuntimeError("Backend not initialized")

        async with self.async_session() as session:
            stmt = select(ToolUsage).order_by(desc(col(ToolUsage.created_at)))

            if tool_name:
                stmt = stmt.filter(col(ToolUsage.tool_name) == tool_name)
            if agent_id:
                stmt = stmt.filter(col(ToolUsage.agent_id) == agent_id)

            stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            db_models = result.scalars().all()

            return list(db_models)

    async def get_turns_by_session(
        self, session_id: str, limit: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get turns by session ID."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            stmt = (
                select(ConversationTurn)
                .where(col(ConversationTurn.agent_id) == session_id)
                .order_by(col(ConversationTurn.turn_number))
            )

            if limit:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            db_models = result.scalars().all()

            return list(db_models)
