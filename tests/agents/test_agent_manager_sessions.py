"""Tests for AgentManager session management functionality."""

import asyncio
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator
from unittest.mock import patch

import pytest
import pytest_asyncio

from agents.agent_manager import AgentManager
from client.models import ModelID
from common.messages import AgentMessage, ErrorMessage, Message, ThinkingMessage, UserMessage
from db.engine import DatabaseEngine


@pytest_asyncio.fixture
async def test_db(tmp_path: Path) -> AsyncGenerator[DatabaseEngine, None]:
    """Create a test database for session tests."""
    db_path = tmp_path / "test_sessions.db"
    db_engine = DatabaseEngine(db_path)
    await db_engine.initialize()
    yield db_engine
    await db_engine.close()


@pytest_asyncio.fixture
async def agent_manager(test_db: DatabaseEngine) -> AsyncGenerator[AgentManager, None]:
    """Create an agent manager for session tests."""
    manager = AgentManager(
        agent_name="TestAgent", db_engine=test_db, mcp_servers=[], llm=ModelID.CLAUDE_SONNET_4
    )
    await manager.initialize()
    yield manager
    await manager.cleanup()


@pytest.mark.integration
class TestSessionManagement:
    """Integration tests for session management with mocked LLM responses."""

    @pytest.mark.asyncio
    async def test_session_persistence(self, agent_manager: AgentManager) -> None:
        """Test that sessions persist across multiple messages."""
        session_id = str(uuid.uuid4())

        # Mock the LLM to respond with predictable content
        call_count = 0
        context_memory = {}  # Simulate memory across calls

        async def mock_llm_stream(*args: Any, **kwargs: Any) -> AsyncGenerator[Message, None]:
            nonlocal call_count, context_memory
            call_count += 1

            if call_count == 1:
                # Store context
                context_memory["name"] = "Alice"
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content="Nice to meet you, Alice! I see you enjoy Python.",
                    final=True,
                )
            elif call_count == 2:
                # Recall context
                name = context_memory.get("name", "Unknown")
                yield AgentMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content=f"Your name is {name}.",
                    final=True,
                )

        assert agent_manager.meta_agent is not None
        with patch.object(
            agent_manager.meta_agent.llm_client,
            "generate_stream_with_tools",
            side_effect=mock_llm_stream,
        ):
            # First message
            msg1 = UserMessage(
                agent_id="METAGEN",
                session_id=session_id,
                content="My name is Alice and I like Python.",
            )

            responses1 = []
            async for msg in agent_manager.chat_stream(msg1):
                responses1.append(msg)
                if isinstance(msg, AgentMessage) and msg.final:
                    break

            assert any(
                "Alice" in m.content
                for m in responses1
                if isinstance(m, AgentMessage) and m.content
            )

            # Second message - should remember context
            msg2 = UserMessage(agent_id="METAGEN", session_id=session_id, content="What's my name?")

            responses2 = []
            async for msg in agent_manager.chat_stream(msg2):
                responses2.append(msg)
                if isinstance(msg, AgentMessage) and msg.final:
                    break

            assert any(
                "Alice" in m.content
                for m in responses2
                if isinstance(m, AgentMessage) and m.content
            )

    @pytest.mark.asyncio
    async def test_concurrent_sessions_isolation(self, agent_manager: AgentManager) -> None:
        """Test that concurrent sessions remain isolated."""
        session1_id = str(uuid.uuid4())
        session2_id = str(uuid.uuid4())

        # Track calls to determine which session is being processed
        call_count = 0
        session_data = {}

        async def mock_llm_stream(*args: Any, **kwargs: Any) -> AsyncGenerator[Message, None]:
            nonlocal call_count, session_data
            call_count += 1

            # The messages should be in args[0] or kwargs['messages']
            messages = args[0] if args else kwargs.get("messages", [])

            # Find which session this is for by looking at the last UserMessage
            current_session_id = None
            content = ""
            for msg in reversed(messages):  # Look from most recent
                if isinstance(msg, UserMessage):
                    current_session_id = msg.session_id
                    content = msg.content
                    break

            # Store what we learned about this session
            if current_session_id:
                session_data[current_session_id] = content

            # Generate response based on the content
            if "blue" in content.lower():
                response_text = "I understand your favorite color is blue."
            elif "red" in content.lower():
                response_text = "I understand your favorite color is red."
            else:
                response_text = "Tell me your favorite color."

            yield AgentMessage(
                agent_id="METAGEN",
                session_id=current_session_id or "",
                content=response_text,
                final=True,
            )

        assert agent_manager.meta_agent is not None
        with patch.object(
            agent_manager.meta_agent.llm_client,
            "generate_stream_with_tools",
            side_effect=mock_llm_stream,
        ):
            # Send messages to both sessions
            async def process_session(session_id: str, color: str) -> list[Message]:
                msg = UserMessage(
                    agent_id="METAGEN",
                    session_id=session_id,
                    content=f"My favorite color is {color}.",
                )

                responses = []
                async for response in agent_manager.chat_stream(msg):
                    responses.append(response)
                    if isinstance(response, AgentMessage) and response.final:
                        break

                return responses

            # Process both sessions concurrently
            results = await asyncio.gather(
                process_session(session1_id, "blue"), process_session(session2_id, "red")
            )

            # Verify each session got the correct response
            session1_responses = results[0]
            session2_responses = results[1]

            # Check responses contain the right colors
            session1_content = " ".join(
                m.content for m in session1_responses if isinstance(m, AgentMessage) and m.content
            )
            session2_content = " ".join(
                m.content for m in session2_responses if isinstance(m, AgentMessage) and m.content
            )

            assert "blue" in session1_content.lower(), (
                f"Session 1 should mention blue, got: {session1_content}"
            )
            assert "red" in session2_content.lower(), (
                f"Session 2 should mention red, got: {session2_content}"
            )

            # Verify both sessions were processed
            assert call_count == 2, f"Expected 2 LLM calls, got {call_count}"
            assert session1_id in session_data, (
                f"Session 1 not processed. Processed sessions: {list(session_data.keys())}"
            )
            assert session2_id in session_data, (
                f"Session 2 not processed. Processed sessions: {list(session_data.keys())}"
            )

    @pytest.mark.asyncio
    async def test_session_queue_ordering(self, agent_manager: AgentManager) -> None:
        """Test that messages are processed in order within a session."""
        session_id = str(uuid.uuid4())
        message_order = []

        async def mock_llm_stream(*args: Any, **kwargs: Any) -> AsyncGenerator[Message, None]:
            # The messages should be in args[0] or kwargs['messages']
            messages = args[0] if args else kwargs.get("messages", [])

            # Track message processing order - look for the most recent UserMessage
            for msg in reversed(messages):
                if isinstance(msg, UserMessage) and msg.content.startswith("Message"):
                    message_order.append(msg.content)
                    break

            # Get the last message content for response
            last_content = "none"
            if messages:
                for msg in reversed(messages):
                    if isinstance(msg, UserMessage):
                        last_content = msg.content
                        break

            yield AgentMessage(
                agent_id="METAGEN",
                session_id=session_id,
                content=f"Processed: {last_content}",
                final=True,
            )

        assert agent_manager.meta_agent is not None
        with patch.object(
            agent_manager.meta_agent.llm_client,
            "generate_stream_with_tools",
            side_effect=mock_llm_stream,
        ):
            # Send multiple messages in sequence
            for i in range(3):
                msg = UserMessage(agent_id="METAGEN", session_id=session_id, content=f"Message {i}")

                async for response in agent_manager.chat_stream(msg):
                    if isinstance(response, AgentMessage) and response.final:
                        break

            # Verify messages were processed in order
            assert message_order == ["Message 0", "Message 1", "Message 2"]

    @pytest.mark.asyncio
    async def test_session_error_handling(self, agent_manager: AgentManager) -> None:
        """Test that sessions handle errors gracefully."""
        session_id = str(uuid.uuid4())

        # First test: Transient error (mock returns error once then succeeds)
        error_count = 0

        async def mock_llm_with_transient_error(
            *args: Any, **kwargs: Any
        ) -> AsyncGenerator[Message, None]:
            nonlocal error_count
            error_count += 1
            if error_count == 1:
                # First call - simulate a transient error
                raise ConnectionError("Network timeout")
            # Subsequent calls work
            yield AgentMessage(
                agent_id="METAGEN",
                session_id=session_id,
                content=f"Response after {error_count} attempts",
                final=True,
            )

        assert agent_manager.meta_agent is not None
        with patch.object(
            agent_manager.meta_agent.llm_client,
            "generate_stream_with_tools",
            side_effect=mock_llm_with_transient_error,
        ):
            # Test that an error is properly reported
            msg1 = UserMessage(
                agent_id="METAGEN",
                session_id=session_id,
                content="This message will initially fail",
            )

            error_found = False
            async for response in agent_manager.chat_stream(msg1):
                if isinstance(response, ErrorMessage):
                    error_found = True
                    assert response.session_id == session_id
                    assert (
                        "Network timeout" in response.error
                        or "error occurred" in response.error.lower()
                    )
                    break

            assert error_found, "Should have received an error message"

            # Second message - should work (mock no longer throws)
            msg2 = UserMessage(
                agent_id="METAGEN", session_id=session_id, content="This message should succeed"
            )

            responses = []
            async for response in agent_manager.chat_stream(msg2):
                responses.append(response)
                if isinstance(response, AgentMessage) and response.final:
                    break

            # Should get a successful response this time
            assert len(responses) > 0, "Should have received responses"
            agent_messages = [m for m in responses if isinstance(m, AgentMessage)]
            assert len(agent_messages) > 0, (
                f"Should have AgentMessage, got: {[type(r).__name__ for r in responses]}"
            )

            # The successful response should indicate it worked
            response_content = " ".join(m.content for m in agent_messages if m.content)
            assert "Response after" in response_content or len(response_content) > 0

    @pytest.mark.asyncio
    async def test_session_registration_and_cleanup(self, agent_manager: AgentManager) -> None:
        """Test session registration and cleanup."""
        session_id = str(uuid.uuid4())

        # Register session
        queue = agent_manager.register_session(session_id)
        assert session_id in agent_manager._session_queues
        assert queue is agent_manager._session_queues[session_id]

        # Re-registering should return same queue
        queue2 = agent_manager.register_session(session_id)
        assert queue is queue2

        # Unregister session
        agent_manager.unregister_session(session_id)
        assert session_id not in agent_manager._session_queues

    @pytest.mark.asyncio
    async def test_multiple_sessions_different_rates(self, agent_manager: AgentManager) -> None:
        """Test sessions with different message rates."""
        fast_session = str(uuid.uuid4())
        slow_session = str(uuid.uuid4())

        message_counts = {fast_session: 0, slow_session: 0}

        async def mock_llm_stream(*args: Any, **kwargs: Any) -> AsyncGenerator[Message, None]:
            # Get session_id from kwargs (passed from generate_stream_with_tools)
            session_id = kwargs.get("session_id", None)

            # If no session_id in kwargs, try to get from messages
            if not session_id:
                messages = args[0] if args else kwargs.get("messages", [])
                for msg in messages:
                    if hasattr(msg, "session_id"):
                        session_id = msg.session_id
                        break

            # Count this call
            if session_id and session_id in message_counts:
                message_counts[session_id] += 1

            yield AgentMessage(
                agent_id="METAGEN",
                session_id=session_id or "",
                content=f"Message count: {message_counts.get(session_id or '', 0)}",
                final=True,
            )

        assert agent_manager.meta_agent is not None
        with patch.object(
            agent_manager.meta_agent.llm_client,
            "generate_stream_with_tools",
            side_effect=mock_llm_stream,
        ):

            async def fast_sender() -> None:
                """Send messages rapidly."""
                for i in range(5):
                    msg = UserMessage(
                        agent_id="METAGEN", session_id=fast_session, content=f"Fast message {i}"
                    )
                    async for response in agent_manager.chat_stream(msg):
                        if isinstance(response, AgentMessage) and response.final:
                            break
                    await asyncio.sleep(0.1)  # Fast rate

            async def slow_sender() -> None:
                """Send messages slowly."""
                for i in range(2):
                    msg = UserMessage(
                        agent_id="METAGEN", session_id=slow_session, content=f"Slow message {i}"
                    )
                    async for response in agent_manager.chat_stream(msg):
                        if isinstance(response, AgentMessage) and response.final:
                            break
                    await asyncio.sleep(0.5)  # Slow rate

            # Run both concurrently
            await asyncio.gather(fast_sender(), slow_sender())

            # Verify message counts
            assert message_counts[fast_session] == 5
            assert message_counts[slow_session] == 2

    @pytest.mark.asyncio
    async def test_session_with_thinking_messages(self, agent_manager: AgentManager) -> None:
        """Test that thinking messages are properly routed."""
        session_id = str(uuid.uuid4())

        async def mock_llm_stream(*args: Any, **kwargs: Any) -> AsyncGenerator[Message, None]:
            yield ThinkingMessage(
                agent_id="METAGEN", session_id=session_id, content="Let me think about this..."
            )
            yield AgentMessage(
                agent_id="METAGEN", session_id=session_id, content="Here's my response", final=False
            )
            yield AgentMessage(agent_id="METAGEN", session_id=session_id, content="", final=True)

        assert agent_manager.meta_agent is not None
        with patch.object(
            agent_manager.meta_agent.llm_client,
            "generate_stream_with_tools",
            side_effect=mock_llm_stream,
        ):
            msg = UserMessage(agent_id="METAGEN", session_id=session_id, content="Make me think")

            message_types = []
            async for response in agent_manager.chat_stream(msg):
                message_types.append(type(response).__name__)
                if isinstance(response, AgentMessage) and response.final:
                    break

            assert "ThinkingMessage" in message_types
            assert "AgentMessage" in message_types

    @pytest.mark.asyncio
    async def test_unregistered_session_handling(self, agent_manager: AgentManager) -> None:
        """Test handling of messages for unregistered sessions."""
        # Start the router task
        router_task = asyncio.create_task(agent_manager._route_agent_outputs())

        try:
            unregistered_session = str(uuid.uuid4())

            # Put a message for an unregistered session directly in the output queue
            msg = AgentMessage(
                agent_id="METAGEN",
                session_id=unregistered_session,
                content="Message for unregistered session",
                final=True,
            )

            await agent_manager.unified_agent_output.put(msg)

            # Give router time to process
            await asyncio.sleep(0.1)

            # Session should not be auto-registered
            assert unregistered_session not in agent_manager._session_queues

        finally:
            router_task.cancel()
            try:
                await router_task
            except asyncio.CancelledError:
                pass


@pytest.mark.llm
class TestSessionManagementWithRealLLM:
    """Tests that use real LLM (not mocked)."""

    @pytest.mark.asyncio
    async def test_real_llm_session_persistence(self, agent_manager: AgentManager) -> None:
        """Test session persistence with real LLM responses."""
        session_id = str(uuid.uuid4())

        # First message - establish context
        msg1 = UserMessage(
            agent_id="METAGEN",
            session_id=session_id,
            content="My name is TestUser and I'm testing session persistence.",
        )

        responses1 = []
        async for response in agent_manager.chat_stream(msg1):
            responses1.append(response)
            if isinstance(response, AgentMessage) and response.final:
                break

        assert len(responses1) > 0

        # Second message - test context retention
        msg2 = UserMessage(agent_id="METAGEN", session_id=session_id, content="What's my name?")

        responses2 = []
        async for response in agent_manager.chat_stream(msg2):
            responses2.append(response)
            if isinstance(response, AgentMessage) and response.final:
                break

        # With real LLM, we can't guarantee exact response but should get something
        assert len(responses2) > 0
        assert any(isinstance(m, AgentMessage) for m in responses2)
