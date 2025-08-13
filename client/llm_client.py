"""Unified LLM Client - Single client for all LLM interactions."""

import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Optional, Union

from opentelemetry import trace

from client.anthropic_client import AnthropicClient
from client.base_provider_client import BaseProviderClient
from client.gemini_client import GeminiClient
from client.models import ModelID, ModelProvider, get_model
from client.openai_client import OpenAIClient
from client.types import LLMMessage, LLMMessageRole
from common.messages import (
    AgentMessage,
    Message,
    ToolCallMessage,
    ToolCallRequest,
    UsageMessage,
    UserMessage,
)
from common.types import ToolCall, ToolCallResult
from tools.base import Tool

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified LLM Client that abstracts provider-specific details.

    Provides:
    - generate_stream(): Streaming text generation with optional tool support
    - generate_structured(): Structured output generation using instructor

    This client is purely for LLM communication. All business logic
    (tool loops, approval flows, etc.) belongs in the Agent layer.
    """

    def __init__(self, model: ModelID = ModelID.CLAUDE_SONNET_4, api_key: Optional[str] = None):
        """
        Initialize LLM client.

        Args:
            model: Model ID enum
            api_key: API key (optional, will use environment or .env)
        """
        self.model = model
        self.api_key = api_key or self._get_api_key_for_model(model)
        self.provider = self._create_provider_client(model, self.api_key)

        self._initialized = False
        self.tracer = trace.get_tracer(__name__)

    @staticmethod
    def load_secrets_from_file(file_path: Optional[str] = None) -> dict[str, str]:
        """Load secrets from a file.

        Args:
            file_path: Path to the secrets file. Defaults to finding .env in project root.

        Returns:
            Dictionary of environment variables
        """
        secrets = {}

        if file_path is None:
            # Find project root by looking for pyproject.toml
            current_dir = Path(__file__).resolve()
            for parent in current_dir.parents:
                if (parent / "pyproject.toml").exists():
                    env_path = parent / ".env"
                    if env_path.exists():
                        file_path = str(env_path)
                        break

        if file_path and os.path.exists(file_path):
            with open(file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        secrets[key.strip()] = value.strip().strip('"').strip("'")

        return secrets

    def _get_api_key_for_model(self, model: ModelID) -> str:
        """Get API key for the given model's provider."""
        model_info = get_model(model.value)
        provider = model_info.provider

        # Try environment first
        env_key_map = {
            ModelProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
            ModelProvider.OPENAI: "OPENAI_API_KEY",
            ModelProvider.GOOGLE: "GEMINI_API_KEY",
        }

        env_key_name = env_key_map.get(provider)
        if env_key_name:
            api_key = os.getenv(env_key_name)
            if api_key:
                return api_key

        # Try loading from .env file
        secrets = self.load_secrets_from_file()
        if env_key_name and env_key_name in secrets:
            return secrets[env_key_name]

        raise ValueError(
            f"API key not found for {provider.value}. "
            f"Set {env_key_name} environment variable or add it to .env file."
        )

    def _create_provider_client(self, model: ModelID, api_key: str) -> BaseProviderClient:
        """Create provider client from ModelID."""
        model_info = get_model(model.value)
        provider = model_info.provider
        model_string = model.value

        if provider == ModelProvider.ANTHROPIC:
            return AnthropicClient(api_key=api_key, default_model=model_string)
        elif provider == ModelProvider.OPENAI:
            return OpenAIClient(api_key=api_key, default_model=model_string)
        elif provider == ModelProvider.GOOGLE:
            return GeminiClient(api_key=api_key, default_model=model_string)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def initialize(self) -> None:
        """Initialize the LLM client."""
        if self._initialized:
            return

        # Initialize the underlying provider client
        await self.provider.initialize()
        self._initialized = True

        logger.info(f"LLM client initialized with {self.provider.name}")

    async def generate_stream_with_tools(
        self,
        messages: list[Message],
        tools: list[Tool],
        tool_calls: Optional[list[ToolCall]] = None,
        tool_results: Optional[list[ToolCallResult]] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        agent_id: str = "METAGEN",
        session_id: str = "",
        **kwargs: Any,
    ) -> AsyncIterator[Message]:
        """
        Generate a streaming response that may request tool usage.

        This is the ONLY public method that agents should use.
        It handles ALL conversions between unified Message format and provider-specific formats.

        Input: list[Message] - Unified message format (only UserMessage, AgentMessage)
        Output: AsyncIterator[Message] - Yields unified messages
            (AgentMessage, ToolCallMessage, UsageMessage)

        NO StreamEvent! The LLM client is the boundary that converts
        everything to/from Message format.

        If tool_calls and tool_results are provided, formats messages
        to include the tool execution results before calling LLM.

        Args:
            messages: Conversation messages in unified Message format
            tools: List of available tools (pass empty list if no tools)
            tool_calls: Optional tool calls from previous iteration
            tool_results: Optional tool results from previous iteration
            model: Optional model override
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional LLM-specific parameters

        Yields:
            Message objects (AgentMessage, ToolCallMessage, UsageMessage)
        """
        if not self._initialized:
            await self.initialize()

        # Convert Message objects to LLMMessage format
        llm_messages = self._convert_to_llm_messages(messages)

        # Add tool results if provided
        if tool_calls and tool_results:
            llm_messages = self._format_messages_with_tool_results(
                llm_messages, tool_calls, tool_results
            )

        # Call provider with tools (non-streaming at provider level)
        response = await self.provider.generate(
            messages=llm_messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            tools=tools,
            **kwargs,
        )
        # Type narrowing - stream=False guarantees LLMMessage
        assert isinstance(response, LLMMessage)

        # Yield content if present
        if response.content:
            yield AgentMessage(agent_id=agent_id, session_id=session_id, content=response.content)

        # Yield tool calls if present
        if hasattr(response, "tool_calls") and response.tool_calls:
            # Convert to ToolCallRequest objects
            tool_call_requests = []
            for i, tool_call in enumerate(response.tool_calls):
                tool_call_requests.append(
                    ToolCallRequest(
                        tool_id=tool_call.get("id", f"call_{i}"),
                        tool_name=tool_call.get("name", ""),
                        tool_args=tool_call.get("arguments", {}),
                    )
                )

            yield ToolCallMessage(
                agent_id=agent_id, session_id=session_id, tool_calls=tool_call_requests
            )

        # Yield usage information
        if hasattr(response, "usage") and response.usage:
            yield UsageMessage(
                agent_id=agent_id,
                session_id=session_id,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                total_tokens=response.usage.total_tokens,
            )

    def _convert_to_llm_messages(self, messages: list[Message]) -> list[LLMMessage]:
        """Convert unified Message objects to LLMMessage format.

        This is the boundary where we convert from our unified format
        to the provider-specific format.

        Only handles UserMessage and AgentMessage - other message types
        like ThinkingMessage are agent-level UI messages, not LLM conversation.
        """
        llm_messages = []

        for msg in messages:
            if isinstance(msg, UserMessage):
                llm_messages.append(LLMMessage(role=LLMMessageRole.USER, content=msg.content))
            elif isinstance(msg, AgentMessage):
                llm_messages.append(LLMMessage(role=LLMMessageRole.ASSISTANT, content=msg.content))
            # Tool messages handled separately in _format_messages_with_tool_results

        return llm_messages

    def _format_messages_with_tool_results(
        self,
        messages: list[LLMMessage],
        tool_calls: list[ToolCall],
        tool_results: list[ToolCallResult],
    ) -> list[LLMMessage]:
        """
        Format messages with tool results according to provider requirements.

        Different providers expect different formats:
        - Claude: Expects assistant message with tool_calls, then tool messages
        - GPT: Similar but with different field names
        - Gemini: Has its own format

        Args:
            messages: Original conversation
            tool_calls: Tool calls from LLM
            tool_results: Execution results

        Returns:
            Formatted message list ready for the provider
        """
        # Create a mapping of tool_id to result for easy lookup
        results_by_id = {call.id: result for call, result in zip(tool_calls, tool_results)}

        # Start with original messages
        formatted_messages = messages.copy()

        # Add assistant message with tool calls
        assistant_msg = LLMMessage(
            role=LLMMessageRole.ASSISTANT,
            content="",  # Content before tool calls (if any)
            tool_calls=tool_calls,
        )
        formatted_messages.append(assistant_msg)

        # Add tool result messages
        # Group results by message (in case we want to batch them)
        tool_results_list = []
        for tool_call in tool_calls:
            result = results_by_id.get(tool_call.id)
            if result:
                tool_results_list.append(result)

        if tool_results_list:
            # Create a single TOOL message with all results
            # Content is a summary of all tool results
            content_parts = []
            for result in tool_results_list:
                if result.is_error:
                    error_msg = result.error or "Unknown error"
                    if result.error_type:
                        content_parts.append(
                            f"[{result.tool_name}] Error ({result.error_type.value}): {error_msg}"
                        )
                    else:
                        content_parts.append(f"[{result.tool_name}] Error: {error_msg}")
                else:
                    content_parts.append(f"[{result.tool_name}] Success")

            tool_msg = LLMMessage(
                role=LLMMessageRole.TOOL,
                content="\n".join(content_parts),
                tool_call_results=tool_results_list,
            )
            formatted_messages.append(tool_msg)

        return formatted_messages

    async def generate(
        self,
        messages: list[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[LLMMessage, AsyncIterator[Message]]:  # type: ignore[return]
        """
        Generate text from the LLM.

        This method exists to satisfy the BaseClient interface.
        For streaming with tools, use generate_stream_with_tools directly.

        Args:
            messages: List of messages in unified Message format
            model: Model to use (if None, uses default for provider)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            stream: Whether to stream the response
            **kwargs: Additional provider-specific parameters

        Returns:
            LLMMessage if stream=False, AsyncIterator[Message] if stream=True
        """
        if not self._initialized:
            await self.initialize()

        if stream:
            # For streaming without tools, pass empty tools list
            # For streaming with tools, callers should use generate_stream_with_tools directly
            return self.generate_stream_with_tools(
                messages=messages,
                tools=[],
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
        else:
            # For non-streaming, convert messages and use the underlying provider
            llm_messages = self._convert_to_llm_messages(messages)
            return await self.provider.generate(  # type: ignore[return-value]
                messages=llm_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
                **kwargs,
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
        """
        Generate structured output using instructor.

        This method provides reliable structured output generation
        for tools and other components that need typed responses.

        Args:
            messages: List of messages in the conversation
            response_model: Pydantic model class for the response
            model: Model to use (if None, uses default for provider)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters

        Returns:
            Instance of response_model with structured data
        """
        if not self._initialized:
            await self.initialize()

        return await self.provider.generate_structured(
            messages=messages,
            response_model=response_model,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    async def close(self) -> None:
        """Close the LLM client."""
        if self.provider:
            try:
                await self.provider.close()
            except Exception as e:
                logger.warning(f"Error closing LLM provider: {e}")

        self._initialized = False

    @property
    def name(self) -> str:
        """Client name."""
        return f"LLM-{getattr(self.provider, 'name', 'Provider')}"
