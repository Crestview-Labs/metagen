"""Test MetaAgent core functionality."""

import logging
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from pydantic import BaseModel, Field

from agents.memory.memory_manager import MemoryManager
from agents.meta_agent import MetaAgent
from client.llm_client import LLMClient
from common.messages import (
    AgentMessage,
    ApprovalDecision,
    ApprovalRequestMessage,
    ApprovalResponseMessage,
    ErrorMessage,
    Message,
    ThinkingMessage,
    ToolCallMessage,
    ToolCallRequest,
    ToolResultMessage,
    ToolStartedMessage,
    UserMessage,
    create_user_message,
)
from tools.base import BaseCoreTool
from tools.registry import get_tool_executor

logger = logging.getLogger(__name__)


@pytest.mark.unit
@pytest.mark.asyncio
class TestMetaAgent:
    """Test MetaAgent functionality."""

    @pytest_asyncio.fixture
    async def test_db_engine(self, tmp_path: Path) -> AsyncIterator[Any]:
        """Create a test database engine."""
        from db.engine import DatabaseEngine

        db_path = tmp_path / "test_meta_agent.db"
        engine = DatabaseEngine(db_path)
        await engine.initialize()
        yield engine
        await engine.close()

    @pytest_asyncio.fixture
    async def memory_manager(self, test_db_engine: Any) -> AsyncIterator[MemoryManager]:
        """Create memory manager for testing."""
        manager = MemoryManager(test_db_engine)
        await manager.initialize()
        yield manager
        await manager.close()

    @pytest_asyncio.fixture
    async def mock_llm_client(self) -> AsyncMock:
        """Create mock LLM client."""
        from unittest.mock import Mock

        mock_client = AsyncMock(spec=LLMClient)
        # generate_stream_with_tools should return an async iterator directly, not a coroutine
        mock_client.generate_stream_with_tools = Mock()
        mock_client.generate_stream_with_tool_results = Mock()
        mock_client.initialize = AsyncMock()
        mock_client.close = AsyncMock()
        mock_client.last_llm_duration_ms = 100
        mock_client.last_tools_duration_ms = 50
        return mock_client

    @pytest_asyncio.fixture
    async def mock_search_tool(self) -> BaseCoreTool:
        """Create a mock search files tool."""

        class SearchInput(BaseModel):
            pattern: str = Field(description="File pattern to search")

        class SearchOutput(BaseModel):
            files_found: int
            message: str

        class MockSearchTool(BaseCoreTool):
            def __init__(self) -> None:
                super().__init__(
                    name="search_files",
                    description="Search for files by pattern",
                    input_schema=SearchInput,
                    output_schema=SearchOutput,
                )

            async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
                # Cast to correct type for internal use
                _ = SearchInput(**input_data.model_dump())  # Validate input
                return SearchOutput(files_found=5, message="Found 5 Python files")

        return MockSearchTool()

    @pytest_asyncio.fixture
    async def meta_agent(
        self, memory_manager: MemoryManager, mock_llm_client: AsyncMock
    ) -> AsyncIterator[MetaAgent]:
        """Create MetaAgent with mocked dependencies."""
        agent = MetaAgent(
            agent_id="test-meta-agent",
            memory_manager=memory_manager,
            available_tools=[],  # No tools for testing
            llm_config=None,  # Don't create client internally
        )
        # Set the mock client before initialization
        agent.llm_client = mock_llm_client
        await agent.initialize()
        yield agent

    @pytest_asyncio.fixture
    async def meta_agent_with_tools(
        self,
        memory_manager: MemoryManager,
        mock_llm_client: AsyncMock,
        mock_search_tool: BaseCoreTool,
    ) -> AsyncIterator[MetaAgent]:
        """Create MetaAgent with tools."""
        # Register the tool with executor so it can be found
        executor = get_tool_executor()
        executor.register_core_tool(mock_search_tool)

        agent = MetaAgent(
            agent_id="test-meta-agent",
            memory_manager=memory_manager,
            available_tools=[mock_search_tool.get_tool_schema()],
            llm_config=None,  # Don't create client internally
        )
        # Set the mock client before initialization
        agent.llm_client = mock_llm_client
        await agent.initialize()
        yield agent

    async def test_process_user_query_simple(
        self, meta_agent: MetaAgent, mock_llm_client: AsyncMock
    ) -> None:
        """Test processing a simple user query."""

        # Mock streaming response
        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
            yield AgentMessage(
                agent_id="METAGEN", session_id="test-session", content="The weather is sunny today!"
            )

        # Since generate_stream_with_tools is now a regular Mock,
        # we can set return_value to the async generator directly
        mock_llm_client.generate_stream_with_tools.return_value = mock_stream()

        # Process query using stream_chat
        chunks = []
        response_content = ""
        async for chunk in meta_agent.stream_chat(
            create_user_message("METAGEN", "test-session", "What's the weather like?")
        ):
            chunks.append(chunk)
            if isinstance(chunk, AgentMessage):
                response_content += chunk.content

        assert response_content == "The weather is sunny today!"
        assert mock_llm_client.generate_stream_with_tools.called

        # Check conversation was recorded
        recent = await meta_agent.memory_manager.get_recent_conversations(limit=1)
        assert len(recent) == 1
        assert recent[0].user_query == "What's the weather like?"
        assert recent[0].agent_response == "The weather is sunny today!"

    async def test_process_user_query_with_tools(
        self,
        meta_agent_with_tools: MetaAgent,
        mock_llm_client: AsyncMock,
        mock_search_tool: BaseCoreTool,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test processing a query that uses tools."""
        # Tool is already registered in meta_agent_with_tools fixture

        # Mock streaming response with tool usage
        # We need to make generate_stream_with_tools return different results on each call
        call_count = 0

        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call - request tool use
                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id="test-session",
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="call_1",
                            tool_name="search_files",
                            tool_args={"pattern": "*.py"},
                        )
                    ],
                )
            else:
                # Second call - respond with the tool results
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id="test-session",
                    content="I found 5 Python files in the current directory.",
                )

        def stream_factory(*args: Any, **kwargs: Any) -> Any:
            return mock_stream()

        mock_llm_client.generate_stream_with_tools.side_effect = stream_factory
        mock_llm_client.last_tools_duration_ms = 200

        # Process query using stream_chat
        chunks = []
        response_content = ""
        async for chunk in meta_agent_with_tools.stream_chat(
            create_user_message("METAGEN", "test-session", "Find all Python files")
        ):
            chunks.append(chunk)
            if isinstance(chunk, AgentMessage):
                response_content += chunk.content

        assert "found" in response_content.lower()
        assert "python" in response_content.lower()

        # Check conversation was recorded with tool usage
        recent = await meta_agent_with_tools.memory_manager.get_recent_conversations(limit=1)
        assert len(recent) == 1
        assert recent[0].tools_used is True
        # TODO: Add timing tracking in BaseAgent
        # assert recent[0].tools_duration_ms == 200

    async def test_build_context_with_memory(
        self, meta_agent: MetaAgent, memory_manager: MemoryManager
    ) -> None:
        """Test context building includes relevant memory."""
        # Add some historical conversations
        await memory_manager.record_conversation_turn(
            user_query="My favorite color is blue",
            agent_response="I'll remember that your favorite color is blue.",
            agent_id="test-meta-agent",
            session_id="test-session",
        )

        await memory_manager.record_conversation_turn(
            user_query="What's the capital of France?",
            agent_response="The capital of France is Paris.",
            agent_id="test-meta-agent",
            session_id="test-session",
        )

        # Build context for related query
        messages = await meta_agent.build_context("What's my favorite color?")

        # Should have some conversation history
        assert len(messages) >= 2  # At least one user-agent exchange

        # Check message types
        user_messages = [m for m in messages if isinstance(m, UserMessage)]
        agent_messages = [m for m in messages if isinstance(m, AgentMessage)]

        assert len(user_messages) >= 1
        assert len(agent_messages) >= 1

        # Check if the relevant conversation about favorite color is included in context
        context_str = " ".join(m.content for m in messages if hasattr(m, "content"))
        assert "blue" in context_str or "color" in context_str

    async def test_error_handling(self, meta_agent: MetaAgent, mock_llm_client: AsyncMock) -> None:
        """Test error handling in query processing."""
        # Mock LLM to raise an error
        mock_llm_client.generate_stream_with_tools.side_effect = Exception("API Error")

        # Should yield an ErrorMessage instead of raising
        messages = []
        async for chunk in meta_agent.stream_chat(
            create_user_message("METAGEN", "test-session", "Test query")
        ):
            messages.append(chunk)

        # Should have received an ErrorMessage
        from common.messages import ErrorMessage

        error_messages = [m for m in messages if isinstance(m, ErrorMessage)]
        assert len(error_messages) >= 1
        assert "API Error" in error_messages[0].error

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

        # Mock streaming response
        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
            yield ToolCallMessage(
                agent_id="METAGEN",
                session_id="test-session",
                tool_calls=[ToolCallRequest(tool_id="call_1", tool_name="test_tool", tool_args={})],
            )
            # Note: LLM doesn't yield ToolResultMessage - that comes from agent executing tools
            yield AgentMessage(
                agent_id="METAGEN", session_id="test-session", content="Hello world!"
            )

        mock_llm_client.generate_stream_with_tools.return_value = mock_stream()

        # Process with streaming
        events = []
        response_content = ""
        async for event in meta_agent.stream_chat(
            create_user_message("METAGEN", "test-session", "Hi there")
        ):
            events.append(event)
            if isinstance(event, AgentMessage):
                response_content += event.content

        # Should have received multiple events including thinking, tool_call, and response
        # Note: We don't see ToolResultMessage because the agent doesn't have a "test_tool"
        # registered, so it can't execute it. The mock only yields what the LLM returns.
        assert len(events) >= 3

        # Check event types
        assert any(isinstance(e, ThinkingMessage) for e in events)
        assert any(isinstance(e, ToolCallMessage) for e in events)
        assert any(isinstance(e, AgentMessage) for e in events)

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
                user_query=f"Question {i}",
                agent_response=f"Answer {i}",
                agent_id="test-meta-agent",
                session_id="test-session",
            )

        # Build context - should limit history
        messages = await meta_agent.build_context("New question")

        # Should not include all 20 historical conversations
        # Should have limited history
        assert len(messages) >= 2  # At least some history
        assert len(messages) < 25  # Reasonable limit

        # All messages should be UserMessage or AgentMessage
        for msg in messages:
            assert isinstance(msg, (UserMessage, AgentMessage))

        # Context should not explode with all historical messages
        # (the actual user message "New question" is added by stream_chat, not build_context)

    async def test_task_detection(self, meta_agent: MetaAgent, mock_llm_client: AsyncMock) -> None:
        """Test that complex queries are recognized as potential tasks."""

        # Mock streaming response suggesting task creation
        async def mock_stream(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
            yield AgentMessage(
                agent_id="METAGEN",
                session_id="test-session",
                content="This seems like a complex workflow. "
                "Would you like me to create a task for this?",
            )

        mock_llm_client.generate_stream_with_tools.return_value = mock_stream()

        # Process query using stream_chat
        chunks = []
        response_content = ""
        async for chunk in meta_agent.stream_chat(
            create_user_message(
                "METAGEN",
                "test-session",
                "I need to analyze all customer feedback from last month, "
                "categorize issues, and create a report",
            )
        ):
            chunks.append(chunk)
            if isinstance(chunk, AgentMessage):
                response_content += chunk.content

        assert "task" in response_content.lower() or "workflow" in response_content.lower()


@pytest.mark.integration
@pytest.mark.llm
@pytest.mark.asyncio
class TestMetaAgentIntegration:
    """Integration tests for MetaAgent with real LLMs."""

    @pytest_asyncio.fixture
    async def test_db_engine(self, tmp_path: Path) -> AsyncIterator[Any]:
        """Create a test database manager."""
        from db.engine import DatabaseEngine

        db_path = tmp_path / "test_meta_agent_integration.db"
        engine = DatabaseEngine(db_path)
        await engine.initialize()
        yield engine
        await engine.close()

    @pytest_asyncio.fixture
    async def memory_manager(self, test_db_engine: Any) -> AsyncIterator[MemoryManager]:
        """Create memory manager for testing."""
        manager = MemoryManager(test_db_engine)
        await manager.initialize()
        yield manager
        await manager.close()

    @pytest_asyncio.fixture
    async def meta_agent(self, memory_manager: MemoryManager) -> AsyncIterator[MetaAgent]:
        """Create MetaAgent with real LLM for integration testing."""
        import os

        from client.models import ModelID

        agent = MetaAgent(
            agent_id="test-meta-agent-integration",
            memory_manager=memory_manager,
            llm_config={
                "llm": ModelID.CLAUDE_SONNET_4,
                "api_key": os.getenv("ANTHROPIC_API_KEY"),
                "max_iterations": 10,
                "max_tools_per_turn": 50,
            },
            available_tools=[],  # No tools for basic tests
        )

        await agent.initialize()
        yield agent

    async def test_simple_conversation(self, meta_agent: MetaAgent) -> None:
        """Test simple conversation with real LLM."""
        response = ""
        chunks_received = 0

        async for chunk in meta_agent.stream_chat(
            create_user_message(
                "METAGEN", "test-session", "Hello! Can you tell me a very short joke?"
            )
        ):
            chunks_received += 1
            if isinstance(chunk, AgentMessage):
                response = chunk.content

        # Should receive multiple chunks
        assert chunks_received >= 3  # thinking, llm_call, response
        # Should get a response
        assert len(response) > 0
        # Response should be reasonable length for a joke
        assert len(response) < 500

    async def test_context_memory(self, meta_agent: MetaAgent) -> None:
        """Test that agent remembers context across messages."""
        # First message
        response1 = ""
        async for chunk in meta_agent.stream_chat(
            create_user_message(
                "METAGEN", "test-session", "My name is TestUser and my favorite color is purple."
            )
        ):
            if isinstance(chunk, AgentMessage):
                response1 = chunk.content

        assert len(response1) > 0
        logger.debug(f"First response: {response1}")

        # Check what's in memory
        recent = await meta_agent.memory_manager.get_recent_conversations(limit=10)
        logger.debug(f"Conversations in memory: {len(recent)}")
        for conv in recent:
            logger.debug(
                f"  - Query: {conv.user_query[:50]}... Response: {conv.agent_response[:50]}..."
            )

        # Check what context will be built for second message
        context_messages = await meta_agent.build_context("What's my name and favorite color?")
        logger.debug(f"\nContext for second message ({len(context_messages)} messages):")
        for i, msg in enumerate(context_messages):
            msg_type = type(msg).__name__
            content_preview = (
                msg.content[:60] + "..."
                if hasattr(msg, "content") and len(msg.content) > 60
                else getattr(msg, "content", "No content")
            )
            logger.debug(f"  [{i}] {msg_type}: {content_preview}")

        # Second message - should remember the name and color
        response2 = ""
        async for chunk in meta_agent.stream_chat(
            create_user_message("METAGEN", "test-session", "What's my name and favorite color?")
        ):
            if isinstance(chunk, AgentMessage):
                response2 = chunk.content

        logger.debug(f"\nSecond response: {response2}")

        # Should remember both pieces of information
        assert "TestUser" in response2 or "test user" in response2.lower()
        assert "purple" in response2.lower()

    async def test_multiple_turns(self, meta_agent: MetaAgent) -> None:
        """Test multiple conversation turns."""
        turns = [
            "Let's play a word association game. I'll say a word, "
            "you respond with a related word. Ready?",
            "Ocean",
            "Mountain",
            "What was the first word I said in our game?",
        ]

        responses = []
        for i, turn in enumerate(turns):
            logger.debug(f"\n=== Turn {i + 1}: {turn}")
            response = ""
            async for chunk in meta_agent.stream_chat(
                create_user_message("METAGEN", "test-session", turn)
            ):
                if isinstance(chunk, AgentMessage):
                    response = chunk.content
            responses.append(response)
            logger.debug(f"Response: {response}")

            # Check conversation history
            recent = await meta_agent.memory_manager.get_recent_conversations(limit=10)
            logger.debug(f"Total conversations in memory: {len(recent)}")

        # All turns should have responses
        assert all(len(r) > 0 for r in responses)
        # Last response should reference "ocean"
        logger.debug(f"\nLast response: {responses[-1]}")
        assert "ocean" in responses[-1].lower()

    async def test_error_recovery(self, meta_agent: MetaAgent) -> None:
        """Test that agent handles edge cases gracefully."""
        # Very long input
        long_input = "Please summarize this: " + "test " * 1000

        response = ""
        error_occurred = False

        async for chunk in meta_agent.stream_chat(
            create_user_message("METAGEN", "test-session", long_input)
        ):
            if isinstance(chunk, ErrorMessage):
                error_occurred = True
            elif isinstance(chunk, AgentMessage):
                response = chunk.content

        # Should either handle it or error gracefully
        assert len(response) > 0 or error_occurred


@pytest.mark.integration
@pytest.mark.llm
@pytest.mark.asyncio
class TestMetaAgentWithToolsIntegration:
    """Integration tests for MetaAgent with tools and real LLMs."""

    @pytest_asyncio.fixture
    async def test_db_engine(self, tmp_path: Path) -> AsyncIterator[Any]:
        """Create a test database manager."""
        from db.engine import DatabaseEngine

        db_path = tmp_path / "test_meta_agent_tools_integration.db"
        engine = DatabaseEngine(db_path)
        await engine.initialize()
        yield engine
        await engine.close()

    @pytest_asyncio.fixture
    async def memory_manager(self, test_db_engine: Any) -> AsyncIterator[MemoryManager]:
        """Create memory manager for testing."""
        manager = MemoryManager(test_db_engine)
        await manager.initialize()
        yield manager
        await manager.close()

    @pytest_asyncio.fixture
    async def meta_agent_with_tools(
        self, memory_manager: MemoryManager
    ) -> AsyncIterator[MetaAgent]:
        """Create MetaAgent with tools for integration testing."""
        import os

        from client.models import ModelID
        from tests.agents.test_agent_tool_selection import CalculatorTool, WeatherTool
        from tools.registry import get_tool_executor

        # Create tool instances
        calculator_tool = CalculatorTool()
        weather_tool = WeatherTool()

        # Register test tools with executor
        executor = get_tool_executor()
        executor.register_core_tool(calculator_tool)
        executor.register_core_tool(weather_tool)

        # Pass tool schemas to agent (not the tool instances)
        available_tools = [calculator_tool.get_tool_schema(), weather_tool.get_tool_schema()]

        agent = MetaAgent(
            agent_id="test-meta-agent-tools-integration",
            memory_manager=memory_manager,
            llm_config={
                "llm": ModelID.CLAUDE_SONNET_4,
                "api_key": os.getenv("ANTHROPIC_API_KEY"),
                "max_iterations": 10,
                "max_tools_per_turn": 50,
            },
            available_tools=available_tools,
        )

        await agent.initialize()
        yield agent

    async def test_tool_usage_calculation(self, meta_agent_with_tools: MetaAgent) -> None:
        """Test that agent correctly uses calculator tool."""
        response = ""
        tool_calls = []

        async for chunk in meta_agent_with_tools.stream_chat(
            create_user_message("METAGEN", "test-session", "What is 42 times 37?")
        ):
            if isinstance(chunk, ToolStartedMessage):
                tool_calls.append(chunk.tool_name)
            elif isinstance(chunk, AgentMessage):
                response = chunk.content

        # Should use calculator
        assert "calculator" in tool_calls
        # Should have the correct answer (may be formatted with comma)
        assert "1554" in response or "1,554" in response  # 42 * 37 = 1554

    async def test_tool_chain(self, meta_agent_with_tools: MetaAgent) -> None:
        """Test using multiple tools in sequence."""
        response = ""
        tool_calls = []

        async for chunk in meta_agent_with_tools.stream_chat(
            create_user_message(
                "METAGEN",
                "test-session",
                "What's the weather in Paris? Also calculate 15% tip on $85.",
            )
        ):
            if isinstance(chunk, ToolStartedMessage):
                tool_calls.append(chunk.tool_name)
            elif isinstance(chunk, AgentMessage):
                response = chunk.content

        # Should use both tools
        assert "get_weather" in tool_calls
        assert "calculator" in tool_calls
        # Should mention Paris weather (mocked as sunny, 72°F)
        assert "paris" in response.lower()
        assert "72" in response or "sunny" in response.lower()
        # Should calculate tip correctly (15% of 85 = 12.75)
        assert "12.75" in response

    async def test_tool_error_handling(self, meta_agent_with_tools: MetaAgent) -> None:
        """Test that agent handles tool errors gracefully."""
        response = ""
        tool_calls = []

        async for chunk in meta_agent_with_tools.stream_chat(
            create_user_message(
                "METAGEN", "test-session", "Calculate the result of dividing by zero: 10/0"
            )
        ):
            if isinstance(chunk, ToolStartedMessage):
                tool_calls.append(chunk.tool_name)
            elif isinstance(chunk, AgentMessage):
                response = chunk.content

        # Should attempt to use calculator
        assert "calculator" in tool_calls
        # Should handle the error gracefully
        assert (
            "error" in response.lower()
            or "cannot" in response.lower()
            or "undefined" in response.lower()
        )

    async def test_no_tool_needed(self, meta_agent_with_tools: MetaAgent) -> None:
        """Test that agent doesn't use tools when not needed."""
        response = ""
        tool_calls = []

        async for chunk in meta_agent_with_tools.stream_chat(
            create_user_message(
                "METAGEN", "test-session", "What is the capital of France? No calculations needed."
            )
        ):
            if isinstance(chunk, ToolStartedMessage):
                tool_calls.append(chunk.tool_name)
            elif isinstance(chunk, AgentMessage):
                response = chunk.content

        # Should not use any tools
        assert len(tool_calls) == 0
        # Should know the answer
        assert "paris" in response.lower()

    async def test_parallel_tool_calls(self, meta_agent_with_tools: MetaAgent) -> None:
        """Test that agent can execute multiple tools in parallel."""
        response = ""
        tool_calls = []
        tool_results = []

        async for chunk in meta_agent_with_tools.stream_chat(
            create_user_message(
                "METAGEN",
                "test-session",
                "Please do all of these at once: "
                "1) Calculate 25 * 4, "
                "2) Calculate 100 / 5, "
                "3) Calculate 15 + 85, "
                "4) Get weather for London",
            )
        ):
            if isinstance(chunk, ToolStartedMessage):
                tool_calls.append(chunk.tool_name)
            elif isinstance(chunk, ToolResultMessage):
                tool_results.append(chunk)
            elif isinstance(chunk, AgentMessage):
                response = chunk.content

        # Should use calculator multiple times and weather once
        calculator_calls = [t for t in tool_calls if t == "calculator"]
        assert len(calculator_calls) >= 3  # At least 3 calculations
        assert "get_weather" in tool_calls

        # TODO: Once we have OpenTelemetry metrics, we can verify:
        # - max_concurrent_tools metric shows tools were executed in parallel
        # - tool_execution_duration shows overlapping execution times
        # For now, we just verify all tools were called and got results

        # Should have results from all tools
        assert len(tool_results) >= 4  # 3 calculator + 1 weather

        # Should have all answers in the response
        assert "100" in response  # 25 * 4
        assert "20" in response  # 100 / 5
        assert "100" in response  # 15 + 85 (same as first)
        assert "london" in response.lower()


@pytest.mark.integration
@pytest.mark.llm
@pytest.mark.asyncio
class TestMetaAgentToolApproval:
    """Integration tests for tool approval flows."""

    @pytest_asyncio.fixture
    async def test_db_engine(self, tmp_path: Path) -> AsyncIterator[Any]:
        """Create a test database manager."""
        from db.engine import DatabaseEngine

        db_path = tmp_path / "test_meta_agent_approval.db"
        engine = DatabaseEngine(db_path)
        await engine.initialize()
        yield engine
        await engine.close()

    @pytest_asyncio.fixture
    async def memory_manager(self, test_db_engine: Any) -> AsyncIterator[MemoryManager]:
        """Create memory manager for testing."""
        manager = MemoryManager(test_db_engine)
        await manager.initialize()
        yield manager
        await manager.close()

    @pytest_asyncio.fixture
    async def meta_agent_with_approval(
        self, memory_manager: MemoryManager
    ) -> AsyncIterator[MetaAgent]:
        """Create MetaAgent with tool approval enabled."""
        import asyncio
        import os

        from client.models import ModelID
        from tests.agents.test_agent_tool_selection import CalculatorTool, SearchTool, WeatherTool
        from tools.registry import get_tool_executor

        # Create tool instances
        calculator_tool = CalculatorTool()
        weather_tool = WeatherTool()
        search_tool = SearchTool()

        # Register test tools with executor
        executor = get_tool_executor()
        executor.register_core_tool(calculator_tool)
        executor.register_core_tool(weather_tool)
        executor.register_core_tool(search_tool)

        # Pass tool schemas to agent (not the tool instances)
        available_tools = [
            calculator_tool.get_tool_schema(),
            weather_tool.get_tool_schema(),
            search_tool.get_tool_schema(),
        ]

        agent = MetaAgent(
            agent_id="test-meta-agent-approval",
            memory_manager=memory_manager,
            llm_config={
                "llm": ModelID.CLAUDE_SONNET_4,
                "api_key": os.getenv("ANTHROPIC_API_KEY"),
                "max_iterations": 10,
                "max_tools_per_turn": 50,
            },
            available_tools=available_tools,
        )

        await agent.initialize()

        # Configure tool approval (using message channel for approvals)
        approval_queue: asyncio.Queue[Message] = asyncio.Queue()
        agent.configure_tool_approval(
            require_approval=True,
            auto_approve_tools=["calculator"],  # Calculator is auto-approved
            approval_queue=approval_queue,
        )

        yield agent

    async def test_mixed_approval_parallel_tools(self, meta_agent_with_approval: MetaAgent) -> None:
        """Test parallel tool execution with mixed approval requirements."""
        import asyncio

        response = ""
        tool_calls = []
        approval_requests: list[ApprovalRequestMessage] = []

        # Task to handle approvals
        async def approve_tools() -> None:
            """Simulate user approving tools after a short delay."""
            await asyncio.sleep(0.5)  # Simulate user thinking

            # Wait for approval requests to come in
            while len(approval_requests) < 2:  # We expect 2 tools needing approval
                await asyncio.sleep(0.1)

            # Put approval responses on the agent's queue
            for approval_req in approval_requests:
                tool_id = approval_req.tool_id
                tool_name = approval_req.tool_name

                # Approve weather, reject search
                if tool_name == "get_weather":
                    approval = ApprovalResponseMessage(
                        agent_id="test-meta-agent-approval",
                        session_id="test-session",
                        tool_id=tool_id,
                        decision=ApprovalDecision.APPROVED,
                        feedback="Approved for testing",
                    )
                else:  # web_search
                    approval = ApprovalResponseMessage(
                        agent_id="test-meta-agent-approval",
                        session_id="test-session",
                        tool_id=tool_id,
                        decision=ApprovalDecision.REJECTED,
                        feedback="Search not needed for this test",
                    )

                # Create approval message and send it through the message channel
                approval_message = approval
                # Process the approval by calling stream_chat with the approval message
                async for _ in meta_agent_with_approval.stream_chat(approval_message):
                    pass  # Just consume the events

        # Start approval task
        approval_task = asyncio.create_task(approve_tools())

        try:
            # Create the user message
            user_message = create_user_message(
                "METAGEN",
                "test-session",
                "Please do these tasks: "
                "1) Calculate 50 * 2 (should be auto-approved), "
                "2) Get weather for Tokyo (needs approval), "
                "3) Search web for 'quantum computing' (needs approval)",
            )
            async for chunk in meta_agent_with_approval.stream_chat(user_message):
                # Debug: log message types
                if isinstance(chunk, AgentMessage):
                    logger.debug(f"DEBUG: Got AgentMessage: {chunk.content[:50]}...")
                    response = chunk.content
                elif isinstance(chunk, ToolStartedMessage):
                    logger.debug(f"DEBUG: Got ToolStartedMessage for tool: {chunk.tool_name}")
                    tool_calls.append(chunk.tool_name)
                elif isinstance(chunk, ApprovalRequestMessage):
                    logger.debug(f"DEBUG: Got ApprovalRequestMessage for tool: {chunk.tool_name}")
                    approval_requests.append(chunk)
                else:
                    logger.debug(f"DEBUG: Got {type(chunk).__name__}")

            # Wait for approval task to complete
            await approval_task

        except Exception:
            approval_task.cancel()
            raise

        # Should have called calculator (auto-approved)
        assert "calculator" in tool_calls
        # Should have requested approval for weather and search
        assert len(approval_requests) >= 2

        # Response should include:
        # - Calculator result (100)
        assert "100" in response
        # - Weather result (approved)
        assert "tokyo" in response.lower()
        # - Search should be mentioned as rejected or not included
        # (The response might explain that search was not performed)
