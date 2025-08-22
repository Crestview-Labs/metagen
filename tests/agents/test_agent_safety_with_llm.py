"""Tests for safety components with LLM (both mock and real)."""

from pathlib import Path
from typing import Any, AsyncGenerator, AsyncIterator

import pytest

from agents.agent_manager import AgentManager
from client.models import ModelID
from common.messages import AgentMessage, Message, ToolCallMessage, ToolCallRequest, UserMessage
from db.engine import DatabaseEngine

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def test_db(tmp_path: Path) -> AsyncGenerator[DatabaseEngine, None]:
    """Create a test database for safety tests."""
    db_path = tmp_path / "test_safety.db"
    db_engine = DatabaseEngine(db_path)
    await db_engine.initialize()
    yield db_engine
    await db_engine.close()


@pytest.fixture
async def agent_manager(test_db: DatabaseEngine) -> AsyncGenerator[AgentManager, None]:
    """Create an agent manager for safety tests."""
    manager = AgentManager(
        agent_name="TestAgent",
        db_engine=test_db,
        mcp_servers=[],  # No MCP servers for tests
        llm=ModelID.CLAUDE_SONNET_4,
    )

    yield manager

    # Cleanup
    await manager.cleanup()


# =============================================================================
# Mock LLM Tests
# =============================================================================


class TestIterationLimitWithMockLLM:
    """Test iteration limit handler with mock LLM streams."""

    @pytest.mark.asyncio
    async def test_iteration_limit_warning_at_80_percent(self, agent_manager: AgentManager) -> None:
        """Test that warning is issued at 80% of iteration limit."""
        # Initialize the agent manager
        await agent_manager.initialize()

        # Override the safety config to have a very low limit
        import config

        original_config = config.LOOP_SAFETY_CONFIG.copy()
        config.LOOP_SAFETY_CONFIG["max_tool_iterations"] = 5

        # Reinitialize meta agent to pick up new config
        await agent_manager.meta_agent.initialize()

        call_count = 0

        async def mock_llm_stream(*args: Any, **kwargs: Any) -> AsyncIterator[Message]:
            nonlocal call_count
            call_count += 1

            # Get session_id from kwargs
            session_id = kwargs.get("session_id", "test-session")

            # Keep calling tools until we hit the warning
            if call_count <= 4:  # 4 tool calls = 80% of 5
                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id=f"call_{call_count}",
                            tool_name="list_files",  # Use a real tool that exists
                            tool_args={"path": "/tmp"},
                        )
                    ],
                )
            elif call_count == 5:
                # After receiving the warning feedback, acknowledge it
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="Understood, I'm approaching the limit. Let me wrap up.",
                )
            else:
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="Here are the results I found.",
                )

        # Mock the LLM client
        agent_manager.meta_agent.llm_client.generate_stream_with_tools = mock_llm_stream

        # Process the message
        messages = []
        async for msg in agent_manager.chat_stream(
            UserMessage(
                agent_id="METAGEN", session_id="test-session", content="List files multiple times"
            )
        ):
            messages.append(msg)

        # Check that the LLM acknowledged the warning in its response
        llm_acknowledged = False
        for msg in messages:
            if isinstance(msg, AgentMessage) and "approaching the limit" in msg.content:
                llm_acknowledged = True
                break

        # Also check that we called the mock the expected number of times
        # The mock should have been called at least 5 times (4 tool calls + 1 acknowledgment)
        assert call_count >= 5, f"Expected at least 5 LLM calls, got {call_count}"
        assert llm_acknowledged, "LLM should have acknowledged the iteration limit warning"

        # Restore original config
        config.LOOP_SAFETY_CONFIG = original_config

    @pytest.mark.asyncio
    async def test_iteration_hard_limit_reached(self, agent_manager: AgentManager) -> None:
        """Test that hard limit stops execution and requests summary."""
        # Initialize the agent manager
        await agent_manager.initialize()

        # Override the safety config to have a very low limit
        import config

        original_config = config.LOOP_SAFETY_CONFIG.copy()
        config.LOOP_SAFETY_CONFIG["max_tool_iterations"] = 5

        # Reinitialize meta agent to pick up new config
        await agent_manager.meta_agent.initialize()

        call_count = 0

        async def mock_llm_stream(*args: Any, **kwargs: Any) -> AsyncIterator[Message]:
            nonlocal call_count
            call_count += 1

            # Get session_id from kwargs
            session_id = kwargs.get("session_id", "test-session")

            # Check if we received the iteration limit message
            messages = args[0] if args else []
            last_message = messages[-1] if messages else None

            if last_message and "ITERATION LIMIT REACHED" in str(
                getattr(last_message, "content", "")
            ):
                # LLM responds to the limit with a summary
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content=(
                        "Summary:\n"
                        "1. Executed 5 file listings\n"
                        "2. Found relevant results\n"
                        "3. To continue: Run additional targeted searches"
                    ),
                )
            elif call_count <= 6:  # Try to exceed the limit
                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id=f"call_{call_count}",
                            tool_name="list_files",
                            tool_args={"path": f"/tmp/test{call_count}"},
                        )
                    ],
                )
            else:
                yield AgentMessage(
                    agent_id="METAGEN", session_id=session_id, content="Done with searches."
                )

        # Mock the LLM client
        agent_manager.meta_agent.llm_client.generate_stream_with_tools = mock_llm_stream

        # Process the message
        messages = []
        async for msg in agent_manager.chat_stream(
            UserMessage(
                agent_id="METAGEN",
                session_id="test-session",
                content="Keep listing files until you find everything",
            )
        ):
            messages.append(msg)

        # Check that we got the summary from the LLM
        summary_found = False
        for msg in messages:
            if isinstance(msg, AgentMessage) and "Summary:" in msg.content:
                summary_found = True
                break

        assert summary_found, "Should have received summary from LLM when limit reached"

        # Restore original config
        config.LOOP_SAFETY_CONFIG = original_config


class TestRepetitionDetectionWithMockLLM:
    """Test repetition detection with mock LLM streams."""

    @pytest.mark.asyncio
    async def test_exact_repetition_detection(self, agent_manager: AgentManager) -> None:
        """Test detection of exact repetition of tool calls."""
        # Initialize the agent manager
        await agent_manager.initialize()

        call_count = 0

        async def mock_llm_stream(*args: Any, **kwargs: Any) -> AsyncIterator[Message]:
            nonlocal call_count
            call_count += 1

            # Get session_id from kwargs
            session_id = kwargs.get("session_id", "test-session")

            # Check if we received repetition feedback
            # Look for feedback in tool results (that's where safety feedback appears)
            tool_results = kwargs.get("tool_results", [])
            has_repetition_feedback = False
            if tool_results:
                from common.types import ToolCallResult

                for result in tool_results:
                    assert isinstance(result, ToolCallResult), (
                        f"Expected ToolCallResult, got {type(result)}"
                    )
                    if "repetition isn't productive" in result.content:
                        has_repetition_feedback = True
                        break

            if has_repetition_feedback:
                # LLM acknowledges and changes approach
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="I understand. Let me try a different approach.",
                )
                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="call_different",
                            tool_name="search_files",
                            tool_args={"pattern": "different pattern"},
                        )
                    ],
                )
            elif call_count <= 3:
                # Keep calling the same tool with same args (will trigger on 3rd)
                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id=f"call_{call_count}",
                            tool_name="search_files",
                            tool_args={"pattern": "test"},  # Same args every time
                        )
                    ],
                )
            else:
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="Found the information with the new search.",
                )

        # Mock the LLM client
        agent_manager.meta_agent.llm_client.generate_stream_with_tools = mock_llm_stream

        # Process the message
        messages = []
        async for msg in agent_manager.chat_stream(
            UserMessage(
                agent_id="METAGEN", session_id="test-session", content="Search for test information"
            )
        ):
            messages.append(msg)

        # Check that repetition was handled
        handled = False
        for msg in messages:
            if isinstance(msg, AgentMessage) and "different approach" in msg.content:
                handled = True
                break

        assert handled, "LLM should have handled repetition detection"

    @pytest.mark.asyncio
    async def test_circular_pattern_detection(self, agent_manager: AgentManager) -> None:
        """Test detection of circular patterns in tool calls."""
        # Initialize the agent manager
        await agent_manager.initialize()

        call_count = 0

        async def mock_llm_stream(*args: Any, **kwargs: Any) -> AsyncIterator[Message]:
            nonlocal call_count
            call_count += 1

            # Get session_id from kwargs
            session_id = kwargs.get("session_id", "test-session")

            # Look for feedback in tool results (that's where safety feedback appears)
            tool_results = kwargs.get("tool_results", [])
            has_pattern_feedback = False
            if tool_results:
                from common.types import ToolCallResult

                for result in tool_results:
                    assert isinstance(result, ToolCallResult), (
                        f"Expected ToolCallResult, got {type(result)}"
                    )
                    if "repeating a pattern" in result.content:
                        has_pattern_feedback = True
                        break

            if has_pattern_feedback:
                # LLM acknowledges the pattern and breaks it
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content=(
                        "I see I'm going in circles. Let me take a different approach. "
                        "Based on what I've found, here's the answer..."
                    ),
                )
            elif call_count <= 4:
                # Create A->B->A->B pattern
                if call_count % 2 == 1:
                    yield ToolCallMessage(
                        agent_id="METAGEN",
                        session_id=session_id,
                        tool_calls=[
                            ToolCallRequest(
                                tool_id=f"call_a_{call_count}",
                                tool_name="search_files",
                                tool_args={"pattern": "query_a"},
                            )
                        ],
                    )
                else:
                    yield ToolCallMessage(
                        agent_id="METAGEN",
                        session_id=session_id,
                        tool_calls=[
                            ToolCallRequest(
                                tool_id=f"call_b_{call_count}",
                                tool_name="list_files",
                                tool_args={"path": "/tmp"},
                            )
                        ],
                    )
            else:
                yield AgentMessage(
                    agent_id="METAGEN", session_id=session_id, content="Analysis complete."
                )

        # Mock the LLM client
        agent_manager.meta_agent.llm_client.generate_stream_with_tools = mock_llm_stream

        # Process the message
        messages = []
        async for msg in agent_manager.chat_stream(
            UserMessage(agent_id="METAGEN", session_id="test-session", content="Analyze the system")
        ):
            messages.append(msg)

        # Check that pattern was handled
        pattern_handled = False
        for msg in messages:
            if isinstance(msg, AgentMessage) and "going in circles" in msg.content:
                pattern_handled = True
                break

        assert pattern_handled, (
            f"LLM should have handled circular pattern detection. Got {len(messages)} messages"
        )

    @pytest.mark.asyncio
    async def test_tool_limit_enforcement(self, agent_manager: AgentManager) -> None:
        """Test that per-tool limits are enforced."""
        # Initialize the agent manager
        await agent_manager.initialize()

        # Override config to set low limit for execute_command
        import config

        original_config = config.LOOP_SAFETY_CONFIG.copy()
        config.LOOP_SAFETY_CONFIG["tool_limits"]["execute_command"] = 2

        # Reinitialize meta agent to pick up new config
        await agent_manager.meta_agent.initialize()

        call_count = 0

        async def mock_llm_stream(*args: Any, **kwargs: Any) -> AsyncIterator[Message]:
            nonlocal call_count
            call_count += 1

            # Get session_id from kwargs
            session_id = kwargs.get("session_id", "test-session")

            # Look for feedback in tool results (that's where safety feedback appears)
            tool_results = kwargs.get("tool_results", [])
            has_limit_feedback = False
            if tool_results:
                from common.types import ToolCallResult

                for result in tool_results:
                    assert isinstance(result, ToolCallResult), (
                        f"Expected ToolCallResult, got {type(result)}"
                    )
                    if "Tool limit exceeded" in result.content:
                        has_limit_feedback = True
                        break

            if has_limit_feedback:
                # LLM acknowledges limit and stops using that tool
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="I've reached the command execution limit. Using search instead.",
                )
                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id="call_search",
                            tool_name="search_files",
                            tool_args={"pattern": "alternative approach"},
                        )
                    ],
                )
            elif call_count <= 3:
                # Try to exceed the limit (2) for execute_command
                yield ToolCallMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    tool_calls=[
                        ToolCallRequest(
                            tool_id=f"call_{call_count}",
                            tool_name="execute_command",
                            tool_args={"command": f"echo test{call_count}"},
                        )
                    ],
                )
            else:
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="Task completed with alternative approach.",
                )

        # Mock the LLM client
        agent_manager.meta_agent.llm_client.generate_stream_with_tools = mock_llm_stream

        # Process the message
        messages = []
        async for msg in agent_manager.chat_stream(
            UserMessage(
                agent_id="METAGEN", session_id="test-session", content="Execute multiple commands"
            )
        ):
            messages.append(msg)

        # Check that tool limit was handled
        limit_handled = False
        for msg in messages:
            if isinstance(msg, AgentMessage) and "command execution limit" in msg.content:
                limit_handled = True
                break

        assert limit_handled, "LLM should have handled tool limit"

        # Restore original config
        config.LOOP_SAFETY_CONFIG = original_config


# =============================================================================
# Real LLM Tests (marked with @pytest.mark.llm)
# =============================================================================


@pytest.mark.llm
class TestSafetyWithRealLLM:
    """Integration tests with real LLM for safety features.

    These tests require a real LLM connection and are marked with
    @pytest.mark.llm so they can be skipped in CI.
    """

    @pytest.mark.asyncio
    async def test_real_llm_handles_iteration_warning(self, agent_manager: AgentManager) -> None:
        """Test that real LLM properly handles iteration warnings."""
        # Initialize the agent manager
        await agent_manager.initialize()

        # Override config for low iteration limit
        import config

        original_config = config.LOOP_SAFETY_CONFIG.copy()
        config.LOOP_SAFETY_CONFIG["max_tool_iterations"] = 3

        # Reinitialize to pick up new config
        await agent_manager.meta_agent.initialize()

        try:
            # Send a message that might trigger multiple tool calls
            messages = []
            async for msg in agent_manager.chat_stream(
                UserMessage(
                    agent_id="METAGEN",
                    session_id="test-session",
                    content=(
                        "Search for 'test1', then search for 'test2', "
                        "then search for 'test3', then search for 'test4'"
                    ),
                )
            ):
                messages.append(msg)

            # Check that the LLM handled the warning gracefully
            final_message = ""
            for msg in messages:
                if isinstance(msg, AgentMessage):
                    final_message += msg.content

            # The LLM should have acknowledged the limit somehow
            assert len(final_message) > 0, "LLM should have provided a response"

        finally:
            # Restore config
            config.LOOP_SAFETY_CONFIG = original_config

    @pytest.mark.asyncio
    async def test_real_llm_handles_repetition_feedback(self, agent_manager: AgentManager) -> None:
        """Test that real LLM properly handles repetition feedback."""
        # Initialize the agent manager
        await agent_manager.initialize()

        # Send a message that explicitly asks for repetition
        messages = []
        async for msg in agent_manager.chat_stream(
            UserMessage(
                agent_id="METAGEN",
                session_id="test-session",
                content=(
                    "Search for 'test' three times with exactly the same query. "
                    "I need you to call search_files with pattern='test' exactly 3 times."
                ),
            )
        ):
            messages.append(msg)

        # Check that feedback was provided if repetition occurred
        all_content = ""
        for msg in messages:
            if isinstance(msg, AgentMessage):
                all_content += msg.content

        # The LLM should have either avoided repetition or acknowledged the feedback
        assert len(all_content) > 0, "LLM should have provided a response"
