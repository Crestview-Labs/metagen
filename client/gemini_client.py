"""Gemini client implementation using the new Google GenAI SDK."""

import logging
from typing import Any, AsyncIterator, Optional, Union

import instructor
from google import genai
from google.genai import types
from google.genai.types import HttpOptions

from client.base_provider_client import BaseProviderClient
from client.types import LLMMessage, LLMMessageRole, LLMStreamEvent, LLMTokenUsage
from tools.base import Tool

logger = logging.getLogger(__name__)


class GeminiClient(BaseProviderClient):
    """Gemini client implementation supporting 2.5 Flash and Pro models."""

    def __init__(self, api_key: str, default_model: Optional[str] = None):
        """Initialize Gemini client.

        Args:
            api_key: Gemini API key
            default_model: Default model to use (e.g., 'gemini-2.5-flash' or 'gemini-2.5-pro')
        """
        super().__init__(api_key)
        self.model_name = default_model or "gemini-2.5-flash"
        self.client: Optional[genai.Client] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the Gemini client."""
        if self._initialized:
            return

        try:
            # Create the client with API key
            # Use v1beta for tools/function calling support
            self.client = genai.Client(
                api_key=self.api_key, http_options=HttpOptions(api_version="v1beta")
            )

            # Initialize instructor client for structured outputs
            self._instructor_client = instructor.from_genai(self.client)

            self._initialized = True
            logger.info(f"Initialized Gemini client with model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise

    def _convert_messages_to_gemini_format(
        self, messages: list[LLMMessage]
    ) -> list[dict[str, Any]]:
        """Convert our LLMMessage format to Gemini's expected format."""
        gemini_contents = []

        for msg in messages:
            if msg.role == LLMMessageRole.TOOL and msg.tool_call_results:
                # Handle tool result messages for Gemini
                for result in msg.tool_call_results:
                    # Gemini expects function responses in a specific format
                    gemini_contents.append(
                        {
                            "role": "function",
                            "parts": [
                                {
                                    "functionResponse": {
                                        "name": result.tool_name,
                                        "response": {
                                            "result": result.content,
                                            "error": result.content if result.is_error else None,
                                        },
                                    }
                                }
                            ],
                        }
                    )
            elif msg.role == LLMMessageRole.ASSISTANT and msg.tool_calls:
                # Handle assistant messages with tool calls
                parts = []
                if msg.content:
                    parts.append({"text": msg.content})
                for tool_call in msg.tool_calls:
                    function_call_part: dict[str, Any] = {
                        "functionCall": {"name": tool_call.name, "args": tool_call.arguments}
                    }
                    parts.append(function_call_part)
                gemini_contents.append({"role": "model", "parts": parts})
            elif msg.role == LLMMessageRole.USER:
                gemini_contents.append({"role": "user", "parts": [{"text": msg.content}]})
            elif msg.role == LLMMessageRole.ASSISTANT:
                gemini_contents.append({"role": "model", "parts": [{"text": msg.content}]})
            elif msg.role == LLMMessageRole.SYSTEM:
                # Gemini handles system instructions differently
                # For now, prepend to first user message
                if gemini_contents and gemini_contents[0]["role"] == "user":
                    parts_list = gemini_contents[0]["parts"]
                    if isinstance(parts_list, list):
                        parts_list.insert(0, {"text": f"System: {msg.content}\n\n"})
                else:
                    gemini_contents.append(
                        {"role": "user", "parts": [{"text": f"System: {msg.content}"}]}
                    )

        return gemini_contents

    def _convert_tools_to_gemini_format(self, tools: list[Tool]) -> list[Any]:
        """Convert tool definitions to Gemini's format.

        Returns a list of Tool objects containing function declarations.
        """
        if not tools:
            return []

        function_declarations = []
        for tool in tools:
            # Create FunctionDeclaration for each Tool object
            func_decl = types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters_json_schema=tool.input_schema,
            )
            function_declarations.append(func_decl)

        # Wrap function declarations in a Tool object
        return [types.Tool(function_declarations=function_declarations)]

    def _extract_tool_calls_from_response(self, response: Any) -> list[dict[str, Any]]:
        """Extract tool calls from Gemini response."""
        tool_calls = []

        if hasattr(response, "candidates"):
            for candidate in response.candidates:
                if hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                    for i, part in enumerate(candidate.content.parts):
                        # Check if part has function_call attribute and it's not None
                        if hasattr(part, "function_call") and part.function_call is not None:
                            # Extract the function call details
                            func_call = part.function_call
                            tool_calls.append(
                                {
                                    # Generate ID since Gemini doesn't provide one
                                    "id": f"call_{i}",
                                    "name": (
                                        func_call.name
                                        if hasattr(func_call, "name")
                                        else func_call.get("name")
                                    ),
                                    "arguments": (
                                        dict(func_call.args)
                                        if hasattr(func_call, "args")
                                        else func_call.get("args", {})
                                    ),
                                }
                            )

        return tool_calls

    def _calculate_usage(self, response: Any) -> Optional[LLMTokenUsage]:
        """Extract token usage from Gemini response."""
        if hasattr(response, "usage_metadata"):
            metadata = response.usage_metadata
            return LLMTokenUsage(
                input_tokens=getattr(metadata, "prompt_token_count", 0),
                output_tokens=getattr(metadata, "candidates_token_count", 0),
                total_tokens=getattr(metadata, "total_token_count", 0),
            )
        return None

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
        """Generate text using Gemini."""
        if not self._initialized:
            await self.initialize()

        # Use provided model or default
        model_to_use = model or self.model_name

        # Convert messages to Gemini format
        gemini_contents = self._convert_messages_to_gemini_format(messages)

        # Convert tools if provided
        gemini_tools = self._convert_tools_to_gemini_format(tools) if tools else None

        try:
            if stream:
                # Streaming not implemented yet
                raise NotImplementedError("Streaming not yet implemented for Gemini client")
            else:
                # Create the config object with tools if provided
                if gemini_tools:
                    config = types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens if max_tokens else None,
                        tools=gemini_tools,
                    )
                else:
                    config = types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens if max_tokens else None,
                    )

                # Use the new SDK's generate_content method
                if not self.client:
                    raise RuntimeError("Client not initialized")
                response = await self.client.aio.models.generate_content(
                    model=model_to_use, contents=gemini_contents, config=config
                )

                # Extract content
                # When tools are used, the response might not have text
                content = ""
                if hasattr(response, "text") and response.text:
                    content = response.text
                elif hasattr(response, "candidates") and response.candidates:
                    # Try to extract text from candidates
                    for candidate in response.candidates:
                        if (
                            hasattr(candidate, "content")
                            and candidate.content
                            and hasattr(candidate.content, "parts")
                        ):
                            if candidate.content.parts:  # type: ignore[attr-defined]
                                for part in candidate.content.parts:  # type: ignore[attr-defined]
                                    if hasattr(part, "text") and part.text:
                                        content += part.text

                # Extract tool calls if any
                tool_calls = self._extract_tool_calls_from_response(response)

                # Calculate usage
                usage = self._calculate_usage(response)

                # Get finish reason
                finish_reason = "stop"
                if hasattr(response, "candidates") and response.candidates:
                    candidate = response.candidates[0]
                    if hasattr(candidate, "finish_reason"):
                        finish_reason = str(candidate.finish_reason)

                # Log if we have an unexpected tool call issue
                if "UNEXPECTED_TOOL_CALL" in finish_reason:
                    logger.warning(f"Gemini returned UNEXPECTED_TOOL_CALL. Response: {response}")

                return LLMMessage(
                    role=LLMMessageRole.ASSISTANT,
                    content=content,
                    usage=usage,
                    model=model_to_use,
                    finish_reason=finish_reason,
                    tool_calls=tool_calls if tool_calls else None,
                )

        except Exception as e:
            logger.error(f"Gemini generation failed: {e}")
            raise

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
        if not self._initialized:
            await self.initialize()

        # Use provided model or default
        model_to_use = model or self.model_name

        # Convert messages to dict format for instructor
        dict_messages = []
        for msg in messages:
            if msg.role == LLMMessageRole.USER:
                dict_messages.append({"role": "user", "content": msg.content})
            elif msg.role == LLMMessageRole.ASSISTANT:
                dict_messages.append({"role": "assistant", "content": msg.content})
            elif msg.role == LLMMessageRole.SYSTEM:
                # Gemini handles system messages differently - prepend to first user message
                if dict_messages and dict_messages[0]["role"] == "user":
                    dict_messages[0]["content"] = (
                        f"System: {msg.content}\n\n{dict_messages[0]['content']}"
                    )
                else:
                    dict_messages.append({"role": "user", "content": f"System: {msg.content}"})

        # Build request parameters
        request_params = {
            "model": model_to_use,
            "messages": dict_messages,
            "response_model": response_model,
        }

        # Add generation config for temperature and max_tokens
        generation_config = {}
        if temperature != 0.7:  # Only add if not default
            generation_config["temperature"] = temperature
        if max_tokens is not None:
            generation_config["max_output_tokens"] = max_tokens

        if generation_config:
            request_params["generation_config"] = generation_config

        try:
            # Use instructor client chat.completions API
            response = await self._instructor_client.chat.completions.create(**request_params)
            return response
        except Exception as e:
            logger.error(f"Gemini structured generation failed: {e}")
            raise

    async def close(self) -> None:
        """Close the client - no cleanup needed for Gemini."""
        self._initialized = False

    @property
    def name(self) -> str:
        """Client name."""
        return f"Gemini-{self.model_name}"
