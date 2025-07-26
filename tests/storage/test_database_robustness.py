"""Robustness tests for database storage layer.

Tests focus on:
- Concurrent write operations with proper isolation
- Transaction atomicity and crash recovery
- Data integrity under load
- SQLite-specific robustness features
"""

import asyncio
import random
import string
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text

from db.manager import DatabaseManager
from db.memory_models import ConversationTurnModel, ToolUsageModel
from memory.storage.models import ConversationTurn, ToolUsage, ToolUsageStatus, TurnStatus
from memory.storage.sqlite_backend import SQLiteBackend


def create_test_turn(**kwargs: Any) -> ConversationTurn:
    """Helper to create ConversationTurn with all required fields."""
    # Ensure required fields are present
    required_fields = {
        "id": kwargs.get("id", "test-turn"),
        "agent_id": kwargs.get("agent_id", "TEST_AGENT"),
        "turn_number": kwargs.get("turn_number", 1),
        "timestamp": kwargs.get("timestamp", datetime.utcnow()),
        "source_entity": kwargs.get("source_entity", "USER"),
        "target_entity": kwargs.get("target_entity", "TEST_AGENT"),
        "conversation_type": kwargs.get("conversation_type", "USER_AGENT"),
        "user_query": kwargs.get("user_query", "Test query"),
        "agent_response": kwargs.get("agent_response", "Test response"),
        "status": kwargs.get("status", TurnStatus.COMPLETED),
    }

    # Add optional fields
    optional_fields = {
        "task_id": kwargs.get("task_id", None),
        "llm_context": kwargs.get("llm_context", None),
        "trace_id": kwargs.get("trace_id", None),
        "total_duration_ms": kwargs.get("total_duration_ms", None),
        "llm_duration_ms": kwargs.get("llm_duration_ms", None),
        "tools_duration_ms": kwargs.get("tools_duration_ms", None),
        "error_details": kwargs.get("error_details", None),
        "compacted": kwargs.get("compacted", False),
    }

    # Merge all fields
    all_fields = {**required_fields, **optional_fields}

    return ConversationTurn(**all_fields)


@pytest_asyncio.fixture
async def test_db_manager(tmp_path: Path):
    """Create a test database manager."""
    db_path = tmp_path / "test_robust.db"
    manager = DatabaseManager(db_path)
    await manager.initialize()
    yield manager
    await manager.close()


@pytest_asyncio.fixture
async def robust_backend(test_db_manager) -> AsyncGenerator[SQLiteBackend, None]:
    """Create a backend with robustness features enabled."""
    backend = SQLiteBackend(test_db_manager)
    await backend.initialize()
    yield backend
    await backend.close()


class TestConcurrentWrites:
    """Test concurrent write operations."""

    @pytest.mark.asyncio
    async def test_concurrent_turn_writes(self, robust_backend: SQLiteBackend) -> None:
        """Test multiple concurrent writes to conversation turns."""
        num_agents = 5
        turns_per_agent = 10

        async def write_turns(agent_id: str) -> None:
            """Write multiple turns for an agent."""
            for i in range(turns_per_agent):
                turn = create_test_turn(
                    id=f"{agent_id}-turn-{i + 1}",  # Add ID
                    agent_id=agent_id,
                    turn_number=i + 1,
                    timestamp=datetime.utcnow(),
                    source_entity="USER",
                    target_entity=agent_id,
                    conversation_type="USER_AGENT",
                    user_query=f"Query {i} from {agent_id}",
                    agent_response=f"Response {i} from {agent_id}",
                    status=TurnStatus.COMPLETED,
                )
                await robust_backend.store_turn(turn)

        # Create concurrent tasks
        tasks = [write_turns(f"AGENT_{i}") for i in range(num_agents)]

        # Execute concurrently
        await asyncio.gather(*tasks)

        # Verify all writes succeeded
        for i in range(num_agents):
            agent_id = f"AGENT_{i}"
            turns = await robust_backend.get_turns_by_agent(agent_id)
            assert len(turns) == turns_per_agent

            # Verify turn numbers are sequential
            turn_numbers = sorted([t.turn_number for t in turns])
            assert turn_numbers == list(range(1, turns_per_agent + 1))

    @pytest.mark.asyncio
    async def test_unique_constraint_under_concurrency(self, robust_backend: SQLiteBackend) -> None:
        """Test that unique constraints are enforced under concurrent writes."""
        agent_id = "TEST_AGENT"
        turn_number = 1

        # Track successful writes
        success_count = 0
        failure_count = 0

        async def try_write_duplicate_turn() -> None:
            """Try to write a turn with the same agent_id and turn_number."""
            nonlocal success_count, failure_count
            try:
                turn = create_test_turn(
                    id=f"duplicate-attempt-{random.random()}",  # Add unique ID
                    agent_id=agent_id,
                    turn_number=turn_number,
                    timestamp=datetime.utcnow(),
                    source_entity="USER",
                    target_entity=agent_id,
                    conversation_type="USER_AGENT",
                    user_query=f"Duplicate attempt {random.random()}",
                    agent_response="Response",
                    status=TurnStatus.COMPLETED,
                )
                await robust_backend.store_turn(turn)
                success_count += 1
            except Exception as e:
                print(f"Failed with: {e}")
                failure_count += 1

        # Try to write the same turn from multiple tasks
        num_attempts = 10
        tasks = [try_write_duplicate_turn() for _ in range(num_attempts)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Only one should succeed
        assert success_count == 1
        assert failure_count == num_attempts - 1

        # Verify only one turn exists
        turns = await robust_backend.get_turns_by_agent(agent_id)
        assert len(turns) == 1

    @pytest.mark.asyncio
    async def test_concurrent_tool_usage_updates(self, robust_backend: SQLiteBackend) -> None:
        """Test concurrent updates to tool usage records."""
        # First create a turn
        turn = create_test_turn(
            id="test-turn",
            agent_id="TEST_AGENT",
            turn_number=1,
            timestamp=datetime.utcnow(),
            source_entity="USER",
            target_entity="TEST_AGENT",
            conversation_type="USER_AGENT",
            user_query="Test query",
            agent_response="Test response",
            status=TurnStatus.COMPLETED,
        )
        await robust_backend.store_turn(turn)

        # Create a tool usage
        tool_usage = ToolUsage(
            id="test-tool",
            turn_id="test-turn",
            entity_id="TEST_AGENT",
            tool_name="test_tool",
            tool_args={},
            requires_approval=True,
            execution_status=ToolUsageStatus.PENDING,
            user_decision=None,
            user_feedback=None,
            decision_timestamp=None,
            execution_started_at=None,
            execution_completed_at=None,
            execution_result=None,
            execution_error=None,
            duration_ms=None,
            tokens_used=None,
            trace_id=None,
        )
        await robust_backend.store_tool_usage(tool_usage)

        # Concurrent update attempts
        async def update_tool_status(status: str) -> Any:
            """Try to update tool status."""
            return await robust_backend.update_tool_usage("test-tool", {"execution_status": status})

        # Multiple concurrent updates
        tasks = [
            update_tool_status("APPROVED"),
            update_tool_status("REJECTED"),
            update_tool_status("EXECUTING"),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All updates should succeed (last write wins)
        successful_updates = [r for r in results if isinstance(r, bool) and r]
        assert len(successful_updates) == 3

        # Verify final state is from one of the updates
        final_tool = await robust_backend.get_tool_usage("test-tool")
        assert final_tool is not None
        assert final_tool.execution_status in ["APPROVED", "REJECTED", "EXECUTING"]


class TestTransactionAtomicity:
    """Test transaction atomicity and rollback behavior."""

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_error(self, robust_backend: SQLiteBackend) -> None:
        """Test that failed transactions are rolled back completely."""
        agent_id = "ROLLBACK_TEST"

        # Custom function that simulates partial work then failure
        async def failing_transaction() -> None:
            assert robust_backend.async_session is not None
            async with robust_backend.async_session() as session:
                # First operation - should succeed
                turn1 = ConversationTurnModel(
                    id="turn-1",
                    agent_id=agent_id,
                    turn_number=1,
                    timestamp=datetime.utcnow(),
                    source_entity="USER",
                    target_entity=agent_id,
                    conversation_type="USER_AGENT",
                    user_query="First query",
                    agent_response="First response",
                )
                session.add(turn1)

                # Second operation - should succeed
                turn2 = ConversationTurnModel(
                    id="turn-2",
                    agent_id=agent_id,
                    turn_number=2,
                    timestamp=datetime.utcnow(),
                    source_entity="USER",
                    target_entity=agent_id,
                    conversation_type="USER_AGENT",
                    user_query="Second query",
                    agent_response="Second response",
                )
                session.add(turn2)

                # Force a constraint violation
                turn3 = ConversationTurnModel(
                    id="turn-3",
                    agent_id=agent_id,
                    turn_number=1,  # Duplicate turn number!
                    timestamp=datetime.utcnow(),
                    source_entity="USER",
                    target_entity=agent_id,
                    conversation_type="USER_AGENT",
                    user_query="Third query",
                    agent_response="Third response",
                )
                session.add(turn3)

                # This should fail
                await session.commit()

        # Execute and expect failure
        with pytest.raises(Exception):
            await failing_transaction()

        # Verify no turns were saved (rollback worked)
        turns = await robust_backend.get_turns_by_agent(agent_id)
        assert len(turns) == 0

    @pytest.mark.asyncio
    async def test_nested_transaction_behavior(self, robust_backend: SQLiteBackend) -> None:
        """Test behavior with nested operations."""
        # Create a turn with tool usage in a single transaction
        turn_id = "nested-test-turn"

        assert robust_backend.async_session is not None
        async with robust_backend.async_session() as session:
            # Add turn
            turn = ConversationTurnModel(
                id=turn_id,
                agent_id="NESTED_TEST",
                turn_number=1,
                timestamp=datetime.utcnow(),
                source_entity="USER",
                target_entity="NESTED_TEST",
                conversation_type="USER_AGENT",
                user_query="Test query",
                agent_response="Test response",
            )
            session.add(turn)

            # Add tool usage
            tool1 = ToolUsageModel(
                id="tool-1",
                turn_id=turn_id,
                entity_id="NESTED_TEST",
                tool_name="test_tool",
                tool_args={},
                execution_status="SUCCESS",
            )
            session.add(tool1)

            # Add another tool usage
            tool2 = ToolUsageModel(
                id="tool-2",
                turn_id=turn_id,
                entity_id="NESTED_TEST",
                tool_name="test_tool_2",
                tool_args={},
                execution_status="SUCCESS",
            )
            session.add(tool2)

            # Commit all at once
            await session.commit()

        # Verify all were saved
        turns = await robust_backend.get_turns_by_agent("NESTED_TEST")
        assert len(turns) == 1

        tools = await robust_backend.get_tool_usage_by_turn(turn_id)
        assert len(tools) == 2


class TestCrashRecovery:
    """Test database recovery after crashes."""

    @pytest.mark.asyncio
    async def test_database_consistency_after_interrupt(self, tmp_path: Path) -> None:
        """Test that database remains consistent after simulated crash."""
        db_path = tmp_path / "crash_test.db"

        # First backend - write some data
        db_manager1 = DatabaseManager(db_path)
        await db_manager1.initialize()
        backend1 = SQLiteBackend(db_manager1)
        await backend1.initialize()

        # Write 5 turns
        for i in range(5):
            turn = create_test_turn(
                id=f"crash-turn-{i}",
                agent_id="CRASH_TEST",
                turn_number=i + 1,
                timestamp=datetime.utcnow(),
                source_entity="USER",
                target_entity="CRASH_TEST",
                conversation_type="USER_AGENT",
                user_query=f"Query {i}",
                agent_response=f"Response {i}",
                status=TurnStatus.COMPLETED,
            )
            await backend1.store_turn(turn)

        # Simulate crash by not closing properly (no checkpoint)
        # Just dispose the engine without proper close
        if backend1.engine:
            await backend1.engine.dispose()

        # Open new backend and check consistency
        db_manager2 = DatabaseManager(db_path)
        await db_manager2.initialize()
        backend2 = SQLiteBackend(db_manager2)
        await backend2.initialize()

        # Should have exactly 5 turns (WAL mode should preserve them)
        turns = await backend2.get_turns_by_agent("CRASH_TEST")
        assert len(turns) == 5

        # All turns should be valid
        for i, turn in enumerate(sorted(turns, key=lambda t: t.turn_number)):
            assert turn.turn_number == i + 1
            assert turn.user_query == f"Query {i}"

        await backend2.close()
        await db_manager1.close()
        await db_manager2.close()

    @pytest.mark.asyncio
    async def test_wal_checkpoint_recovery(self, robust_backend: SQLiteBackend) -> None:
        """Test WAL checkpoint and recovery."""
        # Write some data
        for i in range(100):
            turn = create_test_turn(
                id=f"wal-turn-{i}",
                agent_id="WAL_TEST",
                turn_number=i + 1,
                timestamp=datetime.utcnow(),
                source_entity="USER",
                target_entity="WAL_TEST",
                conversation_type="USER_AGENT",
                user_query=f"Query {i}",
                agent_response=f"Response {i}",
                status=TurnStatus.COMPLETED,
            )
            await robust_backend.store_turn(turn)

        # Force WAL checkpoint
        assert robust_backend.engine is not None
        async with robust_backend.engine.begin() as conn:
            await conn.execute(text("PRAGMA wal_checkpoint(FULL)"))

        # Verify all data is persisted
        turns = await robust_backend.get_turns_by_agent("WAL_TEST")
        assert len(turns) == 100


class TestDataIntegrity:
    """Test data integrity constraints and validation."""

    @pytest.mark.asyncio
    async def test_foreign_key_enforcement(self, robust_backend: SQLiteBackend) -> None:
        """Test that foreign key constraints are enforced."""
        # Try to create tool usage with non-existent turn_id
        tool = ToolUsage(
            id="orphan-tool",
            turn_id="non-existent-turn",
            entity_id="TEST",
            tool_name="test_tool",
            tool_args={},
            requires_approval=False,
            execution_status=ToolUsageStatus.PENDING,
            user_decision=None,
            user_feedback=None,
            decision_timestamp=None,
            execution_started_at=None,
            execution_completed_at=None,
            execution_result=None,
            execution_error=None,
            duration_ms=None,
            tokens_used=None,
            trace_id=None,
        )

        # This should fail due to foreign key constraint
        with pytest.raises(Exception) as exc_info:
            await robust_backend.store_tool_usage(tool)

        # Verify it's a foreign key violation
        assert (
            "foreign key" in str(exc_info.value).lower()
            or "constraint" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_required_fields_validation(self, robust_backend: SQLiteBackend) -> None:
        """Test that required fields are enforced at database level."""
        # Try to store turn with missing required fields
        assert robust_backend.async_session is not None
        async with robust_backend.async_session() as session:
            # Missing agent_response (required field)
            invalid_turn = ConversationTurnModel(
                id="invalid-turn",
                agent_id="TEST",
                turn_number=1,
                timestamp=datetime.utcnow(),
                source_entity="USER",
                target_entity="TEST",
                conversation_type="USER_AGENT",
                user_query="Test query",
                # agent_response is missing!
            )
            session.add(invalid_turn)

            with pytest.raises(Exception):
                await session.commit()

    @pytest.mark.asyncio
    async def test_data_type_validation(self, robust_backend: SQLiteBackend) -> None:
        """Test that data types are validated."""
        # This test would need schema-level validation
        # SQLite is quite permissive with types, so we test the Pydantic layer

        # Try to create turn with invalid data types
        with pytest.raises(Exception):
            ConversationTurn(
                id="invalid-test",
                agent_id="TEST",
                turn_number="not_a_number",  # type: ignore[arg-type]  # Should be int
                timestamp="not_a_datetime",  # type: ignore[arg-type]  # Should be datetime
                source_entity="USER",
                target_entity="TEST",
                conversation_type="USER_AGENT",
                user_query="Test",
                agent_response="Test",
                status=TurnStatus.COMPLETED,
                task_id=None,
                llm_context=None,
                trace_id=None,
                total_duration_ms=None,
                llm_duration_ms=None,
                tools_duration_ms=None,
                error_details=None,
                compacted=False,
            )


class TestPerformanceUnderLoad:
    """Test performance and stability under heavy load."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_bulk_write_performance(self, robust_backend: SQLiteBackend) -> None:
        """Test bulk write operations."""
        num_turns = 1000
        batch_size = 100

        start_time = datetime.utcnow()

        for batch in range(0, num_turns, batch_size):
            tasks = []
            for i in range(batch, min(batch + batch_size, num_turns)):
                turn = create_test_turn(
                    id=f"bulk-turn-{i}",  # Add ID
                    agent_id="BULK_TEST",
                    turn_number=i + 1,
                    timestamp=datetime.utcnow(),
                    source_entity="USER",
                    target_entity="BULK_TEST",
                    conversation_type="USER_AGENT",
                    user_query=f"Bulk query {i}",
                    agent_response=f"Bulk response {i}",
                    status=TurnStatus.COMPLETED,
                )
                tasks.append(robust_backend.store_turn(turn))

            await asyncio.gather(*tasks)

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        # Verify all writes succeeded
        turns = await robust_backend.get_turns_by_agent("BULK_TEST")
        assert len(turns) == num_turns

        # Performance assertion (should complete in reasonable time)
        assert duration < 30  # 30 seconds for 1000 writes

        # Calculate writes per second
        writes_per_second = num_turns / duration
        print(f"Bulk write performance: {writes_per_second:.2f} writes/second")

    @pytest.mark.asyncio
    async def test_concurrent_read_write_performance(self, robust_backend: SQLiteBackend) -> None:
        """Test performance with mixed read/write workload."""
        agent_id = "MIXED_LOAD"
        num_operations = 100

        # First, seed with some data
        for i in range(50):
            turn = create_test_turn(
                id=f"seed-turn-{i}",  # Add ID
                agent_id=agent_id,
                turn_number=i + 1,
                timestamp=datetime.utcnow(),
                source_entity="USER",
                target_entity=agent_id,
                conversation_type="USER_AGENT",
                user_query=f"Seed query {i}",
                agent_response=f"Seed response {i}",
                status=TurnStatus.COMPLETED,
            )
            await robust_backend.store_turn(turn)

        # Mixed operations
        async def mixed_operation(op_id: int) -> None:
            if op_id % 3 == 0:
                # Write operation
                turn = create_test_turn(
                    id=f"mixed-turn-{op_id}",  # Add ID
                    agent_id=agent_id,
                    turn_number=50 + op_id + 1,  # Start from 51 to avoid conflict
                    timestamp=datetime.utcnow(),
                    source_entity="USER",
                    target_entity=agent_id,
                    conversation_type="USER_AGENT",
                    user_query=f"Mixed query {op_id}",
                    agent_response=f"Mixed response {op_id}",
                    status=TurnStatus.COMPLETED,
                )
                await robust_backend.store_turn(turn)
            else:
                # Read operation - get recent turns
                await robust_backend.get_turns_by_timerange(limit=10)

        # Execute mixed operations concurrently
        start_time = datetime.utcnow()
        tasks = [mixed_operation(i) for i in range(num_operations)]
        await asyncio.gather(*tasks)
        end_time = datetime.utcnow()

        duration = (end_time - start_time).total_seconds()
        ops_per_second = num_operations / duration
        print(f"Mixed workload performance: {ops_per_second:.2f} ops/second")


class TestSQLiteSpecificFeatures:
    """Test SQLite-specific robustness features."""

    @pytest.mark.asyncio
    async def test_pragma_settings(self, robust_backend: SQLiteBackend) -> None:
        """Verify SQLite pragma settings are correctly applied."""
        assert robust_backend.engine is not None
        async with robust_backend.engine.begin() as conn:
            # Check foreign keys are enabled
            result = await conn.execute(text("PRAGMA foreign_keys"))
            fk_enabled = result.scalar()
            assert fk_enabled == 1

            # Check journal mode
            result = await conn.execute(text("PRAGMA journal_mode"))
            journal_mode = result.scalar()
            assert journal_mode is not None
            assert journal_mode.upper() == "WAL"

            # Check synchronous mode
            result = await conn.execute(text("PRAGMA synchronous"))
            sync_mode = result.scalar()
            assert sync_mode in [1, "NORMAL"]  # 1 is NORMAL mode (as set in SQLiteBackend)

    @pytest.mark.asyncio
    async def test_busy_timeout_handling(self, robust_backend: SQLiteBackend) -> None:
        """Test busy timeout handling for concurrent access."""

        # Create a long-running transaction
        async def long_transaction() -> None:
            assert robust_backend.async_session is not None
            async with robust_backend.async_session() as session:
                async with session.begin():
                    # Add a turn
                    turn = ConversationTurnModel(
                        id="long-tx-turn",
                        agent_id="LONG_TX",
                        turn_number=1,
                        timestamp=datetime.utcnow(),
                        source_entity="USER",
                        target_entity="LONG_TX",
                        conversation_type="USER_AGENT",
                        user_query="Long transaction",
                        agent_response="Response",
                    )
                    session.add(turn)

                    # Hold the transaction open
                    await asyncio.sleep(2)

                    # Transaction commits automatically when exiting the context

        # Try concurrent access
        async def concurrent_access() -> None:
            # This should wait due to busy timeout instead of failing immediately
            await robust_backend.get_turns_by_timerange(limit=1)

        # Run both concurrently
        await asyncio.gather(long_transaction(), concurrent_access())

        # Both should succeed
        turns = await robust_backend.get_turns_by_agent("LONG_TX")
        assert len(turns) == 1


# Helper function for crash simulation tests
def _generate_random_string(length: int = 10) -> str:
    """Generate random string for test data."""
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))
