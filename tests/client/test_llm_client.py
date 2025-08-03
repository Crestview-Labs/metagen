"""Comprehensive tests for unified LLMClient with tool calling and structured outputs."""

import os
from typing import Any, Optional
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from pydantic import BaseModel, Field

from client.llm_client import LLMClient
from client.models import REASONING_MODELS, STRUCTURED_OUTPUT_MODELS, ModelID
from client.types import LLMMessage, LLMMessageRole, LLMTokenUsage
from common.messages import AgentMessage, Message, ToolCallMessage, UsageMessage, UserMessage
from common.types import ToolCall, ToolCallResult, ToolErrorType
from tools.base import Tool


# Test models for structured output
class SimpleResponse(BaseModel):
    """Simple response model for testing."""

    answer: str
    confidence: float = Field(ge=0.0, le=1.0)


class ComplexResponse(BaseModel):
    """Complex response model with nested structures."""

    title: str
    items: list[str]
    metadata: dict
    optional_field: Optional[str] = None


class ExtractedEntity(BaseModel):
    """Model for entity extraction testing."""

    name: str = Field(description="The name of the entity")
    entity_type: str = Field(
        description="The type of entity (e.g., 'landmark', 'person', 'structure')"
    )
    attributes: dict = Field(
        default_factory=dict, description="A dictionary of key attributes of the entity"
    )


class AnalysisResult(BaseModel):
    """Model for analysis results."""

    summary: str
    key_points: list[str]
    sentiment: str = Field(pattern="^(positive|negative|neutral)$")
    confidence_score: float = Field(ge=0.0, le=1.0)


@pytest.mark.unit
@pytest.mark.asyncio
class TestLLMClientUnit:
    """Unit tests for LLMClient with mocked dependencies."""

    @pytest_asyncio.fixture
    async def mock_provider(self) -> AsyncMock:
        """Create a mock LLM provider for testing."""
        mock_provider = AsyncMock()
        mock_provider.initialize = AsyncMock()
        mock_provider.generate = AsyncMock()
        mock_provider.generate_structured = AsyncMock()
        mock_provider.close = AsyncMock()
        mock_provider.name = "MockProvider"
        mock_provider.api_key = "test-api-key"
        return mock_provider

    @pytest_asyncio.fixture
    async def llm_client_factory(self, mock_provider: AsyncMock) -> Any:
        """Factory to create LLMClient instances with different models."""
        clients: list[LLMClient] = []

        async def _create_client(model_id: ModelID) -> LLMClient:
            with patch.object(LLMClient, "_create_provider_client", return_value=mock_provider):
                client = LLMClient(model=model_id)
                await client.initialize()
                clients.append(client)
                return client

        yield _create_client

        # Cleanup
        for client in clients:
            await client.close()

    # Tool calling tests - parameterized for ALL REASONING_MODELS
    @pytest.mark.parametrize("model_id", REASONING_MODELS)
    async def test_generate_stream_with_tools_basic(
        self, model_id: ModelID, llm_client_factory: Any, mock_provider: AsyncMock
    ) -> None:
        """Test basic streaming generation with tools for reasoning models."""
        llm_client = await llm_client_factory(model_id)

        # Setup mock response with tool calls
        mock_response = LLMMessage(
            role=LLMMessageRole.ASSISTANT,
            content="I'll help you with that calculation.",
            tool_calls=[
                {"id": "call_1", "name": "calculator", "arguments": {"expression": "2 + 2"}}
            ],
            usage=LLMTokenUsage(input_tokens=100, output_tokens=50, total_tokens=150),
            model=model_id.value,
            finish_reason="tool_use",
        )
        mock_provider.generate.return_value = mock_response

        # Create tools
        tools = [
            Tool(
                name="calculator",
                description="Perform calculations",
                input_schema={
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            )
        ]

        # Create messages
        messages: list[Message] = [UserMessage(content="What is 2 + 2?")]

        # Collect events
        events = []
        async for event in llm_client.generate_stream_with_tools(messages=messages, tools=tools):
            events.append(event)

        # Verify we got the right message types
        assert len(events) >= 2  # AgentMessage, ToolCallMessage, UsageMessage

        # Check agent message
        agent_messages = [e for e in events if isinstance(e, AgentMessage)]
        assert len(agent_messages) == 1
        assert agent_messages[0].content == "I'll help you with that calculation."

        # Check tool call message
        tool_messages = [e for e in events if isinstance(e, ToolCallMessage)]
        assert len(tool_messages) == 1
        assert len(tool_messages[0].tool_calls) == 1
        assert tool_messages[0].tool_calls[0].tool_name == "calculator"
        assert tool_messages[0].tool_calls[0].tool_args == {"expression": "2 + 2"}

        # Check usage message
        usage_messages = [e for e in events if isinstance(e, UsageMessage)]
        assert len(usage_messages) == 1
        assert usage_messages[0].input_tokens == 100
        assert usage_messages[0].output_tokens == 50

    @pytest.mark.parametrize("model_id", REASONING_MODELS)
    async def test_generate_stream_with_multiple_tools(
        self, model_id: ModelID, llm_client_factory: Any, mock_provider: AsyncMock
    ) -> None:
        """Test generation with multiple tool calls for reasoning models."""
        llm_client = await llm_client_factory(model_id)

        # Setup mock response with multiple tool calls
        mock_response = LLMMessage(
            role=LLMMessageRole.ASSISTANT,
            content="I'll search for that information and calculate the result.",
            tool_calls=[
                {"id": "call_1", "name": "search", "arguments": {"query": "Paris weather"}},
                {
                    "id": "call_2",
                    "name": "calculator",
                    "arguments": {"expression": "32 * 1.8 + 32"},
                },
            ],
            usage=LLMTokenUsage(input_tokens=120, output_tokens=60, total_tokens=180),
            model=model_id.value,
            finish_reason="tool_use",
        )
        mock_provider.generate.return_value = mock_response

        # Create tools
        tools = [
            Tool(
                name="search",
                description="Search for information",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            ),
            Tool(
                name="calculator",
                description="Perform calculations",
                input_schema={
                    "type": "object",
                    "properties": {"expression": {"type": "string"}},
                    "required": ["expression"],
                },
            ),
        ]

        messages = [UserMessage(content="What's the weather in Paris in Fahrenheit?")]

        # Collect events
        events = []
        async for event in llm_client.generate_stream_with_tools(messages=messages, tools=tools):
            events.append(event)

        # Check tool call message with multiple tools
        tool_messages = [e for e in events if isinstance(e, ToolCallMessage)]
        assert len(tool_messages) == 1
        assert len(tool_messages[0].tool_calls) == 2
        assert tool_messages[0].tool_calls[0].tool_name == "search"
        assert tool_messages[0].tool_calls[0].tool_args == {"query": "Paris weather"}
        assert tool_messages[0].tool_calls[1].tool_name == "calculator"
        assert tool_messages[0].tool_calls[1].tool_args == {"expression": "32 * 1.8 + 32"}

    @pytest.mark.parametrize("model_id", REASONING_MODELS)
    async def test_generate_stream_with_tool_results(
        self, model_id: ModelID, llm_client_factory: Any, mock_provider: AsyncMock
    ) -> None:
        """Test continuing generation after tool execution for reasoning models."""
        llm_client = await llm_client_factory(model_id)

        # Setup mock response
        mock_response = LLMMessage(
            role=LLMMessageRole.ASSISTANT,
            content="The result is 4.",
            usage=LLMTokenUsage(input_tokens=150, output_tokens=20, total_tokens=170),
            model=model_id.value,
            finish_reason="stop",
        )
        mock_provider.generate.return_value = mock_response

        # Create initial messages
        messages: list[Message] = [UserMessage(content="What is 2 + 2?")]

        # Create tool calls and results
        tool_calls = [ToolCall(id="call_1", name="calculator", arguments={"expression": "2 + 2"})]

        tool_results = [
            ToolCallResult(
                tool_name="calculator",
                tool_call_id="call_1",
                content="4",
                is_error=False,
                error=None,
                error_type=None,
                user_display=None,
            )
        ]

        # Empty tools list (no more tools needed)
        tools: list[Tool] = []

        # Collect events
        events = []
        async for event in llm_client.generate_stream_with_tools(
            messages=messages, tools=tools, tool_calls=tool_calls, tool_results=tool_results
        ):
            events.append(event)

        # Verify formatted messages were created correctly
        call_args = mock_provider.generate.call_args
        formatted_messages = call_args[1]["messages"]

        # Should have original message + assistant with tool calls + tool results
        assert len(formatted_messages) == 3
        assert formatted_messages[0].role == LLMMessageRole.USER
        assert formatted_messages[1].role == LLMMessageRole.ASSISTANT
        assert formatted_messages[1].tool_calls == tool_calls
        assert formatted_messages[2].role == LLMMessageRole.TOOL
        assert formatted_messages[2].tool_call_results == tool_results

        # Verify events
        agent_messages = [e for e in events if isinstance(e, AgentMessage)]
        assert len(agent_messages) == 1
        assert agent_messages[0].content == "The result is 4."

    @pytest.mark.parametrize("model_id", REASONING_MODELS)
    async def test_tool_error_handling(
        self, model_id: ModelID, llm_client_factory: Any, mock_provider: AsyncMock
    ) -> None:
        """Test handling of tool execution errors for reasoning models."""
        llm_client = await llm_client_factory(model_id)

        # Setup initial response with tool call
        initial_response = LLMMessage(
            role=LLMMessageRole.ASSISTANT,
            content="Let me calculate that.",
            tool_calls=[{"id": "call_1", "name": "calculator", "arguments": {"expr": "1/0"}}],
            usage=LLMTokenUsage(input_tokens=50, output_tokens=20, total_tokens=70),
            model=model_id.value,
            finish_reason="tool_use",
        )

        # Setup response after error
        error_response = LLMMessage(
            role=LLMMessageRole.ASSISTANT,
            content="I encountered an error: division by zero.",
            usage=LLMTokenUsage(input_tokens=100, output_tokens=30, total_tokens=130),
            model=model_id.value,
            finish_reason="stop",
        )

        mock_provider.generate.side_effect = [initial_response, error_response]

        # Create messages and tool with error result
        messages = [UserMessage(content="Calculate 1/0")]
        tools = [
            Tool(
                name="calculator",
                description="Perform calculations",
                input_schema={"type": "object", "properties": {"expr": {"type": "string"}}},
            )
        ]

        # First call - get tool request
        events = []
        async for event in llm_client.generate_stream_with_tools(messages, tools):
            events.append(event)

        assert any(isinstance(e, ToolCallMessage) for e in events)

        # Simulate tool error
        tool_calls = [ToolCall(id="call_1", name="calculator", arguments={"expr": "1/0"})]
        tool_results = [
            ToolCallResult(
                tool_name="calculator",
                tool_call_id="call_1",
                content="Division by zero error",
                is_error=True,
                error="ZeroDivisionError",
                error_type=ToolErrorType.EXECUTION_ERROR,
                user_display=None,
            )
        ]

        # Continue with error result
        events = []
        async for event in llm_client.generate_stream_with_tools(
            messages, tools, tool_calls, tool_results
        ):
            events.append(event)

        # Verify error was handled
        agent_messages = [e for e in events if isinstance(e, AgentMessage)]
        assert len(agent_messages) == 1
        assert "error" in agent_messages[0].content.lower()

    # Structured output tests - parameterized for ALL STRUCTURED_OUTPUT_MODELS
    @pytest.mark.parametrize("model_id", STRUCTURED_OUTPUT_MODELS)
    async def test_generate_structured_simple(
        self, model_id: ModelID, llm_client_factory: Any, mock_provider: AsyncMock
    ) -> None:
        """Test basic structured generation for structured output models."""
        llm_client = await llm_client_factory(model_id)

        # Mock structured response
        mock_response = SimpleResponse(answer="Paris", confidence=0.95)
        mock_provider.generate_structured.return_value = mock_response

        messages = [LLMMessage(role=LLMMessageRole.USER, content="What is the capital of France?")]

        result = await llm_client.generate_structured(
            messages=messages, response_model=SimpleResponse
        )

        assert isinstance(result, SimpleResponse)
        assert result.answer == "Paris"
        assert result.confidence == 0.95
        assert mock_provider.generate_structured.called

    @pytest.mark.parametrize("model_id", STRUCTURED_OUTPUT_MODELS)
    async def test_generate_structured_complex(
        self, model_id: ModelID, llm_client_factory: Any, mock_provider: AsyncMock
    ) -> None:
        """Test complex structured generation with nested fields for structured output models."""
        llm_client = await llm_client_factory(model_id)

        # Mock complex response
        mock_response = ComplexResponse(
            title="Task List",
            items=["Complete project", "Review code", "Deploy"],
            metadata={"priority": "high", "deadline": "2024-01-15"},
            optional_field="Additional notes",
        )
        mock_provider.generate_structured.return_value = mock_response

        messages = [
            LLMMessage(role=LLMMessageRole.USER, content="Create a task list for the project")
        ]

        result = await llm_client.generate_structured(
            messages=messages, response_model=ComplexResponse, temperature=0.5
        )

        assert isinstance(result, ComplexResponse)
        assert result.title == "Task List"
        assert len(result.items) == 3
        assert result.metadata["priority"] == "high"
        assert result.optional_field == "Additional notes"

    @pytest.mark.parametrize("model_id", STRUCTURED_OUTPUT_MODELS)
    async def test_generate_structured_entity_extraction(
        self, model_id: ModelID, llm_client_factory: Any, mock_provider: AsyncMock
    ) -> None:
        """Test entity extraction using structured output for structured output models."""
        llm_client = await llm_client_factory(model_id)

        # Mock entity extraction response
        mock_response = ExtractedEntity(
            name="Eiffel Tower",
            entity_type="landmark",
            attributes={"location": "Paris, France", "height": "330 meters", "built": "1889"},
        )
        mock_provider.generate_structured.return_value = mock_response

        messages = [
            LLMMessage(
                role=LLMMessageRole.USER,
                content="Extract information about the Eiffel Tower from this text...",
            )
        ]

        result = await llm_client.generate_structured(
            messages=messages, response_model=ExtractedEntity
        )

        assert isinstance(result, ExtractedEntity)
        assert result.name == "Eiffel Tower"
        assert result.entity_type == "landmark"
        assert result.attributes["location"] == "Paris, France"

    @pytest.mark.parametrize("model_id", STRUCTURED_OUTPUT_MODELS)
    async def test_generate_structured_analysis(
        self, model_id: ModelID, llm_client_factory: Any, mock_provider: AsyncMock
    ) -> None:
        """Test analysis result with validation for structured output models."""
        llm_client = await llm_client_factory(model_id)

        # Mock analysis response
        mock_response = AnalysisResult(
            summary="Positive review of the product",
            key_points=["High quality", "Good value", "Fast shipping"],
            sentiment="positive",
            confidence_score=0.85,
        )
        mock_provider.generate_structured.return_value = mock_response

        messages = [LLMMessage(role=LLMMessageRole.USER, content="Analyze this customer review...")]

        result = await llm_client.generate_structured(
            messages=messages, response_model=AnalysisResult
        )

        assert isinstance(result, AnalysisResult)
        assert result.sentiment == "positive"
        assert result.confidence_score == 0.85
        assert len(result.key_points) == 3

    # General tests for select models from both categories
    @pytest.mark.parametrize("model_id", [REASONING_MODELS[0], STRUCTURED_OUTPUT_MODELS[0]])
    async def test_generate_non_streaming(
        self, model_id: ModelID, llm_client_factory: Any, mock_provider: AsyncMock
    ) -> None:
        """Test non-streaming generation for both model types."""
        llm_client = await llm_client_factory(model_id)

        # Setup mock response
        mock_response = LLMMessage(
            role=LLMMessageRole.ASSISTANT,
            content="Hello! How can I help you?",
            usage=LLMTokenUsage(input_tokens=10, output_tokens=8, total_tokens=18),
            model=model_id.value,
            finish_reason="stop",
        )
        mock_provider.generate.return_value = mock_response

        messages = [LLMMessage(role=LLMMessageRole.USER, content="Hello")]

        # Call generate with stream=False
        response = await llm_client.generate(messages=messages, stream=False)

        # Verify response
        assert isinstance(response, LLMMessage)
        assert response.content == "Hello! How can I help you?"
        assert mock_provider.generate.called
        assert mock_provider.generate.call_args[1]["stream"] is False

    @pytest.mark.parametrize("model_id", [REASONING_MODELS[0], STRUCTURED_OUTPUT_MODELS[0]])
    async def test_temperature_and_params(
        self, model_id: ModelID, llm_client_factory: Any, mock_provider: AsyncMock
    ) -> None:
        """Test temperature and other parameters are passed correctly."""
        llm_client = await llm_client_factory(model_id)

        mock_response = LLMMessage(
            role=LLMMessageRole.ASSISTANT,
            content="Response",
            usage=LLMTokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            model=model_id.value,
            finish_reason="stop",
        )
        mock_provider.generate.return_value = mock_response

        messages = [LLMMessage(role=LLMMessageRole.USER, content="Test")]

        # Test with custom parameters
        await llm_client.generate(
            messages=messages, temperature=0.3, max_tokens=100, stream=False, custom_param="value"
        )

        # Verify parameters were passed
        call_args = mock_provider.generate.call_args[1]
        assert call_args["temperature"] == 0.3
        assert call_args["max_tokens"] == 100
        assert call_args["custom_param"] == "value"

    @pytest.mark.parametrize("model_id", [REASONING_MODELS[0], STRUCTURED_OUTPUT_MODELS[0]])
    async def test_model_override(
        self, model_id: ModelID, llm_client_factory: Any, mock_provider: AsyncMock
    ) -> None:
        """Test model override functionality."""
        llm_client = await llm_client_factory(model_id)

        mock_response = LLMMessage(
            role=LLMMessageRole.ASSISTANT,
            content="Response",
            usage=LLMTokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            model="gpt-4",
            finish_reason="stop",
        )
        mock_provider.generate.return_value = mock_response

        messages = [LLMMessage(role=LLMMessageRole.USER, content="Test")]

        # Override model
        await llm_client.generate(messages=messages, model="gpt-4", stream=False)

        # Verify model was passed
        call_args = mock_provider.generate.call_args[1]
        assert call_args["model"] == "gpt-4"

    @pytest.mark.parametrize("model_id", [REASONING_MODELS[0], STRUCTURED_OUTPUT_MODELS[0]])
    async def test_error_propagation(
        self, model_id: ModelID, llm_client_factory: Any, mock_provider: AsyncMock
    ) -> None:
        """Test that errors are properly propagated."""
        llm_client = await llm_client_factory(model_id)

        # Setup mock to raise an exception
        mock_provider.generate.side_effect = Exception("API Error")

        messages = [LLMMessage(role=LLMMessageRole.USER, content="Test error")]

        # Verify exception is propagated
        with pytest.raises(Exception) as exc_info:
            await llm_client.generate(messages=messages, stream=False)

        assert "API Error" in str(exc_info.value)

        # Test with streaming
        with pytest.raises(Exception) as exc_info:
            async for _ in llm_client.generate_stream_with_tools(messages=messages, tools=[]):
                pass

        assert "API Error" in str(exc_info.value)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY"),
    reason="No API keys found for integration tests",
)
class TestLLMClientIntegration:
    """Integration tests with real LLM providers."""

    @pytest.mark.parametrize("model_id", REASONING_MODELS)
    async def test_real_tool_calling(self, model_id: ModelID) -> None:
        """Test tool calling with real LLM providers."""
        # Skip specific models that might not be available
        if model_id == ModelID.O3_PRO:
            pytest.skip("O3_PRO requires special access")

        client = LLMClient(model=model_id)
        await client.initialize()

        try:
            # Create a simple tool
            tools = [
                Tool(
                    name="get_current_time",
                    description="Get the current time",
                    input_schema={"type": "object", "properties": {}, "required": []},
                )
            ]

            messages: list[Message] = [UserMessage(content="What time is it?")]

            # Collect events
            events = []
            async for event in client.generate_stream_with_tools(
                messages=messages, tools=tools, temperature=0.5
            ):
                events.append(event)

            # Should have at least content or tool execution request
            assert len(events) > 0

            # Check for tool execution request (now using ToolCallMessage)
            tool_call_messages = [e for e in events if isinstance(e, ToolCallMessage)]
            if tool_call_messages:
                # We should get exactly one ToolCallMessage with all tools
                assert len(tool_call_messages) == 1
                tool_calls = tool_call_messages[0].tool_calls
                assert len(tool_calls) > 0
                # Check that get_current_time is one of the requested tools
                tool_names = [call.tool_name for call in tool_calls]
                assert "get_current_time" in tool_names

        finally:
            await client.close()

    @pytest.mark.parametrize("model_id", STRUCTURED_OUTPUT_MODELS)
    async def test_real_structured_output(self, model_id: ModelID) -> None:
        """Test structured output with real LLM providers."""
        client = LLMClient(model=model_id)
        await client.initialize()

        try:
            messages = [
                LLMMessage(
                    role=LLMMessageRole.USER,
                    content="Extract: The Eiffel Tower is 330 meters tall and located in Paris.",
                )
            ]

            result = await client.generate_structured(
                messages=messages, response_model=ExtractedEntity, temperature=0.3
            )

            assert isinstance(result, ExtractedEntity)
            assert "eiffel" in result.name.lower() or "tower" in result.name.lower()
            assert result.entity_type.lower() in [
                "landmark",
                "structure",
                "building",
                "monument",
                "tower",
            ]
            # Attributes extraction is optional - models may or may not populate it

        finally:
            await client.close()

    async def test_real_multi_turn_conversation(self) -> None:
        """Test multi-turn conversation with tool results."""
        client = LLMClient(model=ModelID.CLAUDE_SONNET_4)
        await client.initialize()

        try:
            # Initial message
            messages: list[Message] = [UserMessage(content="I need to calculate 15% of 85.")]

            tools = [
                Tool(
                    name="calculator",
                    description="Perform mathematical calculations",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "expression": {
                                "type": "string",
                                "description": "Mathematical expression to evaluate",
                            }
                        },
                        "required": ["expression"],
                    },
                )
            ]

            # First turn - should request calculator tool
            tool_calls_made = []
            async for event in client.generate_stream_with_tools(messages, tools):
                if isinstance(event, ToolCallMessage):
                    # Handle tool calls from ToolCallMessage
                    for tool_call in event.tool_calls:
                        tool_calls_made.append(
                            ToolCall(
                                id=tool_call.tool_id,
                                name=tool_call.tool_name,
                                arguments=tool_call.tool_args,
                            )
                        )

            assert len(tool_calls_made) > 0
            assert tool_calls_made[0].name == "calculator"

            # Simulate tool execution
            tool_results = [
                ToolCallResult(
                    tool_name="calculator",
                    tool_call_id=tool_calls_made[0].id,
                    content="12.75",
                    is_error=False,
                    error=None,
                    error_type=None,
                    user_display=None,
                )
            ]

            # Second turn - continue with tool results
            final_content = ""
            async for event in client.generate_stream_with_tools(
                messages, tools, tool_calls_made, tool_results
            ):
                if isinstance(event, AgentMessage):
                    final_content += event.content

            # Should have the answer
            assert "12.75" in final_content or "12.8" in final_content

        finally:
            await client.close()
