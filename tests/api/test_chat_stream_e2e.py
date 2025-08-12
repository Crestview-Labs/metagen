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
            tool_id=approval_request.tool_id,
            decision=ApprovalDecision.APPROVED,
            agent_id=approval_request.agent_id,
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
