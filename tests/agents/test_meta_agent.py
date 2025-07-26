"""Test MetaAgent core functionality."""

from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from agents.meta_agent import MetaAgent
from client.agentic_client import AgenticClient
from client.base_client import Role, StreamEvent, StreamEventType
from memory.storage.manager import MemoryManager
from memory.storage.sqlite_backend import SQLiteBackend


@pytest.mark.unit
@pytest.mark.asyncio
class TestMetaAgent:
    """Test MetaAgent functionality."""

    @pytest_asyncio.fixture
    async def test_db_manager(self, tmp_path: Path) -> AsyncIterator[Any]:
        """Create a test database manager."""
        from db.manager import DatabaseManager

        db_path = tmp_path / "test_meta_agent.db"
        manager = DatabaseManager(db_path)
        await manager.initialize()
        yield manager
        await manager.close()

    @pytest_asyncio.fixture
    async def memory_manager(self, test_db_manager: Any) -> AsyncIterator[MemoryManager]:
        """Create memory manager for testing."""
        backend = SQLiteBackend(test_db_manager)
        manager = MemoryManager(backend)
        await manager.initialize()
        yield manager
        await manager.close()

    @pytest_asyncio.fixture
    async def mock_llm_client(self) -> AsyncMock:
        """Create mock LLM client."""
        mock_client = AsyncMock(spec=AgenticClient)
        mock_client.generate = AsyncMock()
        mock_client.initialize = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.last_llm_duration_ms = 100
        mock_client.last_tools_duration_ms = 50
        return mock_client

    @pytest_asyncio.fixture
    async def meta_agent(
        self, memory_manager: MemoryManager, mock_llm_client: AsyncMock
    ) -> AsyncIterator[MetaAgent]:
        """Create MetaAgent with mocked dependencies."""
        agent = MetaAgent(
            agent_id="test-meta-agent",
            agentic_client=mock_llm_client,
            memory_manager=memory_manager,
        )
        yield agent

    async def test_process_user_query_simple(
        self, meta_agent: MetaAgent, mock_llm_client: AsyncMock
    ) -> None:
        """Test processing a simple user query."""

        # Mock streaming response
        async def mock_stream() -> AsyncIterator[StreamEvent]:
            yield StreamEvent(type=StreamEventType.CONTENT, content="The weather is sunny today!")

        mock_llm_client.generate.return_value = mock_stream()

        # Process query using stream_chat
        chunks = []
        response_content = ""
        async for chunk in meta_agent.stream_chat("What's the weather like?"):
            chunks.append(chunk)
            if chunk.get("stage") == "response":
                response_content = chunk.get("content", "")

        assert response_content == "The weather is sunny today!"
        assert mock_llm_client.generate.called

        # Check conversation was recorded
        recent = await meta_agent.memory_manager.get_recent_conversations(limit=1)
        assert len(recent) == 1
        assert recent[0].user_query == "What's the weather like?"
        assert recent[0].agent_response == "The weather is sunny today!"

    async def test_process_user_query_with_tools(
        self, meta_agent: MetaAgent, mock_llm_client: AsyncMock
    ) -> None:
        """Test processing a query that uses tools."""

        # Mock streaming response with tool usage
        async def mock_stream() -> AsyncIterator[StreamEvent]:
            yield StreamEvent.tool_call(tool_name="search_files", tool_args={"pattern": "*.py"})
            yield StreamEvent.tool_result(
                tool_name="search_files",
                success=True,
                result="Found 5 Python files",
                duration_ms=200,
            )
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                content="I found 5 Python files in the current directory.",
            )

        mock_llm_client.generate.return_value = mock_stream()
        mock_llm_client.last_tools_duration_ms = 200

        # Process query using stream_chat
        chunks = []
        response_content = ""
        async for chunk in meta_agent.stream_chat("Find all Python files"):
            chunks.append(chunk)
            if chunk.get("stage") == "response":
                response_content = chunk.get("content", "")

        assert "found" in response_content.lower()
        assert "python" in response_content.lower()

        # Check conversation was recorded with tool usage
        recent = await meta_agent.memory_manager.get_recent_conversations(limit=1)
        assert len(recent) == 1
        assert recent[0].tools_used is True
        assert recent[0].tools_duration_ms == 200

    async def test_build_context_with_memory(
        self, meta_agent: MetaAgent, memory_manager: MemoryManager
    ) -> None:
        """Test context building includes relevant memory."""
        # Add some historical conversations
        await memory_manager.record_conversation_turn(
            user_query="My favorite color is blue",
            agent_response="I'll remember that your favorite color is blue.",
            agent_id="test-meta-agent",
        )

        await memory_manager.record_conversation_turn(
            user_query="What's the capital of France?",
            agent_response="The capital of France is Paris.",
            agent_id="test-meta-agent",
        )

        # Build context for related query
        messages = await meta_agent.build_context("What's my favorite color?")

        # Should have system message and possibly some history
        assert len(messages) >= 1
        assert messages[0]["role"] == Role.SYSTEM.value

        # System message should mention available tools
        assert "tools" in messages[0]["content"].lower()

        # Check if the relevant conversation about favorite color is included in context
        context_str = str(messages)
        assert "blue" in context_str or "color" in context_str

    async def test_error_handling(self, meta_agent: MetaAgent, mock_llm_client: AsyncMock) -> None:
        """Test error handling in query processing."""
        # Mock LLM to raise an error
        mock_llm_client.generate.side_effect = Exception("API Error")

        # Should handle error gracefully by yielding error event
        chunks = []
        error_event_found = False
        async for chunk in meta_agent.stream_chat("Test query"):
            chunks.append(chunk)
            if chunk.get("stage") == "error":
                error_event_found = True
                assert "API Error" in chunk.get("content", "")
                assert chunk.get("metadata", {}).get("error") == "API Error"

        assert error_event_found, "Expected an error event to be yielded"

        # Error should be recorded in conversation
        recent = await meta_agent.memory_manager.get_recent_conversations(limit=1)
        assert len(recent) == 1
        assert recent[0].status == "error"  # status is already a string due to use_enum_values
        assert recent[0].error_details is not None
        assert recent[0].user_query == "Test query"

    async def test_streaming_response(
        self, meta_agent: MetaAgent, mock_llm_client: AsyncMock
    ) -> None:
        """Test streaming response handling."""

        # Mock streaming response - only the last content event is kept
        async def mock_stream() -> AsyncIterator[StreamEvent]:
            yield StreamEvent.tool_call("test_tool", {})
            yield StreamEvent.tool_result("test_tool", success=True, result="Tool executed")
            yield StreamEvent(type=StreamEventType.CONTENT, content="Hello world!")

        mock_llm_client.generate.return_value = mock_stream()

        # Process with streaming
        events = []
        response_content = ""
        async for event in meta_agent.stream_chat("Hi there"):
            events.append(event)
            if event.get("stage") == "response":
                response_content = event.get("content", "")

        # Should have received multiple events including thinking, llm_call, tool_call, response
        assert len(events) >= 4
        # Should have tool events
        tool_events = [e for e in events if e.get("stage") in ["tool_call", "tool_result"]]
        assert len(tool_events) >= 1

        # Response content should be the final content
        assert response_content == "Hello world!"

        # Should record conversation
        recent = await meta_agent.memory_manager.get_recent_conversations(limit=1)
        assert len(recent) == 1
        assert recent[0].agent_response == "Hello world!"

    async def test_context_size_limit(
        self, meta_agent: MetaAgent, memory_manager: MemoryManager
    ) -> None:
        """Test that context building respects size limits."""
        # Add many conversations
        for i in range(20):
            await memory_manager.record_conversation_turn(
                user_query=f"Question {i}", agent_response=f"Answer {i}", agent_id="test-meta-agent"
            )

        # Build context - should limit history
        messages = await meta_agent.build_context("New question")

        # Should not include all 20 historical conversations
        # At minimum should have system message
        assert len(messages) >= 1
        assert len(messages) < 25  # Reasonable limit
        assert messages[0]["role"] == Role.SYSTEM.value

        # Context should not explode with all historical messages
        # (the actual user message "New question" is added by stream_chat, not build_context)

    async def test_task_detection(self, meta_agent: MetaAgent, mock_llm_client: AsyncMock) -> None:
        """Test that complex queries are recognized as potential tasks."""

        # Mock streaming response suggesting task creation
        async def mock_stream() -> AsyncIterator[StreamEvent]:
            yield StreamEvent(
                type=StreamEventType.CONTENT,
                content="This seems like a complex workflow. "
                "Would you like me to create a task for this?",
            )

        mock_llm_client.generate.return_value = mock_stream()

        # Process query using stream_chat
        chunks = []
        response_content = ""
        async for chunk in meta_agent.stream_chat(
            "I need to analyze all customer feedback from last month, "
            "categorize issues, and create a report"
        ):
            chunks.append(chunk)
            if chunk.get("stage") == "response":
                response_content = chunk.get("content", "")

        assert "task" in response_content.lower() or "workflow" in response_content.lower()
