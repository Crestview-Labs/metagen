"""Pytest configuration and fixtures for metagen tests."""

import os
import tempfile
import uuid
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

import pytest
import pytest_asyncio
from dotenv import load_dotenv

from agents.memory.memory_manager import MemoryManager
from agents.memory.sqlite_backend import SQLiteBackend
from common.models import (
    CompactMemory,
    ConversationTurn,
    LongTermMemory,
    ToolUsage,
    ToolUsageStatus,
    TurnStatus,
)
from db.engine import DatabaseEngine

# Load environment variables from .env file
load_dotenv()


F = TypeVar("F", bound=Callable[..., Any])


@pytest.fixture
def session_id() -> str:
    """Generate a unique session ID for testing."""
    return f"test-session-{uuid.uuid4().hex[:8]}"


def with_openai_key(func: F) -> F:
    """Decorator to skip test if OpenAI API key is not available."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            pytest.skip("OpenAI API key not available")
        return func(*args, **kwargs)

    return wrapper  # type: ignore


def with_anthropic_key(func: F) -> F:
    """Decorator to skip test if Anthropic API key is not available."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip("Anthropic API key not available")
        return func(*args, **kwargs)

    return wrapper  # type: ignore


# Fixtures for API key validation
@pytest.fixture
def require_anthropic_key() -> None:
    """Fixture to skip test if Anthropic API key is not available."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("Anthropic API key not available")


@pytest.fixture
def require_openai_key() -> None:
    """Fixture to skip test if OpenAI API key is not available."""
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OpenAI API key not available")


@pytest.fixture
def require_gemini_key() -> None:
    """Fixture to skip test if Gemini API key is not available."""
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("Gemini API key not available")


@pytest.fixture
def require_all_llm_keys() -> None:
    """Fixture to skip test if any LLM API key is missing."""
    missing_keys = []
    if not os.getenv("ANTHROPIC_API_KEY"):
        missing_keys.append("ANTHROPIC_API_KEY")
    if not os.getenv("OPENAI_API_KEY"):
        missing_keys.append("OPENAI_API_KEY")
    if not os.getenv("GEMINI_API_KEY"):
        missing_keys.append("GEMINI_API_KEY")

    if missing_keys:
        pytest.skip(f"Missing API keys: {', '.join(missing_keys)}")


@pytest.fixture
def temp_db_path() -> Any:  # Generator type
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    yield db_path
    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest_asyncio.fixture
async def db_engine(temp_db_path: str) -> Any:  # Generator type
    """Create a DatabaseEngine instance for testing."""
    engine = DatabaseEngine(Path(temp_db_path))
    await engine.initialize()
    yield engine
    await engine.close()


@pytest_asyncio.fixture
async def storage_backend(db_engine: DatabaseEngine) -> Any:  # Generator type
    """Create a storage backend (SQLiteBackend) for low-level testing."""
    backend = SQLiteBackend(db_engine)
    await backend.initialize()
    yield backend
    await backend.close()


@pytest_asyncio.fixture
async def memory_manager(db_engine: DatabaseEngine) -> Any:  # Generator type
    """Create a MemoryManager instance for testing."""
    manager = MemoryManager(db_engine)
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
def sample_conversation_turn() -> ConversationTurn:
    """Create a sample conversation turn for testing."""
    return ConversationTurn(
        id="test-turn-1",
        agent_id="test-agent-1",
        turn_number=1,
        timestamp=datetime.utcnow(),
        source_entity="USER",
        target_entity="test-agent-1",
        conversation_type="USER_AGENT",
        user_query="What is the capital of France?",
        agent_response="The capital of France is Paris.",
        task_id=None,
        compacted=False,
        llm_context={"model": "test-model", "temperature": 0.7},
        tools_used=True,
        trace_id="trace-123",
        total_duration_ms=1500,
        llm_duration_ms=800,
        tools_duration_ms=200,
        user_metadata={"user_id": "test-user"},
        agent_metadata={"agent_version": "1.0"},
        status=TurnStatus.COMPLETED,
        error_details=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_compact_memory() -> CompactMemory:
    """Create a sample compact memory for testing."""
    return CompactMemory(
        id="compact-1",
        created_at=datetime.utcnow(),
        start_time=datetime.utcnow() - timedelta(hours=1),
        end_time=datetime.utcnow(),
        task_ids=["task-1", "task-2"],
        summary="Discussion about European capitals",
        key_points=["Paris is capital of France", "Berlin is capital of Germany"],
        entities={"countries": ["France", "Germany"], "cities": ["Paris", "Berlin"]},
        semantic_labels=["geography", "capitals", "europe"],
        turn_count=5,
        token_count=200,
        compressed_token_count=100,
        processed=False,
    )


@pytest.fixture
def sample_long_term_memory() -> LongTermMemory:
    """Create a sample long-term memory for testing."""
    return LongTermMemory(
        id="longterm-1",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        task_id="task-1",
        content=(
            "Knowledge about capital cities of European countries including "
            "France (Paris) and Germany (Berlin)."
        ),
    )


@pytest.fixture
def sample_preference() -> LongTermMemory:
    """Create a sample user preference for testing."""
    return LongTermMemory(
        id="preference-1",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        task_id=None,
        content="User prefers short, direct answers rather than verbose explanations.",
    )


@pytest.fixture
def multiple_turns() -> list[ConversationTurn]:
    """Create multiple conversation turns for testing."""
    base_time = datetime.utcnow()
    turns = []

    for i in range(5):
        turn = ConversationTurn(
            id=f"turn-{i}",
            agent_id="multi-agent",
            turn_number=i + 1,
            timestamp=base_time + timedelta(minutes=i),
            source_entity="USER",
            target_entity="multi-agent",
            conversation_type="USER_AGENT",
            user_query=f"Question {i}",
            agent_response=f"Answer {i}",
            task_id=None,
            llm_context={"model": "test-model"},
            tools_used=False,
            trace_id=f"trace-{i}",
            total_duration_ms=1000 + i * 100,
            llm_duration_ms=500 + i * 50,
            tools_duration_ms=100 + i * 10,
            user_metadata={},
            agent_metadata={},
            status=TurnStatus.COMPLETED,
            error_details=None,
            compacted=False,
            created_at=base_time + timedelta(minutes=i),
            updated_at=base_time + timedelta(minutes=i),
        )
        turns.append(turn)

    return turns


@pytest.fixture
def enhanced_conversation_turn() -> ConversationTurn:
    """Create a conversation turn with entity tracking fields."""
    return ConversationTurn(
        id="enhanced-turn-1",
        agent_id="METAGEN",
        turn_number=1,
        timestamp=datetime.utcnow(),
        source_entity="USER",
        target_entity="METAGEN",
        conversation_type="USER_AGENT",
        user_query="Search my emails for urgent messages",
        agent_response="I'll search your emails for urgent messages.",
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


@pytest.fixture
def agent_to_agent_turn() -> ConversationTurn:
    """Create an agent-to-agent conversation turn."""
    return ConversationTurn(
        id="agent-turn-1",
        agent_id="TASK_EXECUTION_123",
        turn_number=1,
        timestamp=datetime.utcnow(),
        source_entity="METAGEN",
        target_entity="TASK_EXECUTION_123",
        conversation_type="AGENT_AGENT",
        user_query="execute_task: Analyze sales data for Q4",
        agent_response="Starting sales data analysis for Q4...",
        task_id="task_123",
        status=TurnStatus.COMPLETED,
        llm_context=None,
        trace_id=None,
        total_duration_ms=None,
        llm_duration_ms=None,
        tools_duration_ms=None,
        error_details=None,
        compacted=False,
    )


@pytest.fixture
def sample_tool_usage() -> ToolUsage:
    """Create a sample tool usage record."""
    return ToolUsage(
        id="tool-usage-1",
        turn_id="test-turn-1",
        entity_id="METAGEN",
        tool_name="gmail_search",
        tool_args={"query": "from:boss urgent"},
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
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def approved_tool_usage() -> ToolUsage:
    """Create an approved tool usage record."""
    now = datetime.utcnow()
    return ToolUsage(
        id="tool-usage-approved",
        turn_id="test-turn-2",
        entity_id="METAGEN",
        tool_name="read_file",
        tool_args={"path": "/tmp/test.txt"},
        requires_approval=True,
        user_decision="APPROVED",
        user_feedback=None,
        decision_timestamp=now,
        execution_status=ToolUsageStatus.APPROVED,
        execution_started_at=None,
        execution_completed_at=None,
        execution_result=None,
        execution_error=None,
        duration_ms=None,
        tokens_used=None,
        trace_id=None,
        created_at=now - timedelta(minutes=5),
        updated_at=now,
    )


@pytest.fixture(autouse=True)
def reset_tool_registry() -> Any:  # Generator type
    """Reset the global tool registry before each test."""
    from tools.registry import get_tool_executor, get_tool_registry

    # Store original state
    executor = get_tool_executor()
    registry = get_tool_registry()
    original_tools = executor.core_tools.copy()
    original_servers = executor.mcp_servers.copy()
    original_disabled = registry.disabled_tools.copy()

    yield

    # Reset to original state
    executor.core_tools = original_tools
    executor.mcp_servers = original_servers
    registry.disabled_tools = original_disabled


@pytest.fixture
def executed_tool_usage() -> ToolUsage:
    """Create a successfully executed tool usage record."""
    now = datetime.utcnow()
    return ToolUsage(
        id="tool-usage-executed",
        turn_id="test-turn-3",
        entity_id="METAGEN",
        tool_name="get_current_time",
        tool_args={},
        requires_approval=False,
        user_decision=None,
        user_feedback=None,
        decision_timestamp=None,
        execution_started_at=now - timedelta(seconds=2),
        execution_completed_at=now,
        execution_status=ToolUsageStatus.SUCCESS,
        execution_result={"time": "2:30 PM PST"},
        execution_error=None,
        duration_ms=125.5,
        tokens_used=15,
        trace_id="test-trace-123",
        created_at=now - timedelta(minutes=1),
        updated_at=now,
    )
