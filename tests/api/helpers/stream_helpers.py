"""Helper utilities for parsing and consuming SSE streams in tests."""

import asyncio
import json
import logging
from typing import Callable, Optional

from httpx import AsyncClient, Response

from api.models.chat import ChatRequest
from common.messages import AgentMessage, ApprovalRequestMessage, Message, message_from_dict

logger = logging.getLogger(__name__)


async def parse_sse_line(line: str) -> Optional[Message]:
    """Parse a single SSE line into a Message object.

    Args:
        line: Raw SSE line (e.g., "data: {...json...}")

    Returns:
        Parsed Message object or None if not a data line
    """
    if not line.startswith("data: "):
        return None

    try:
        json_str = line[6:]  # Remove "data: " prefix
        data = json.loads(json_str)

        # Check for completion signal (not a Message type)
        if data.get("type") == "complete":
            return None  # Handle completion separately

        # Convert dict to proper Message type
        return message_from_dict(data)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse SSE line: {line}, error: {e}")
        return None


async def parse_sse_stream(response: Response) -> list[Message]:
    """Parse SSE stream into list of Message objects.

    Args:
        response: HTTP response with SSE stream

    Returns:
        List of parsed Message objects
    """
    messages: list[Message] = []

    async for line in response.aiter_lines():
        if line.strip():
            message = await parse_sse_line(line)
            if message:
                messages.append(message)
                logger.debug(f"Parsed message: {type(message).__name__}")

    return messages


async def consume_stream_until(
    response: Response, condition: Callable[[Message], bool], timeout: float = 30.0
) -> Optional[Message]:
    """Consume stream until condition is met or timeout.

    Args:
        response: HTTP response with SSE stream
        condition: Function that returns True when desired message is found
        timeout: Maximum time to wait in seconds

    Returns:
        First message matching condition or None if timeout
    """
    start_time = asyncio.get_event_loop().time()

    async for line in response.aiter_lines():
        if asyncio.get_event_loop().time() - start_time > timeout:
            logger.warning(f"Timeout waiting for condition after {timeout}s")
            return None

        if line.strip():
            message = await parse_sse_line(line)
            if message and condition(message):
                return message

    return None


def extract_messages_by_type(messages: list[Message], message_type: type[Message]) -> list[Message]:
    """Filter messages by type.

    Args:
        messages: List of Message objects
        message_type: Message class to filter for (e.g., AgentMessage, ThinkingMessage)

    Returns:
        Filtered list of messages matching the type
    """
    return [msg for msg in messages if isinstance(msg, message_type)]


async def wait_for_message_type(
    response: Response, message_type: type[Message], timeout: float = 10.0
) -> Optional[Message]:
    """Wait for a specific message type in the stream.

    Args:
        response: HTTP response with SSE stream
        message_type: Message class to wait for
        timeout: Maximum time to wait

    Returns:
        First message of the specified type or None if timeout
    """
    return await consume_stream_until(response, lambda msg: isinstance(msg, message_type), timeout)


async def collect_stream_with_timeout(
    client: AsyncClient, chat_request: ChatRequest, timeout: float = 30.0
) -> list[Message]:
    """Make a streaming request and collect all messages with timeout.

    Args:
        client: HTTP client
        chat_request: Typed ChatRequest object
        timeout: Maximum time to wait for stream completion

    Returns:
        List of all Message objects from the stream
    """
    messages: list[Message] = []

    async with client.stream(
        "POST", "/api/chat/stream", json=chat_request.model_dump(), timeout=timeout
    ) as response:
        async for line in response.aiter_lines():
            if line.strip():
                # Parse message
                message = await parse_sse_line(line)
                if message:
                    messages.append(message)

                    # Check if this is the final AgentMessage
                    if isinstance(message, AgentMessage) and message.final:
                        break

    return messages


def validate_sse_format(response: Response) -> None:
    """Validate that response has correct SSE headers.

    Args:
        response: HTTP response to validate

    Raises:
        AssertionError: If headers are incorrect
    """
    assert response.headers.get("content-type") == "text/event-stream"
    assert response.headers.get("cache-control") == "no-cache"
    assert response.headers.get("connection") == "keep-alive"


async def stream_until_complete(
    client: AsyncClient, chat_request: ChatRequest, max_messages: int = 1000
) -> tuple[list[Message], bool]:
    """Stream messages until completion or max messages reached.

    Args:
        client: HTTP client
        chat_request: Typed ChatRequest object
        max_messages: Maximum messages to collect

    Returns:
        Tuple of (list of Message objects, whether stream completed normally)
    """
    messages: list[Message] = []
    completed = False

    async with client.stream(
        "POST", "/api/chat/stream", json=chat_request.model_dump(), timeout=60.0
    ) as response:
        validate_sse_format(response)

        async for line in response.aiter_lines():
            if line.strip():
                # Parse message
                message = await parse_sse_line(line)
                if message:
                    messages.append(message)

                    # Check if this is the final AgentMessage
                    if isinstance(message, AgentMessage) and message.final:
                        completed = True
                        break

                    if len(messages) >= max_messages:
                        logger.warning(f"Reached max messages limit: {max_messages}")
                        break

    return messages, completed


async def get_final_agent_response(messages: list[Message]) -> Optional[AgentMessage]:
    """Extract the final agent response from a list of messages.

    Args:
        messages: List of Message objects

    Returns:
        The final AgentMessage with final=True, or None if not found
    """
    agent_messages = extract_messages_by_type(messages, AgentMessage)
    for msg in reversed(agent_messages):
        if msg.final:
            return msg
    return None


async def wait_for_approval_request(
    response: Response, timeout: float = 10.0
) -> Optional[ApprovalRequestMessage]:
    """Wait for an approval request message in the stream.

    Args:
        response: HTTP response with SSE stream
        timeout: Maximum time to wait

    Returns:
        ApprovalRequestMessage or None if timeout
    """
    message = await wait_for_message_type(response, ApprovalRequestMessage, timeout)
    return message if isinstance(message, ApprovalRequestMessage) else None


async def verify_message_sequence(
    messages: list[Message], expected_types: list[type[Message]]
) -> bool:
    """Verify that messages appear in expected sequence.

    Args:
        messages: List of Message objects
        expected_types: Expected message types in order

    Returns:
        True if sequence matches (allowing other messages in between)
    """
    type_index = 0
    for msg in messages:
        if type_index < len(expected_types) and isinstance(msg, expected_types[type_index]):
            type_index += 1

    return type_index == len(expected_types)
