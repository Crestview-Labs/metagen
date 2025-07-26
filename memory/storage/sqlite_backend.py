"""SQLite implementation of turn-based conversation storage."""

import asyncio
import logging
import uuid
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Coroutine, Optional, TypeVar

from sqlalchemy import and_, delete, desc, func, or_, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.future import select

from db.memory_models import CompactMemoryModel, ConversationTurnModel, TaskModel, ToolUsageModel

from .api import StorageBackend
from .memory_models import CompactMemory
from .models import ConversationTurn, ToolUsage, ToolUsageStatus, TurnStatus
from .task_models import Task, TaskParameter

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


class SQLiteBackend(StorageBackend):
    """SQLite storage backend for turn-based conversations."""

    def __init__(self, db_manager: Any):
        """Initialize SQLite backend.

        Args:
            db_manager: DatabaseManager instance
        """
        self.db_manager = db_manager
        self.engine: Optional[AsyncEngine] = None
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

            # Get engine from DatabaseManager
            logger.debug("🔍 Getting async engine from DatabaseManager...")
            self.engine = await self.db_manager.get_async_engine()
            logger.debug("🔍 Async engine obtained from DatabaseManager")

            self.async_session = async_sessionmaker(self.engine, expire_on_commit=False)

            # DatabaseManager handles all schema creation, pragma settings, and integrity checks
            logger.debug("🔍 Schema initialization handled by DatabaseManager")

            self._is_initialized = True
            logger.info("SQLite backend initialized")

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
            db_turn = ConversationTurnModel(
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
                trace_id=turn.trace_id,
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
                update(ConversationTurnModel)
                .where(ConversationTurnModel.id == turn_id)
                .values(**updates)
            )

            result = await session.execute(stmt)
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
                select(ConversationTurnModel)
                .where(ConversationTurnModel.agent_id == agent_id)
                .order_by(ConversationTurnModel.turn_number.asc())
            )

            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            db_turns = result.scalars().all()

            return [self._to_pydantic(turn) for turn in db_turns]

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
            query = select(ConversationTurnModel)

            conditions = []
            if start_time:
                conditions.append(ConversationTurnModel.timestamp >= start_time)
            if end_time:
                conditions.append(ConversationTurnModel.timestamp <= end_time)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.order_by(ConversationTurnModel.timestamp.desc())

            if offset:
                query = query.offset(offset)
            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            db_turns = result.scalars().all()

            logger.debug(f"📊 SQLite returned {len(db_turns)} turns from timerange query")
            turns = [self._to_pydantic(turn) for turn in db_turns]
            return turns

    async def search_turns(
        self,
        query: str,
        search_user_queries: bool = True,
        search_agent_responses: bool = True,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[ConversationTurn]:
        """Search turns by content in user queries and/or agent responses."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            search_query = select(ConversationTurnModel)

            conditions = []
            if search_user_queries:
                conditions.append(ConversationTurnModel.user_query.contains(query))
            if search_agent_responses:
                conditions.append(ConversationTurnModel.agent_response.contains(query))

            if conditions:
                search_query = search_query.where(or_(*conditions))

            search_query = search_query.order_by(ConversationTurnModel.timestamp.desc())

            if offset:
                search_query = search_query.offset(offset)
            if limit:
                search_query = search_query.limit(limit)

            result = await session.execute(search_query)
            db_turns = result.scalars().all()

            return [self._to_pydantic(turn) for turn in db_turns]

    async def get_turn_by_id(self, turn_id: str) -> Optional[ConversationTurn]:
        """Get a specific turn by its ID."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            query = select(ConversationTurnModel).where(ConversationTurnModel.id == turn_id)
            result = await session.execute(query)
            db_turn = result.scalar_one_or_none()

            if db_turn:
                return self._to_pydantic(db_turn)
            return None

    async def get_next_turn_number(self, agent_id: str) -> int:
        """Get the next turn number for an agent."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            query = select(func.max(ConversationTurnModel.turn_number)).where(
                ConversationTurnModel.agent_id == agent_id
            )
            result = await session.execute(query)
            max_turn = result.scalar()

            return (max_turn or 0) + 1

    async def delete_all_turns(self) -> int:
        """Delete all conversation turns and return the number of deleted records."""
        async with AsyncSession(self.engine) as session:
            # Count rows before deletion for return value
            count_result = await session.execute(select(func.count(ConversationTurnModel.id)))
            total_count = count_result.scalar()

            # Delete all turns
            delete_stmt = delete(ConversationTurnModel)
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
                update(ConversationTurnModel)
                .where(ConversationTurnModel.id.in_(turn_ids))
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
                select(ConversationTurnModel)
                .where(ConversationTurnModel.compacted.is_(False))
                .order_by(ConversationTurnModel.timestamp.asc())
            )

            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            db_turns = result.scalars().all()

            turns = [self._to_pydantic(turn) for turn in db_turns]

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
            db_compact = CompactMemoryModel(
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
            query = select(CompactMemoryModel)

            conditions = []
            if start_time:
                conditions.append(CompactMemoryModel.created_at >= start_time)
            if end_time:
                conditions.append(CompactMemoryModel.created_at <= end_time)
            if processed is not None:
                conditions.append(CompactMemoryModel.processed == processed)

            if conditions:
                query = query.where(and_(*conditions))

            query = query.order_by(CompactMemoryModel.created_at.desc())

            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            db_compacts = result.scalars().all()

            return [self._compact_to_pydantic(compact) for compact in db_compacts]

    async def mark_compact_memory_processed(self, compact_id: str) -> None:
        """Mark a compact memory as processed."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            from sqlalchemy import update

            stmt = (
                update(CompactMemoryModel)
                .where(CompactMemoryModel.id == compact_id)
                .values(processed=True)
            )

            await session.execute(stmt)
            await session.commit()
            logger.debug(f"Marked compact memory {compact_id} as processed")

    async def get_all_tasks(self, limit: int = 50) -> list[Task]:
        """Get all tasks with optional limit."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            query = select(TaskModel).order_by(TaskModel.created_at.desc())
            if limit:
                query = query.limit(limit)

            result = await session.execute(query)
            db_tasks = result.scalars().all()

            return [self._task_to_pydantic(task) for task in db_tasks]

    def _task_to_pydantic(self, db_model: TaskModel) -> Task:  # type: ignore[misc]
        """Convert TaskModel to Pydantic Task."""

        # Convert input/output parameters from JSON
        input_params: list[TaskParameter] = []
        if db_model.input_parameters and isinstance(db_model.input_parameters, list):
            for param_data in db_model.input_parameters:
                if isinstance(param_data, dict):
                    input_params.append(TaskParameter(**param_data))

        output_params: list[TaskParameter] = []
        if db_model.output_parameters and isinstance(db_model.output_parameters, list):
            for param_data in db_model.output_parameters:
                if isinstance(param_data, dict):
                    output_params.append(TaskParameter(**param_data))

        return Task(  # type: ignore[call-arg]
            id=db_model.id,  # type: ignore[arg-type]
            name=db_model.name,  # type: ignore[arg-type]
            description=db_model.description,  # type: ignore[arg-type]
            instructions=db_model.instructions,  # type: ignore[arg-type]
            input_parameters=input_params,
            output_parameters=output_params,
            created_at=db_model.created_at,  # type: ignore[arg-type]
            updated_at=db_model.updated_at,  # type: ignore[arg-type]
            usage_count=db_model.usage_count or 0,  # type: ignore[arg-type]
        )

    async def vacuum(self) -> None:
        """Vacuum the database to reclaim space and optimize performance."""
        if not self.engine:
            raise RuntimeError("SQLite backend not initialized")
        logger.info("Starting database vacuum operation")
        async with self.engine.begin() as conn:
            await conn.execute(text("VACUUM"))
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
        if not self.engine:
            raise RuntimeError("SQLite backend not initialized")
        async with self.engine.begin() as conn:
            result = await conn.execute(text(f"PRAGMA wal_checkpoint({mode})"))
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
        if not self.engine:
            raise RuntimeError("SQLite backend not initialized")
        async with self.engine.begin() as conn:
            # Get page statistics
            page_count = await conn.execute(text("PRAGMA page_count"))
            page_size = await conn.execute(text("PRAGMA page_size"))
            freelist_count = await conn.execute(text("PRAGMA freelist_count"))

            # Get cache statistics
            cache_size = await conn.execute(text("PRAGMA cache_size"))
            cache_spill = await conn.execute(text("PRAGMA cache_spill"))

            # Get WAL statistics
            wal_checkpoint = await conn.execute(text("PRAGMA wal_checkpoint(PASSIVE)"))
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
            tables_result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            tables = [row[0] for row in tables_result]

            table_stats = {}
            for table in tables:
                if not table.startswith("sqlite_"):
                    count_result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    table_stats[table] = count_result.scalar()

            stats["tables"] = table_stats

        return stats

    async def close(self) -> None:
        """Close database connections with cleanup."""
        if self._is_initialized and self.engine:
            # Perform final checkpoint
            try:
                await self.checkpoint("TRUNCATE")
            except Exception as e:
                logger.warning(f"Error during final checkpoint: {e}")

            # Close engine
            await self.engine.dispose()
            self._is_initialized = False
            logger.info("SQLite backend closed")

    def _compact_to_pydantic(self, db_model: CompactMemoryModel) -> CompactMemory:
        """Convert CompactMemoryModel to Pydantic model."""
        return CompactMemory(  # type: ignore[call-arg]
            id=db_model.id,  # type: ignore[arg-type]
            created_at=db_model.created_at,  # type: ignore[arg-type]
            start_time=db_model.start_time,  # type: ignore[arg-type]
            end_time=db_model.end_time,  # type: ignore[arg-type]
            task_ids=db_model.session_ids or [],  # type: ignore[arg-type] # db model uses session_ids, pydantic uses task_ids
            summary=db_model.summary,  # type: ignore[arg-type]
            key_points=db_model.key_points or [],  # type: ignore[arg-type]
            entities=db_model.entities or {},  # type: ignore[arg-type]
            semantic_labels=db_model.semantic_labels or [],  # type: ignore[arg-type]
            turn_count=db_model.turn_count or 0,  # type: ignore[arg-type]
            token_count=db_model.token_count or 0,  # type: ignore[arg-type]
            compressed_token_count=db_model.compressed_token_count or 0,  # type: ignore[arg-type]
            processed=db_model.processed or False,  # type: ignore[arg-type]
        )

    def _to_pydantic(self, db_model: ConversationTurnModel) -> ConversationTurn:
        """Convert SQLAlchemy model to Pydantic model."""
        turn = ConversationTurn(  # type: ignore[call-arg]
            id=db_model.id,  # type: ignore[arg-type]
            agent_id=db_model.agent_id,  # type: ignore[arg-type]
            turn_number=db_model.turn_number,  # type: ignore[arg-type]
            timestamp=db_model.timestamp,  # type: ignore[arg-type]
            source_entity=db_model.source_entity,  # type: ignore[arg-type]
            target_entity=db_model.target_entity,  # type: ignore[arg-type]
            conversation_type=db_model.conversation_type,  # type: ignore[arg-type]
            user_query=db_model.user_query,  # type: ignore[arg-type]
            agent_response=db_model.agent_response,  # type: ignore[arg-type]
            task_id=db_model.task_id,  # type: ignore[arg-type]
            llm_context=db_model.llm_context,  # type: ignore[arg-type]
            tools_used=db_model.tools_used,  # type: ignore[arg-type]
            trace_id=db_model.trace_id,  # type: ignore[arg-type]
            total_duration_ms=db_model.total_duration_ms,  # type: ignore[arg-type]
            llm_duration_ms=db_model.llm_duration_ms,  # type: ignore[arg-type]
            tools_duration_ms=db_model.tools_duration_ms,  # type: ignore[arg-type]
            user_metadata=db_model.user_metadata or {},  # type: ignore[arg-type]
            agent_metadata=db_model.agent_metadata or {},  # type: ignore[arg-type]
            status=TurnStatus(db_model.status),
            error_details=db_model.error_details,  # type: ignore[arg-type]
            created_at=db_model.created_at,  # type: ignore[arg-type]
            updated_at=db_model.updated_at,  # type: ignore[arg-type]
        )

        # Add compacted attribute from database (always present)
        turn.compacted = db_model.compacted  # type: ignore[assignment]

        return turn

    # Task Management Methods
    async def store_task(self, task: Task) -> str:
        """Store a task and return its ID."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            # Convert TaskParameter objects to JSON
            input_params_json = []
            for param in task.input_parameters:
                input_params_json.append(
                    {
                        "name": param.name,
                        "type": param.type,
                        "description": param.description,
                        "required": param.required,
                        "default_value": param.default_value,
                        "example_value": param.example_value,
                    }
                )

            output_params_json = []
            for param in task.output_parameters:
                output_params_json.append(
                    {
                        "name": param.name,
                        "type": param.type,
                        "description": param.description,
                        "required": param.required,
                        "default_value": param.default_value,
                        "example_value": param.example_value,
                    }
                )

            db_task = TaskModel(
                id=task.id,
                name=task.name,
                description=task.description,
                instructions=task.instructions,
                input_parameters=input_params_json,
                output_parameters=output_params_json,
                created_at=task.created_at,
                updated_at=task.updated_at,
                usage_count=task.usage_count,
            )

            session.add(db_task)
            await session.commit()
            logger.info(f"Stored task {task.id}: {task.name}")

            return task.id

    async def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            query = select(TaskModel).where(TaskModel.id == task_id)
            result = await session.execute(query)
            db_task = result.scalar_one_or_none()

            if db_task:
                return self._task_to_pydantic(db_task)
            return None

    async def update_task(self, task: Task) -> bool:
        """Update a task."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            from sqlalchemy import update

            # Convert TaskParameter objects to JSON
            input_params_json = []
            for param in task.input_parameters:
                input_params_json.append(
                    {
                        "name": param.name,
                        "type": param.type,
                        "description": param.description,
                        "required": param.required,
                        "default_value": param.default_value,
                        "example_value": param.example_value,
                    }
                )

            output_params_json = []
            for param in task.output_parameters:
                output_params_json.append(
                    {
                        "name": param.name,
                        "type": param.type,
                        "description": param.description,
                        "required": param.required,
                        "default_value": param.default_value,
                        "example_value": param.example_value,
                    }
                )

            stmt = (
                update(TaskModel)
                .where(TaskModel.id == task.id)
                .values(
                    name=task.name,
                    description=task.description,
                    instructions=task.instructions,
                    input_parameters=input_params_json,
                    output_parameters=output_params_json,
                    updated_at=task.updated_at,
                    usage_count=task.usage_count,
                )
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

            stmt = delete(TaskModel).where(TaskModel.id == task_id)
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
            db_tool_usage = ToolUsageModel(
                id=tool_usage.id,
                turn_id=tool_usage.turn_id,
                entity_id=tool_usage.entity_id,
                tool_name=tool_usage.tool_name,
                tool_args=tool_usage.tool_args,
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
                trace_id=tool_usage.trace_id,
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
            stmt = select(ToolUsageModel).where(ToolUsageModel.id == tool_usage_id)
            result = await session.execute(stmt)
            db_model = result.scalar_one_or_none()

            if db_model:
                return self._db_to_tool_usage(db_model)
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

            stmt = (
                update(ToolUsageModel).where(ToolUsageModel.id == tool_usage_id).values(**updates)
            )
            result = await session.execute(stmt)
            await session.commit()

            return result.rowcount > 0

    async def get_tool_usage_by_turn(self, turn_id: str) -> list[ToolUsage]:
        """Get all tool usage records for a conversation turn."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            stmt = (
                select(ToolUsageModel)
                .where(ToolUsageModel.turn_id == turn_id)
                .order_by(ToolUsageModel.created_at)
            )

            result = await session.execute(stmt)
            db_models = result.scalars().all()

            return [self._db_to_tool_usage(db_model) for db_model in db_models]

    async def get_pending_tool_approvals(self, entity_id: Optional[str] = None) -> list[ToolUsage]:
        """Get tool usage records pending user approval."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            stmt = select(ToolUsageModel).where(
                and_(
                    ToolUsageModel.execution_status == "PENDING",
                    ToolUsageModel.requires_approval.is_(True),
                )
            )

            if entity_id:
                stmt = stmt.where(ToolUsageModel.entity_id == entity_id)

            stmt = stmt.order_by(ToolUsageModel.created_at)

            result = await session.execute(stmt)
            db_models = result.scalars().all()

            return [self._db_to_tool_usage(db_model) for db_model in db_models]

    async def get_recent_tool_usage(
        self, tool_name: Optional[str] = None, entity_id: Optional[str] = None, limit: int = 10
    ) -> list[ToolUsage]:
        """Get recent tool usage records."""
        if not self.engine or not self.async_session:
            raise RuntimeError("Backend not initialized")

        async with self.async_session() as session:
            stmt = select(ToolUsageModel).order_by(desc(ToolUsageModel.created_at))

            if tool_name:
                stmt = stmt.filter(ToolUsageModel.tool_name == tool_name)
            if entity_id:
                stmt = stmt.filter(ToolUsageModel.entity_id == entity_id)

            stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            db_models = result.scalars().all()

            return [self._db_to_tool_usage(db_model) for db_model in db_models]

    def _db_to_tool_usage(self, db_model: ToolUsageModel) -> ToolUsage:
        """Convert database model to Pydantic model."""
        return ToolUsage(  # type: ignore[call-arg]
            id=db_model.id,  # type: ignore[arg-type]
            turn_id=db_model.turn_id,  # type: ignore[arg-type]
            entity_id=db_model.entity_id,  # type: ignore[arg-type]
            tool_name=db_model.tool_name,  # type: ignore[arg-type]
            tool_args=db_model.tool_args or {},  # type: ignore[arg-type]
            requires_approval=db_model.requires_approval,  # type: ignore[arg-type]
            user_decision=db_model.user_decision,  # type: ignore[arg-type]
            user_feedback=db_model.user_feedback,  # type: ignore[arg-type]
            decision_timestamp=db_model.decision_timestamp,  # type: ignore[arg-type]
            execution_started_at=db_model.execution_started_at,  # type: ignore[arg-type]
            execution_completed_at=db_model.execution_completed_at,  # type: ignore[arg-type]
            execution_status=ToolUsageStatus(db_model.execution_status)
            if db_model.execution_status
            else None,
            execution_result=db_model.execution_result,  # type: ignore[arg-type]
            execution_error=db_model.execution_error,  # type: ignore[arg-type]
            duration_ms=db_model.duration_ms,  # type: ignore[arg-type]
            tokens_used=db_model.tokens_used,  # type: ignore[arg-type]
            trace_id=db_model.trace_id,  # type: ignore[arg-type]
            created_at=db_model.created_at,  # type: ignore[arg-type]
            updated_at=db_model.updated_at,  # type: ignore[arg-type]
        )

    async def get_turns_by_session(
        self, session_id: str, limit: Optional[int] = None
    ) -> list[ConversationTurn]:
        """Get turns by session ID."""
        if not self.async_session:
            raise RuntimeError("SQLite backend not initialized")
        async with self.async_session() as session:
            stmt = (
                select(ConversationTurnModel)
                .where(ConversationTurnModel.agent_id == session_id)
                .order_by(ConversationTurnModel.turn_number)
            )

            if limit:
                stmt = stmt.limit(limit)

            result = await session.execute(stmt)
            db_models = result.scalars().all()

            return [self._to_pydantic(db_model) for db_model in db_models]
