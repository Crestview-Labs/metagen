"""OpenAI client with Instructor support."""

import json
from typing import Any, AsyncIterator, Optional, Union

import instructor
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion

from tools.base import Tool

from .base_provider_client import BaseProviderClient
from .models import ModelID, get_model
from .types import (
    LLMMessage,
    LLMMessageRole,
    LLMStreamChunk,
    LLMStreamEvent,
    LLMStreamEventType,
    LLMTokenUsage,
)


class OpenAIClient(BaseProviderClient):
    """OpenAI client for text generation."""

    def __init__(self, api_key: str, default_model: Optional[str] = None):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
            default_model: Default model to use (e.g., 'gpt-4o-mini')
        """
        super().__init__(api_key)
        self.default_model = default_model or "gpt-4o-mini"
        self._client: Optional[AsyncOpenAI] = None
        self._instructor_client: Optional[instructor.AsyncInstructor] = None

    async def initialize(self) -> None:
        """Initialize the OpenAI client."""
        self._client = AsyncOpenAI(api_key=self.api_key)
        # Create instructor-patched client for structured outputs
        self._instructor_client = instructor.from_openai(self._client)

    def _llm_message_to_openai_dict(
        self, msg: LLMMessage
    ) -> Union[dict[str, Any], list[dict[str, Any]]]:
        """Convert a single LLMMessage to OpenAI format.

        Returns either a single dict or a list of dicts (for tool results).
        """
        # Handle tool result messages
        if msg.role == LLMMessageRole.TOOL and msg.tool_call_results:
            # OpenAI expects tool results as separate messages for each result
            results = []
            for result in msg.tool_call_results:
                results.append(
                    {
                        "role": "tool",
                        "tool_call_id": result.tool_call_id,
                        "name": result.tool_name,
                        "content": result.content,
                    }
                )
            return results

        # Handle assistant messages with tool calls
        elif msg.role == LLMMessageRole.ASSISTANT and msg.tool_calls:
            # Format tool calls
            tool_calls = []
            for tool_call in msg.tool_calls:
                tool_calls.append(
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": tool_call.name,
                            "arguments": json.dumps(tool_call.arguments),
                        },
                    }
                )

            assistant_msg: dict[str, Any] = {"role": "assistant", "content": msg.content or None}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            return assistant_msg

        # Handle system messages
        elif msg.role == LLMMessageRole.SYSTEM:
            return {"role": "system", "content": msg.content}

        # Handle regular user/assistant messages
        else:
            return {"role": msg.role.value, "content": msg.content}

    def _convert_messages_to_openai(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """Convert our Message format to OpenAI's format."""
        openai_messages = []

        for msg in messages:
            result = self._llm_message_to_openai_dict(msg)
            if isinstance(result, list):
                openai_messages.extend(result)
            else:
                openai_messages.append(result)

        return openai_messages

    def _parse_openai_response(
        self, response: ChatCompletion, model: str, has_tools: bool = False
    ) -> LLMMessage:
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
            usage = LLMTokenUsage(
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens,
            )

        response_data: dict[str, Any] = {
            "role": LLMMessageRole.ASSISTANT,
            "content": content,
            "usage": usage,
            "model": model,
            "finish_reason": choice.finish_reason,
        }

        # Add tool_calls if present
        if tool_calls:
            response_data["tool_calls"] = tool_calls

        return LLMMessage(**response_data)

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

        # O3 models need much more tokens for reasoning
        # If max_tokens is too low, O3 will return empty content
        if is_o3_model and max_tokens < 4096:
            max_tokens = 4096  # Recommended minimum for O3 to produce output

        request_params = {"model": model, "messages": openai_messages, **kwargs}

        # O3 models only support temperature=1
        if is_o3_model:
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
            # Convert Tool objects to OpenAI format
            openai_tools = []
            for tool in tools:
                openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema,
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
    ) -> AsyncIterator[LLMStreamEvent]:
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
                    yield LLMStreamEvent(
                        type=LLMStreamEventType.CONTENT,
                        content=choice.delta.content,
                        chunk=LLMStreamChunk(content=choice.delta.content),
                    )
                if choice.finish_reason:
                    yield LLMStreamEvent(
                        type=LLMStreamEventType.CONTENT,
                        content="",
                        chunk=LLMStreamChunk(content="", finish_reason=choice.finish_reason),
                        metadata={"finish_reason": choice.finish_reason},
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
        if is_o3_model:
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

    @property
    def name(self) -> str:
        """Client name."""
        return "OpenAI"
