"""OpenAI client with Instructor support."""

import json
import os
from typing import Any, AsyncIterator, Optional, Union

import instructor
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from .base_client import (
    BaseClient,
    GenerationResponse,
    Message,
    Role,
    StreamChunk,
    StreamEvent,
    StreamEventType,
    Usage,
)
from .models import ModelID, get_model


class OpenAIClient(BaseClient):
    """OpenAI client for text generation."""

    def __init__(self, api_key: Optional[str] = None, default_model: Optional[str] = None):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
            default_model: Default model to use (e.g., 'gpt-4o-mini')
        """
        super().__init__(api_key)
        self.default_model = default_model or "gpt-4o-mini"
        self._client: Optional[AsyncOpenAI] = None
        self._instructor_client: Optional[instructor.AsyncInstructor] = None

    def _get_api_key(self) -> str:
        """Get OpenAI API key from environment or secrets file."""
        # Try environment first
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return api_key

        # Try secrets file
        secrets = self.load_secrets_from_file()
        api_key = secrets.get("OPENAI_API_KEY")
        if api_key:
            return api_key

        raise ValueError(
            "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
            "or add it to .env file in project root"
        )

    async def initialize(self) -> None:
        """Initialize the OpenAI client."""
        self._client = AsyncOpenAI(api_key=self.api_key)
        # Create instructor-patched client for structured outputs
        self._instructor_client = instructor.from_openai(self._client)

    def _convert_messages_to_openai(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert our Message format to OpenAI's format."""
        openai_messages = []

        for msg in messages:
            # Handle tool result messages
            if msg.tool_results:
                # OpenAI expects tool results as assistant messages with tool_call_id
                for result in msg.tool_results:
                    openai_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": result.tool_call_id,
                            "name": result.tool_name,
                            "content": result.content,
                        }
                    )
            # Handle assistant messages with tool calls
            elif msg.role == Role.ASSISTANT and msg.tool_calls:
                content_parts = []
                if msg.content:
                    content_parts.append({"type": "text", "text": msg.content})

                # Add tool calls
                tool_calls = []
                for tool_call in msg.tool_calls:
                    tool_calls.append(
                        {
                            "id": tool_call.get("id"),
                            "type": "function",
                            "function": {
                                "name": tool_call.get("name"),
                                "arguments": json.dumps(tool_call.get("arguments", {})),
                            },
                        }
                    )

                assistant_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content or None,
                }
                if tool_calls:
                    assistant_msg["tool_calls"] = tool_calls
                openai_messages.append(assistant_msg)
            # Regular messages
            else:
                openai_messages.append(msg.to_dict())

        return openai_messages

    def _parse_openai_response(
        self, response: ChatCompletion, model: str, has_tools: bool = False
    ) -> GenerationResponse:
        """Parse OpenAI response into our format."""
        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls = []

        # Check for tool calls
        if has_tools and hasattr(choice.message, "tool_calls") and choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                if hasattr(tc, "function"):
                    tool_calls.append(
                        {
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": json.loads(tc.function.arguments)
                            if tc.function.arguments
                            else {},
                        }
                    )

        # Parse usage
        usage = None
        if response.usage:
            usage = Usage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

        response_data: dict[str, Any] = {
            "content": content,
            "usage": usage,
            "model": model,
            "finish_reason": choice.finish_reason,
            "raw_response": response,
        }

        # Add tool_calls if present
        if tool_calls:
            response_data["tool_calls"] = tool_calls

        return GenerationResponse(**response_data)

    async def generate(
        self,
        messages: list[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Union[GenerationResponse, AsyncIterator[StreamEvent]]:
        """Generate text from OpenAI."""
        if not self._client:
            await self.initialize()

        model = model or self.default_model

        # Get model info for max tokens
        model_info = get_model(model)
        if max_tokens is None:
            max_tokens = model_info.max_output_tokens or 4096

        # Prepare request
        openai_messages = self._convert_messages_to_openai(messages)

        # Check if this is an O3 model that needs special handling
        is_o3_model = model in [ModelID.O3.value, ModelID.O3_PRO.value, ModelID.O4_MINI.value]

        request_params = {"model": model, "messages": openai_messages, **kwargs}

        # O3 models only support temperature=1
        if model == ModelID.O3.value:
            request_params["temperature"] = 1.0
        else:
            request_params["temperature"] = temperature

        # O3 models use max_completion_tokens instead of max_tokens
        if is_o3_model:
            request_params["max_completion_tokens"] = max_tokens
        else:
            request_params["max_tokens"] = max_tokens

        # Add tools if provided
        if tools:
            # Convert tools to OpenAI format
            openai_tools = []
            for tool in tools:
                openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool["description"],
                            "parameters": tool.get("input_schema", {}),
                        },
                    }
                )
            request_params["tools"] = openai_tools

        if stream:
            return self._stream_generate(request_params, model)
        else:
            # O3-pro requires special handling as it's not a chat model
            if model == ModelID.O3_PRO.value:
                raise NotImplementedError(
                    f"Model {model} is not a chat model and requires the completions API. "
                    "This is not yet implemented. Please use o3 or other chat models instead."
                )

            if not self._client:
                raise RuntimeError("OpenAI client not initialized")
            response = await self._client.chat.completions.create(**request_params)
            return self._parse_openai_response(response, model, tools is not None)

    async def _stream_generate(
        self, request_params: dict[str, Any], model: str
    ) -> AsyncIterator[StreamEvent]:
        """Stream generation response from OpenAI."""
        request_params["stream"] = True

        # O3-pro requires special handling as it's not a chat model
        if model == ModelID.O3_PRO.value:
            raise NotImplementedError(
                f"Model {model} is not a chat model and requires the completions API. "
                "This is not yet implemented. Please use o3 or other chat models instead."
            )

        if not self._client:
            raise RuntimeError("OpenAI client not initialized")
        stream = await self._client.chat.completions.create(**request_params)

        async for chunk in stream:
            if chunk.choices:
                choice = chunk.choices[0]
                if choice.delta.content:
                    yield StreamEvent(
                        type=StreamEventType.CONTENT,
                        content=choice.delta.content,
                        chunk=StreamChunk(content=choice.delta.content),
                    )
                if choice.finish_reason:
                    yield StreamEvent(
                        type=StreamEventType.CONTENT,
                        content="",
                        chunk=StreamChunk(finish_reason=choice.finish_reason),
                        metadata={"finish_reason": choice.finish_reason},
                    )

    async def generate_structured(
        self,
        messages: list[Message],
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
        model_info = get_model(model)
        if max_tokens is None:
            max_tokens = model_info.max_output_tokens or 4096

        # O3-pro requires special handling as it's not a chat model
        if model == ModelID.O3_PRO.value:
            raise NotImplementedError(
                f"Model {model} is not a chat model and requires the completions API. "
                "This is not yet implemented. Please use o3 or other chat models instead."
            )

        # Prepare request
        openai_messages = self._convert_messages_to_openai(messages)

        # Check if this is an O3 model that needs special handling
        is_o3_model = model in [ModelID.O3.value, ModelID.O3_PRO.value, ModelID.O4_MINI.value]

        request_params = {
            "model": model,
            "messages": openai_messages,
            "response_model": response_model,
            **kwargs,
        }

        # O3 models only support temperature=1
        if model == ModelID.O3.value:
            request_params["temperature"] = 1.0
        else:
            request_params["temperature"] = temperature

        # O3 models use max_completion_tokens instead of max_tokens
        if is_o3_model:
            request_params["max_completion_tokens"] = max_tokens
        else:
            request_params["max_tokens"] = max_tokens

        if not self._instructor_client:
            raise RuntimeError("Instructor client not initialized")
        return await self._instructor_client.chat.completions.create(**request_params)

    async def close(self) -> None:
        """Close the client."""
        if self._client:
            await self._client.close()
