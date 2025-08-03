"""Anthropic Claude client with Instructor support."""

from typing import Any, AsyncIterator, Optional, Union

import instructor
from anthropic import AsyncAnthropic
from anthropic.types import Message as AnthropicMessage

from tools.base import Tool

from .base_provider_client import BaseProviderClient
from .models import get_model
from .types import (
    LLMMessage,
    LLMMessageRole,
    LLMStreamChunk,
    LLMStreamEvent,
    LLMStreamEventType,
    LLMTokenUsage,
)


class AnthropicClient(BaseProviderClient):
    """Anthropic Claude client for text generation."""

    def __init__(self, api_key: str, default_model: Optional[str] = None):
        """Initialize Anthropic client.

        Args:
            api_key: Anthropic API key
            default_model: Default model to use (e.g., 'claude-sonnet-4-20250514')
        """
        super().__init__(api_key)
        self.default_model = default_model or "claude-sonnet-4-20250514"
        self._client: Optional[AsyncAnthropic] = None
        self._instructor_client: Optional[instructor.AsyncInstructor] = None

    async def initialize(self) -> None:
        """Initialize the Anthropic client."""
        self._client = AsyncAnthropic(api_key=self.api_key)
        # Create instructor-patched client for structured outputs
        self._instructor_client = instructor.from_anthropic(self._client)

    def _convert_messages_to_anthropic(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """Convert our Message format to Anthropic's format."""
        anthropic_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == LLMMessageRole.SYSTEM:
                # System messages are handled separately in Anthropic
                continue

            # Handle tool result messages (TOOL role)
            if msg.role == LLMMessageRole.TOOL and msg.tool_call_results:
                content = []
                for result in msg.tool_call_results:
                    content.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": result.tool_call_id,
                            "content": result.content,
                            "is_error": result.is_error,
                        }
                    )
                anthropic_messages.append({"role": "user", "content": content})
            # Handle assistant messages with tool calls
            elif msg.role == LLMMessageRole.ASSISTANT and msg.tool_calls:
                content = []
                if msg.content:  # Include text content if present
                    content.append({"type": "text", "text": msg.content})
                for tool_call in msg.tool_calls:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.id,
                            "name": tool_call.name,
                            "input": tool_call.arguments,
                        }
                    )
                anthropic_messages.append({"role": "assistant", "content": content})
            # Regular messages
            else:
                anthropic_msg = {
                    "role": "user" if msg.role == LLMMessageRole.USER else "assistant",
                    "content": msg.content,
                }
                anthropic_messages.append(anthropic_msg)

        return anthropic_messages

    def _extract_system_message(self, messages: list[LLMMessage]) -> Optional[str]:
        """Extract system message content from messages."""
        for msg in messages:
            if msg.role == LLMMessageRole.SYSTEM:
                return msg.content
        return None

    def _parse_anthropic_response(
        self, response: AnthropicMessage, model: str, has_tools: bool = False
    ) -> LLMMessage:
        """Parse Anthropic response into our format."""
        content = ""
        tool_calls = []

        # Handle different content types
        if isinstance(response.content, str):
            content = response.content
        elif isinstance(response.content, list):
            for block in response.content:
                if hasattr(block, "type"):
                    if block.type == "text":
                        content += block.text
                    elif block.type == "tool_use" and has_tools:
                        tool_calls.append(
                            {"id": block.id, "name": block.name, "arguments": block.input}
                        )

        # Parse usage
        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = LLMTokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            )

        # Create response with tool calls if present
        response_data: dict[str, Any] = {
            "role": LLMMessageRole.ASSISTANT,
            "content": content,
            "usage": usage,
            "model": model,
            "finish_reason": getattr(response, "stop_reason", None),
        }

        # Add tool_calls if present
        if tool_calls:
            response_data["tool_calls"] = tool_calls

        return LLMMessage(**response_data)

    def _convert_tools_to_anthropic(self, tools: list[Tool]) -> list[dict[str, Any]]:
        """Convert Tool objects to Anthropic format."""
        # Convert Tool objects to dicts
        return [tool.model_dump() for tool in tools]

    async def generate(
        self,
        messages: list[LLMMessage],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        tools: Optional[list[Tool]] = None,
        **kwargs: Any,
    ) -> Union[LLMMessage, AsyncIterator[LLMStreamEvent]]:
        """Generate text from Anthropic Claude."""
        if not self._client:
            await self.initialize()

        model = model or self.default_model

        # Get model info for max tokens
        model_info = get_model(model)
        if max_tokens is None:
            # For streaming, we can use the full max_output_tokens
            # For non-streaming, Anthropic SDK limits to ~10 minutes worth
            if stream:
                max_tokens = model_info.max_output_tokens or 4096
            else:
                # Non-streaming is limited by Anthropic SDK to prevent timeouts
                # Use 8192 as a safe maximum for non-streaming calls
                max_tokens = min(model_info.max_output_tokens or 4096, 8192)

        # Prepare request
        anthropic_messages = self._convert_messages_to_anthropic(messages)
        system_message = self._extract_system_message(messages)

        request_params = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }

        if system_message:
            request_params["system"] = system_message

        # Add tools if provided
        if tools:
            request_params["tools"] = self._convert_tools_to_anthropic(tools)

        if stream:
            return self._stream_generate(request_params, model)
        else:
            if not self._client:
                raise RuntimeError("Anthropic client not initialized")
            response = await self._client.messages.create(**request_params)
            return self._parse_anthropic_response(response, model, tools is not None)

    async def _stream_generate(
        self, request_params: dict[str, Any], model: str
    ) -> AsyncIterator[LLMStreamEvent]:
        """Stream generation response from Anthropic."""
        if not self._client:
            raise RuntimeError("Anthropic client not initialized")
        async with self._client.messages.stream(**request_params) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        yield LLMStreamEvent(
                            type=LLMStreamEventType.CONTENT,
                            content=event.delta.text,
                            chunk=LLMStreamChunk(content=event.delta.text),
                        )
                elif event.type == "message_stop":
                    yield LLMStreamEvent(
                        type=LLMStreamEventType.CONTENT,
                        content="",
                        chunk=LLMStreamChunk(content="", finish_reason="stop"),
                        metadata={"finish_reason": "stop"},
                    )

    async def generate_structured(
        self,
        messages: list[LLMMessage],
        response_model: type,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        """Generate structured output using Instructor."""
        if not self._instructor_client:
            await self.initialize()

        model = model or self.default_model

        # Get model info for max tokens
        _ = get_model(model)  # TODO: Use model_info when needed
        if max_tokens is None:
            # For structured output, use a reasonable default
            # Even though instructor supports streaming, the Anthropic SDK still
            # enforces the 10-minute timeout for large max_tokens values
            max_tokens = 8192

        # Prepare request
        anthropic_messages = self._convert_messages_to_anthropic(messages)
        system_message = self._extract_system_message(messages)

        request_params = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_model": response_model,
            **kwargs,
        }

        if system_message:
            request_params["system"] = system_message

        if not self._instructor_client:
            raise RuntimeError("Anthropic client not initialized")
        return await self._instructor_client.messages.create(**request_params)

    async def close(self) -> None:
        """Close the client (Anthropic client doesn't need explicit closing)."""
        pass

    @property
    def name(self) -> str:
        """Client name."""
        return "Anthropic"
