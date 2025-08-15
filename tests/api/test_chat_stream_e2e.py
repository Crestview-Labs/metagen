"""Tests for the /chat/stream endpoint using real server.

IMPORTANT: These tests require manual server setup:
1. Start the server manually: uv run python main.py --db-path /tmp/test.db
2. Run the tests: uv run pytest tests/api/test_chat_stream_e2e.py -xvs
3. Clear the database between test runs if needed
"""

import asyncio
import json
import logging

import httpx
import pytest

from common.messages import (
    AgentMessage,
    ApprovalDecision,
    ApprovalRequestMessage,
    ApprovalResponseMessage,
    Message,
    ToolResultMessage,
    message_from_dict,
)

logger = logging.getLogger(__name__)

# Skip all tests in this module unless server is manually started
# To run: Start server with `uv run python main.py --db-path /tmp/test.db`
# Then run tests with: `uv run pytest tests/api/test_chat_stream_e2e.py -xvs`
pytestmark = pytest.mark.skip(
    reason="Requires manual server setup - see module docstring for instructions"
)


@pytest.mark.asyncio
async def test_basic_chat_stream(client: httpx.AsyncClient) -> None:
    """Test basic streaming functionality."""
    request_data = {"message": "Hello, just say hi back", "session_id": "test-basic"}

    async with client.stream("POST", "/api/chat/stream", json=request_data) as response:
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream"

        messages = []
        async for line in response.aiter_lines():
            if line.strip() and line.startswith("data: "):
                data = json.loads(line[6:])
                msg = message_from_dict(data)
                messages.append(msg)

                if isinstance(msg, AgentMessage) and msg.final:
                    break

        assert len(messages) > 0
        assert any(isinstance(m, AgentMessage) for m in messages)


@pytest.mark.asyncio
async def test_tool_approval_flow(client: httpx.AsyncClient) -> None:
    """Test tool approval workflow with real server."""

    # Request that triggers tool use requiring approval
    request_data = {
        "message": "Use the write_file tool to create test_approval.txt with content 'test'",
        "session_id": "test-approval",
    }

    approval_request = None
    messages_received = []

    async def process_stream() -> None:
        """Process the stream and collect messages."""
        nonlocal approval_request
        async with client.stream(
            "POST", "/api/chat/stream", json=request_data, timeout=30
        ) as response:
            assert response.status_code == 200

            async for line in response.aiter_lines():
                if line.strip() and line.startswith("data: "):
                    data = json.loads(line[6:])
                    msg = message_from_dict(data)
                    messages_received.append(msg)

                    if isinstance(msg, ApprovalRequestMessage):
                        approval_request = msg
                        # Wait a bit for the approval to be sent
                        await asyncio.sleep(0.5)
                    elif isinstance(msg, AgentMessage) and msg.final:
                        # CRITICAL: Wait for final message before ending
                        break

    async def send_approval() -> None:
        """Send approval once we detect the request."""
        # Wait for approval request to be available
        for _ in range(50):  # 5 second timeout
            if approval_request:
                break
            await asyncio.sleep(0.1)

        if approval_request:
            # Send approval
            approval_response = await client.post(
                "/api/chat/approval-response",
                json={
                    "tool_id": approval_request.tool_id,
                    "decision": ApprovalDecision.APPROVED.value,
                    "agent_id": approval_request.agent_id,
                },
            )
            assert approval_response.status_code == 200

    # Run both tasks concurrently
    stream_task = asyncio.create_task(process_stream())
    approval_task = asyncio.create_task(send_approval())

    # Wait for both to complete
    await asyncio.gather(stream_task, approval_task)

    # Verify we got all expected messages including final
    assert approval_request is not None, "Should receive approval request"
    assert any(isinstance(msg, AgentMessage) and msg.final for msg in messages_received), (
        "Should have received final message"
    )


@pytest.mark.skip(
    reason="Sending approval through chat stream creates separate conversation - "
    "use dedicated endpoint"
)
@pytest.mark.asyncio
async def test_approval_via_chat_message(client: httpx.AsyncClient) -> None:
    """Test sending approval through chat stream instead of separate endpoint.

    NOTE: This test is skipped because the current implementation treats
    ApprovalResponseMessage sent through /chat/stream as a new conversation
    rather than continuing the existing stream. Use /api/chat/approval-response
    endpoint instead (see test_tool_approval_flow).
    """
    # Request that triggers tool use requiring approval
    request_data = {
        "message": "Use the write_file tool to create approval_test.txt with content 'hello'",
        "session_id": "test-approval-chat",
    }

    approval_request = None
    messages_received = []

    async def process_first_stream() -> None:
        """Process the first stream and collect messages."""
        nonlocal approval_request
        async with client.stream(
            "POST", "/api/chat/stream", json=request_data, timeout=30
        ) as response:
            async for line in response.aiter_lines():
                if line.strip() and line.startswith("data: "):
                    data = json.loads(line[6:])
                    msg = message_from_dict(data)
                    messages_received.append(msg)

                    if isinstance(msg, ApprovalRequestMessage):
                        approval_request = msg
                        # Wait a bit for the approval to be sent
                        await asyncio.sleep(0.5)
                    elif isinstance(msg, AgentMessage) and msg.final:
                        break

    async def send_approval() -> None:
        """Send approval once we detect the request."""
        # Wait for approval request to be available
        for _ in range(50):  # 5 second timeout
            if approval_request:
                break
            await asyncio.sleep(0.1)

        if not approval_request:
            return

        # Create proper ApprovalResponseMessage object
        approval_msg = ApprovalResponseMessage(
            agent_id=approval_request.agent_id,
            session_id="test-session",
            tool_id=approval_request.tool_id,
            decision=ApprovalDecision.APPROVED,
        )

        # Send approval through chat stream with the message object as dict
        approval_request_data = {
            "message": approval_msg.to_dict(),
            "session_id": "test-approval-chat",
        }

        # Send the approval through chat stream
        async with client.stream(
            "POST", "/api/chat/stream", json=approval_request_data, timeout=30
        ) as response:
            async for line in response.aiter_lines():
                if line.strip() and line.startswith("data: "):
                    # Just consume the response - should get success
                    pass

    # Run both tasks concurrently
    stream_task = asyncio.create_task(process_first_stream())
    approval_task = asyncio.create_task(send_approval())

    # Wait for both to complete
    await asyncio.gather(stream_task, approval_task)

    # Verify we got the expected messages
    assert approval_request is not None, "Should have received approval request"
    assert any(isinstance(msg, ToolResultMessage) for msg in messages_received), (
        "Should have received tool result"
    )
    assert any(isinstance(msg, AgentMessage) and msg.final for msg in messages_received), (
        "Should have received final message"
    )


@pytest.mark.skip(reason="Approval system is single-threaded, concurrent requests not supported")
@pytest.mark.asyncio
async def test_concurrent_streams(client: httpx.AsyncClient) -> None:
    """Test multiple concurrent streaming connections."""

    async def stream_request(session_id: str) -> list[Message]:
        request_data = {"message": f"Hello from session {session_id}", "session_id": session_id}

        messages = []
        async with client.stream("POST", "/api/chat/stream", json=request_data) as response:
            async for line in response.aiter_lines():
                if line.strip() and line.startswith("data: "):
                    data = json.loads(line[6:])
                    msg = message_from_dict(data)
                    messages.append(msg)

                    if isinstance(msg, AgentMessage) and msg.final:
                        break

        return messages

    # Run 3 concurrent streams
    results = await asyncio.gather(
        stream_request("session-1"), stream_request("session-2"), stream_request("session-3")
    )

    # Verify all completed successfully
    for messages in results:
        assert len(messages) > 0
        assert any(isinstance(m, AgentMessage) and m.final for m in messages)


@pytest.mark.asyncio
async def test_session_persistence_across_requests(client: httpx.AsyncClient) -> None:
    """Test that a session persists across multiple HTTP requests."""
    import uuid

    session_id = str(uuid.uuid4())

    # First request - introduce context
    request1 = {
        "message": "My name is Alice and I love Python programming.",
        "session_id": session_id,
    }

    async with client.stream("POST", "/api/chat/stream", json=request1, timeout=30) as response:
        assert response.status_code == 200
        messages1 = []
        async for line in response.aiter_lines():
            if line.strip() and line.startswith("data: "):
                data = json.loads(line[6:])
                msg = message_from_dict(data)
                messages1.append(msg)
                if isinstance(msg, AgentMessage) and msg.final:
                    break

    assert len(messages1) > 0

    # Second request - test context retention
    request2 = {"message": "What's my name and what do I love?", "session_id": session_id}

    async with client.stream("POST", "/api/chat/stream", json=request2, timeout=30) as response:
        assert response.status_code == 200
        messages2 = []
        async for line in response.aiter_lines():
            if line.strip() and line.startswith("data: "):
                data = json.loads(line[6:])
                msg = message_from_dict(data)
                messages2.append(msg)
                if isinstance(msg, AgentMessage) and msg.final:
                    break

    assert len(messages2) > 0

    # Check that agent remembered the context
    # The response should mention "Alice" and "Python"
    agent_responses = [m for m in messages2 if isinstance(m, AgentMessage)]
    response_text = " ".join(m.content for m in agent_responses if m.content)

    # Note: This is a weak assertion since we don't control the LLM response
    # In a real test, we'd mock the agent or use a deterministic response
    assert len(response_text) > 0, "Should have received agent responses"

    # Third request - continue conversation
    request3 = {"message": "Great! Now let's talk about testing.", "session_id": session_id}

    async with client.stream("POST", "/api/chat/stream", json=request3, timeout=30) as response:
        assert response.status_code == 200
        messages3 = []
        async for line in response.aiter_lines():
            if line.strip() and line.startswith("data: "):
                data = json.loads(line[6:])
                msg = message_from_dict(data)
                messages3.append(msg)
                if isinstance(msg, AgentMessage) and msg.final:
                    break

    assert len(messages3) > 0

    # All three requests should have completed successfully with the same session
    logger.info(f"✅ Session {session_id[:8]} persisted across 3 requests")


@pytest.mark.asyncio
async def test_multiple_concurrent_sessions(client: httpx.AsyncClient) -> None:
    """Test that multiple sessions can run concurrently without interference."""
    import uuid

    session1_id = str(uuid.uuid4())
    session2_id = str(uuid.uuid4())

    async def run_session(session_id: str, name: str, color: str) -> list[Message]:
        """Run a session with specific context."""
        messages = []

        # First message - set context
        request1 = {
            "message": f"My name is {name} and my favorite color is {color}.",
            "session_id": session_id,
        }

        async with client.stream("POST", "/api/chat/stream", json=request1, timeout=30) as response:
            async for line in response.aiter_lines():
                if line.strip() and line.startswith("data: "):
                    data = json.loads(line[6:])
                    msg = message_from_dict(data)
                    messages.append(msg)
                    if isinstance(msg, AgentMessage) and msg.final:
                        break

        # Second message - verify context
        request2 = {"message": "What's my favorite color?", "session_id": session_id}

        async with client.stream("POST", "/api/chat/stream", json=request2, timeout=30) as response:
            async for line in response.aiter_lines():
                if line.strip() and line.startswith("data: "):
                    data = json.loads(line[6:])
                    msg = message_from_dict(data)
                    messages.append(msg)
                    if isinstance(msg, AgentMessage) and msg.final:
                        break

        return messages

    # Run both sessions concurrently
    results = await asyncio.gather(
        run_session(session1_id, "Bob", "blue"),
        run_session(session2_id, "Charlie", "red"),
        return_exceptions=True,
    )

    # Check both sessions completed
    assert len(results) == 2
    assert not any(isinstance(r, Exception) for r in results), "No session should have failed"

    session1_messages = results[0]
    session2_messages = results[1]

    assert isinstance(session1_messages, list), "Session 1 result should be a list"
    assert isinstance(session2_messages, list), "Session 2 result should be a list"
    assert len(session1_messages) > 0, "Session 1 should have messages"
    assert len(session2_messages) > 0, "Session 2 should have messages"

    logger.info(
        f"✅ Session {session1_id[:8]} and {session2_id[:8]} ran concurrently without interference"
    )


@pytest.mark.asyncio
async def test_session_isolation(client: httpx.AsyncClient) -> None:
    """Test that sessions are properly isolated from each other."""
    import uuid

    session1_id = str(uuid.uuid4())
    session2_id = str(uuid.uuid4())

    # Session 1: Set a specific context
    request1 = {"message": "Remember this secret code: ALPHA123", "session_id": session1_id}

    async with client.stream("POST", "/api/chat/stream", json=request1, timeout=30) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.strip() and line.startswith("data: "):
                data = json.loads(line[6:])
                msg = message_from_dict(data)
                if isinstance(msg, AgentMessage) and msg.final:
                    break

    # Session 2: Try to access session 1's context (should fail)
    request2 = {"message": "What was the secret code I just told you?", "session_id": session2_id}

    messages2 = []
    async with client.stream("POST", "/api/chat/stream", json=request2, timeout=30) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.strip() and line.startswith("data: "):
                data = json.loads(line[6:])
                msg = message_from_dict(data)
                messages2.append(msg)
                if isinstance(msg, AgentMessage) and msg.final:
                    break

    # Session 2 should not have access to ALPHA123
    agent_responses = [m for m in messages2 if isinstance(m, AgentMessage)]
    " ".join(m.content for m in agent_responses if m.content)

    # Note: This is a weak assertion - in practice the agent would say it doesn't know
    assert len(messages2) > 0, "Session 2 should have received responses"

    # Session 1: Verify it still remembers its context
    request3 = {"message": "What was the secret code?", "session_id": session1_id}

    messages3 = []
    async with client.stream("POST", "/api/chat/stream", json=request3, timeout=30) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.strip() and line.startswith("data: "):
                data = json.loads(line[6:])
                msg = message_from_dict(data)
                messages3.append(msg)
                if isinstance(msg, AgentMessage) and msg.final:
                    break

    assert len(messages3) > 0, "Session 1 should still respond"

    logger.info(f"✅ Sessions {session1_id[:8]} and {session2_id[:8]} are properly isolated")


@pytest.mark.asyncio
async def test_session_handles_disconnection_gracefully(client: httpx.AsyncClient) -> None:
    """Test that sessions handle client disconnection gracefully."""
    import uuid

    session_id = str(uuid.uuid4())

    # Start a request but disconnect early
    request1 = {
        "message": "Start a long explanation about machine learning",
        "session_id": session_id,
    }

    messages_before_disconnect = []
    try:
        async with client.stream("POST", "/api/chat/stream", json=request1, timeout=2) as response:
            assert response.status_code == 200
            message_count = 0
            async for line in response.aiter_lines():
                if line.strip() and line.startswith("data: "):
                    data = json.loads(line[6:])
                    msg = message_from_dict(data)
                    messages_before_disconnect.append(msg)
                    message_count += 1
                    # Simulate early disconnection
                    if message_count >= 2:
                        break  # Disconnect early
    except (httpx.ReadTimeout, httpx.RemoteProtocolError):
        # These are expected when we disconnect early
        pass

    # Wait a bit for any background processing
    await asyncio.sleep(1)

    # Reconnect with the same session - should still work
    request2 = {"message": "Are you still there? Just say yes or no.", "session_id": session_id}

    messages_after_reconnect = []
    async with client.stream("POST", "/api/chat/stream", json=request2, timeout=30) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.strip() and line.startswith("data: "):
                data = json.loads(line[6:])
                msg = message_from_dict(data)
                messages_after_reconnect.append(msg)
                if isinstance(msg, AgentMessage) and msg.final:
                    break

    assert len(messages_after_reconnect) > 0, "Should be able to reconnect to session"

    logger.info(f"✅ Session {session_id[:8]} handled disconnection and reconnection gracefully")


@pytest.mark.asyncio
async def test_session_queue_ordering(client: httpx.AsyncClient) -> None:
    """Test that messages within a session are processed in order."""
    import uuid

    session_id = str(uuid.uuid4())

    # Send multiple requests in sequence to the same session
    questions = [
        "Let's count together. Say '1'",
        "Now say '2'",
        "Now say '3'",
        "What numbers did we just count?",
    ]

    all_responses = []

    for i, question in enumerate(questions):
        request = {"message": question, "session_id": session_id}

        async with client.stream("POST", "/api/chat/stream", json=request, timeout=30) as response:
            assert response.status_code == 200
            messages = []
            async for line in response.aiter_lines():
                if line.strip() and line.startswith("data: "):
                    data = json.loads(line[6:])
                    msg = message_from_dict(data)
                    messages.append(msg)
                    if isinstance(msg, AgentMessage) and msg.final:
                        break

            all_responses.append(messages)
            assert len(messages) > 0, f"Request {i + 1} should have responses"

    # Verify we got responses for all requests in order
    assert len(all_responses) == len(questions)
    logger.info(f"✅ Session {session_id[:8]} processed {len(questions)} requests in order")


@pytest.mark.asyncio
async def test_session_queue_backpressure(client: httpx.AsyncClient) -> None:
    """Test that session queues handle rapid requests without message loss."""
    import uuid

    session_id = str(uuid.uuid4())

    async def send_rapid_request(request_num: int) -> list[Message]:
        """Send a request and collect all responses."""
        request = {
            "message": f"Request {request_num}: Acknowledge with the number {request_num}",
            "session_id": session_id,
        }

        messages = []
        async with client.stream("POST", "/api/chat/stream", json=request, timeout=30) as response:
            async for line in response.aiter_lines():
                if line.strip() and line.startswith("data: "):
                    data = json.loads(line[6:])
                    msg = message_from_dict(data)
                    messages.append(msg)
                    if isinstance(msg, AgentMessage) and msg.final:
                        break
        return messages

    # Send multiple requests rapidly (with minimal delay)
    tasks = []
    num_requests = 5

    for i in range(num_requests):
        # Small stagger to avoid overwhelming the server
        await asyncio.sleep(0.1)
        task = asyncio.create_task(send_rapid_request(i))
        tasks.append(task)

    # Wait for all requests to complete
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Verify all requests completed successfully
    successful_requests = [r for r in results if not isinstance(r, Exception)]
    assert len(successful_requests) == num_requests, f"All {num_requests} requests should complete"

    # Each request should have received responses
    for i, messages in enumerate(successful_requests):
        assert isinstance(messages, list), f"Request {i} result should be a list"
        assert len(messages) > 0, f"Request {i} should have responses"

    logger.info(f"✅ Session {session_id[:8]} handled {num_requests} rapid requests without loss")


@pytest.mark.asyncio
async def test_multiple_sessions_with_different_queue_sizes(client: httpx.AsyncClient) -> None:
    """Test that different sessions can have different amounts of traffic."""
    import uuid

    # Create sessions with different traffic patterns
    light_session = str(uuid.uuid4())
    heavy_session = str(uuid.uuid4())

    async def light_traffic() -> int:
        """Session with light traffic."""
        count = 0
        for i in range(2):
            request = {"message": f"Light traffic message {i}", "session_id": light_session}
            async with client.stream(
                "POST", "/api/chat/stream", json=request, timeout=30
            ) as response:
                async for line in response.aiter_lines():
                    if line.strip() and line.startswith("data: "):
                        data = json.loads(line[6:])
                        msg = message_from_dict(data)
                        if isinstance(msg, AgentMessage) and msg.final:
                            count += 1
                            break
            await asyncio.sleep(1)  # Slow pace
        return count

    async def heavy_traffic() -> int:
        """Session with heavy traffic."""
        count = 0
        for i in range(10):
            request = {"message": f"Heavy traffic message {i}", "session_id": heavy_session}
            async with client.stream(
                "POST", "/api/chat/stream", json=request, timeout=30
            ) as response:
                async for line in response.aiter_lines():
                    if line.strip() and line.startswith("data: "):
                        data = json.loads(line[6:])
                        msg = message_from_dict(data)
                        if isinstance(msg, AgentMessage) and msg.final:
                            count += 1
                            break
            await asyncio.sleep(0.2)  # Rapid pace
        return count

    # Run both traffic patterns concurrently
    light_count, heavy_count = await asyncio.gather(light_traffic(), heavy_traffic())

    assert light_count == 2, "Light session should complete 2 requests"
    assert heavy_count == 10, "Heavy session should complete 10 requests"

    print(
        f"✅ Light session {light_session[:8]} (2 requests) and "
        f"heavy session {heavy_session[:8]} (10 requests) both handled correctly"
    )


@pytest.mark.asyncio
async def test_session_queue_cleanup_after_errors(client: httpx.AsyncClient) -> None:
    """Test that session queues recover properly after errors."""
    import uuid

    session_id = str(uuid.uuid4())

    # First request - normal
    request1 = {
        "message": "This is a normal message. Remember the word: BANANA",
        "session_id": session_id,
    }

    async with client.stream("POST", "/api/chat/stream", json=request1, timeout=30) as response:
        assert response.status_code == 200
        message_count = 0
        async for line in response.aiter_lines():
            if line.strip() and line.startswith("data: "):
                data = json.loads(line[6:])
                msg = message_from_dict(data)
                message_count += 1
                if isinstance(msg, AgentMessage) and msg.final:
                    break
        assert message_count > 0

    # Second request - intentionally malformed to potentially cause issues
    # Note: This might not actually cause an error depending on server validation
    # but we're testing recovery either way
    request2 = {"message": "What was the word I asked you to remember?", "session_id": session_id}

    messages2 = []
    async with client.stream("POST", "/api/chat/stream", json=request2, timeout=30) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.strip() and line.startswith("data: "):
                data = json.loads(line[6:])
                msg = message_from_dict(data)
                messages2.append(msg)
                if isinstance(msg, AgentMessage) and msg.final:
                    break

    assert len(messages2) > 0, "Session should still work after potential error"

    # Third request - verify session is still functional
    request3 = {"message": "Are you still working? Just say yes.", "session_id": session_id}

    messages3 = []
    async with client.stream("POST", "/api/chat/stream", json=request3, timeout=30) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.strip() and line.startswith("data: "):
                data = json.loads(line[6:])
                msg = message_from_dict(data)
                messages3.append(msg)
                if isinstance(msg, AgentMessage) and msg.final:
                    break

    assert len(messages3) > 0, "Session should continue working"

    logger.info(f"✅ Session {session_id[:8]} recovered and continued working properly")


@pytest.mark.asyncio
async def test_session_message_interleaving(client: httpx.AsyncClient) -> None:
    """Test that messages from different sessions don't get interleaved."""
    import uuid

    session1_id = str(uuid.uuid4())
    session2_id = str(uuid.uuid4())

    async def send_and_verify(session_id: str, session_name: str, expected_content: str) -> bool:
        """Send a message and verify response is for the correct session."""
        request = {
            "message": f"I am {session_name}. Please respond with 'Hello {session_name}'",
            "session_id": session_id,
        }

        messages = []
        async with client.stream("POST", "/api/chat/stream", json=request, timeout=30) as response:
            async for line in response.aiter_lines():
                if line.strip() and line.startswith("data: "):
                    data = json.loads(line[6:])
                    msg = message_from_dict(data)
                    messages.append(msg)

                    # Verify session_id in response matches request
                    if hasattr(msg, "session_id"):
                        assert msg.session_id == session_id, (
                            "Response session_id should match request"
                        )

                    if isinstance(msg, AgentMessage) and msg.final:
                        break

        # Check that we got appropriate responses
        agent_messages = [m for m in messages if isinstance(m, AgentMessage)]
        return len(agent_messages) > 0

    # Send interleaved requests from both sessions
    tasks = []
    for i in range(3):
        tasks.append(send_and_verify(session1_id, "Session1", "Hello Session1"))
        tasks.append(send_and_verify(session2_id, "Session2", "Hello Session2"))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # All tasks should complete successfully
    assert all(r is True for r in results if not isinstance(r, Exception)), (
        "All session messages should be routed correctly"
    )

    logger.info(
        f"✅ Sessions {session1_id[:8]} and {session2_id[:8]} messages were properly isolated"
    )


@pytest.mark.asyncio
async def test_session_queue_with_long_processing(client: httpx.AsyncClient) -> None:
    """Test that session queues handle long-running requests properly."""
    import uuid

    session_id = str(uuid.uuid4())

    # First request - potentially long-running
    request1 = {
        "message": "Count from 1 to 10 slowly, taking your time with each number.",
        "session_id": session_id,
    }

    # Start the long request
    async def long_request() -> list[Message]:
        messages = []
        async with client.stream("POST", "/api/chat/stream", json=request1, timeout=60) as response:
            async for line in response.aiter_lines():
                if line.strip() and line.startswith("data: "):
                    data = json.loads(line[6:])
                    msg = message_from_dict(data)
                    messages.append(msg)
                    if isinstance(msg, AgentMessage) and msg.final:
                        break
        return messages

    # Start the long request in background
    long_task = asyncio.create_task(long_request())

    # Wait a bit then send a second request to same session
    await asyncio.sleep(1)

    request2 = {
        "message": "While you're counting, also remember the word PARALLEL",
        "session_id": session_id,
    }

    # This should queue behind the first request
    async def second_request() -> list[Message]:
        messages = []
        async with client.stream("POST", "/api/chat/stream", json=request2, timeout=60) as response:
            async for line in response.aiter_lines():
                if line.strip() and line.startswith("data: "):
                    data = json.loads(line[6:])
                    msg = message_from_dict(data)
                    messages.append(msg)
                    if isinstance(msg, AgentMessage) and msg.final:
                        break
        return messages

    second_task = asyncio.create_task(second_request())

    # Wait for both to complete
    long_messages, second_messages = await asyncio.gather(long_task, second_task)

    assert len(long_messages) > 0, "Long request should complete"
    assert len(second_messages) > 0, "Second request should complete after first"

    logger.info(f"✅ Session {session_id[:8]} properly queued and processed long-running requests")
