"""Comprehensive tests for AgenticClient with tool calling capabilities."""

import os
from typing import Any, AsyncGenerator, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from client.agentic_client import AgenticClient
from client.base_client import (
    GenerationResponse,
    Message,
    Role,
    StreamEvent,
    StreamEventType,
    ToolErrorType,
)
from client.models import REASONING_MODELS, ModelID, get_reasoning_model
from tools.base import ToolResult as ToolExecutionResult


@pytest.mark.unit
@pytest.mark.asyncio
class TestAgenticClientUnit:
    """Unit tests for AgenticClient with mocked dependencies."""

    @pytest_asyncio.fixture
    async def mock_llm_client(self) -> AsyncMock:
        """Create a mock LLM client for testing."""
        mock_client = AsyncMock()
        mock_client.initialize = AsyncMock()
        mock_client.generate = AsyncMock()
        mock_client.close = AsyncMock()
        return mock_client

    @pytest_asyncio.fixture
    async def mock_tool_registry(self) -> Mock:
        """Create a mock tool registry."""
        registry = Mock()
        registry.get_all_tools = Mock(
            return_value=[
                {
                    "name": "test_tool",
                    "description": "A test tool",
                    "input_schema": {
                        "type": "object",
                        "properties": {"message": {"type": "string"}},
                    },
                }
            ]
        )
        registry.set_disabled_tools = Mock()
        registry.discover_and_register_tools = AsyncMock()
        return registry

    @pytest_asyncio.fixture
    async def mock_tool_executor(self) -> Mock:
        """Create a mock tool executor."""
        executor = Mock()
        executor.execute = AsyncMock(
            return_value=ToolExecutionResult(
                success=True,
                llm_content="Tool executed successfully",
                user_display="Tool executed successfully",
                error=None,
            )
        )
        executor.core_tools = {}
        return executor

    @pytest_asyncio.fixture
    async def agentic_client(
        self, mock_llm_client: AsyncMock, mock_tool_registry: Mock, mock_tool_executor: Mock
    ) -> AsyncGenerator[AgenticClient, None]:
        """Create AgenticClient with mocked dependencies."""
        with patch("client.agentic_client.get_tool_registry", return_value=mock_tool_registry):
            with patch("client.agentic_client.get_tool_executor", return_value=mock_tool_executor):
                # Mock the _create_llm_client method to return our mock
                with patch.object(
                    AgenticClient, "_create_llm_client", return_value=mock_llm_client
                ):
                    # Use ModelID enum - default to first reasoning model
                    model = REASONING_MODELS[0]
                    client = AgenticClient(llm=model)
                    client.tool_registry = mock_tool_registry
                    client.tool_executor = mock_tool_executor
                    await client.initialize()
                    yield client

    async def test_tool_calling_integration(
        self, agentic_client: AgenticClient, mock_llm_client: AsyncMock
    ) -> None:
        """Test tool schema validation and execution."""
        # Setup mock response with tool call
        mock_response = GenerationResponse(
            content="I'll help you with that.",
            tool_calls=[{"id": "call_1", "name": "test_tool", "arguments": {"message": "Hello"}}],
        )

        # First call returns tool request, second call returns final response
        mock_llm_client.generate.side_effect = [
            mock_response,
            GenerationResponse(content="Task completed successfully."),
        ]

        messages = [Message(role=Role.USER, content="Please use the test tool")]

        response = await agentic_client.generate(messages)

        # Type narrowing - we know it's GenerationResponse when stream=False
        assert isinstance(response, GenerationResponse)
        assert response.content == "Task completed successfully."
        assert mock_llm_client.generate.call_count == 2
        # Type assertion - we know tool_executor.execute is an AsyncMock in tests
        assert hasattr(agentic_client.tool_executor.execute, "called")
        assert agentic_client.tool_executor.execute.called  # type: ignore[attr-defined]

    async def test_streaming_functionality(
        self, agentic_client: AgenticClient, mock_llm_client: AsyncMock
    ) -> None:
        """Test real-time streaming with tool calls."""
        # When stream=True is passed to generate(), AgenticClient:
        # 1. First calls llm_provider.generate(stream=True)
        # 2. Returns immediately to _handle_streaming_with_tools
        # 3. _handle_streaming_with_tools makes a NEW call with stream=False

        # Mock the initial streaming response (just returns immediately)
        async def mock_initial_stream() -> AsyncGenerator[StreamEvent, None]:
            # This doesn't get used, AgenticClient goes to _handle_streaming_with_tools
            yield StreamEvent(type=StreamEventType.CONTENT, content="ignored")

        # Mock responses for the actual implementation
        mock_response_with_tools = GenerationResponse(
            content="",
            tool_calls=[{"id": "call_1", "name": "test_tool", "arguments": {"message": "Hello"}}],
        )

        mock_final_response = GenerationResponse(content="Done!")

        # Track calls
        call_count = 0

        async def mock_generate(**kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if kwargs.get("stream", False):
                # First call with stream=True, return a dummy stream
                return mock_initial_stream()
            else:
                # Subsequent calls with stream=False from _handle_streaming_with_tools
                if call_count == 2:
                    # Second call: return tool calls
                    return mock_response_with_tools
                else:
                    # Third call: after tool execution, return final response
                    return mock_final_response

        mock_llm_client.generate = mock_generate

        messages = [Message(role=Role.USER, content="Stream test")]

        events = []
        stream_response = await agentic_client.generate(messages, stream=True)
        # Type narrowing - we know it's AsyncIterator when stream=True
        assert not isinstance(stream_response, GenerationResponse)
        async for event in stream_response:
            events.append(event)

        # Should have: tool_call event, tool_result event, and final content
        assert len(events) >= 2  # At least tool call and result

        # Find the different event types
        tool_call_events = [e for e in events if e.type == StreamEventType.TOOL_CALL]
        tool_result_events = [e for e in events if e.type == StreamEventType.TOOL_RESULT]
        content_events = [e for e in events if e.type == StreamEventType.CONTENT]

        assert len(tool_call_events) == 1
        assert len(tool_result_events) == 1
        assert len(content_events) >= 1

    async def test_agentic_loop_protection(
        self, agentic_client: AgenticClient, mock_llm_client: AsyncMock
    ) -> None:
        """Test iteration limits and token budgets."""
        # Setup response that always requests tools
        from client.base_client import Usage

        tool_response = GenerationResponse(
            content="",
            tool_calls=[{"id": "call_1", "name": "test_tool", "arguments": {"message": "Loop"}}],
            usage=Usage(input_tokens=50, output_tokens=50, total_tokens=100),
        )

        # Track how many times the LLM is called
        call_count = 0

        async def mock_generate(**kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1

            # Check if this is being called with tool result messages
            messages = kwargs.get("messages", [])

            # Look for tool result messages that indicate repeated calls
            tool_result_messages = [
                m for m in messages if hasattr(m, "tool_results") and m.tool_results
            ]

            # After seeing enough tool results with errors, return final response
            if tool_result_messages:
                # Check if we have loop detected errors
                for msg in tool_result_messages:
                    for result in msg.tool_results:
                        if result.is_error and result.error_type == ToolErrorType.LOOP_DETECTED:
                            # Stop requesting tools after loop is detected
                            return GenerationResponse(content="I've detected a loop and will stop.")

            # Otherwise keep requesting tools
            return tool_response

        mock_llm_client.generate = mock_generate

        messages = [Message(role=Role.USER, content="Test loop protection")]

        response = await agentic_client.generate(messages)

        # Type narrowing - we know it's GenerationResponse when stream=False
        assert isinstance(response, GenerationResponse)

        # The loop detection should kick in after max_repeated_calls (5)
        # LLM calls: 1 initial + 5 successful tool calls + 1 after error = 7
        assert call_count <= 10  # Allow some buffer
        assert response.content  # Should have final response
        assert "loop" in response.content.lower() or "stop" in response.content.lower()

    async def test_tool_error_handling(
        self, agentic_client: AgenticClient, mock_llm_client: AsyncMock, mock_tool_executor: Mock
    ) -> None:
        """Test tool execution error handling and propagation."""
        # Setup tool to fail
        mock_tool_executor.execute.side_effect = Exception("Tool execution failed")

        mock_response = GenerationResponse(
            content="",
            tool_calls=[{"id": "call_1", "name": "test_tool", "arguments": {"message": "Fail"}}],
        )

        mock_llm_client.generate.side_effect = [
            mock_response,
            GenerationResponse(content="I encountered an error with the tool."),
        ]

        messages = [Message(role=Role.USER, content="Test error handling")]

        response = await agentic_client.generate(messages)

        # Type narrowing - we know it's GenerationResponse when stream=False
        assert isinstance(response, GenerationResponse)

        # Should handle error gracefully
        assert "error" in response.content.lower()
        assert mock_llm_client.generate.call_count == 2

        # Check that error was passed to LLM
        second_call_messages = mock_llm_client.generate.call_args_list[1][1]["messages"]
        assert any(
            isinstance(msg.tool_results, list)
            for msg in second_call_messages
            if hasattr(msg, "tool_results")
        )

    async def test_multi_tool_execution(
        self, agentic_client: AgenticClient, mock_llm_client: AsyncMock
    ) -> None:
        """Test multiple tool calls in sequence."""
        # First response requests multiple tools
        multi_tool_response = GenerationResponse(
            content="I'll check multiple things.",
            tool_calls=[
                {"id": "call_1", "name": "test_tool", "arguments": {"message": "First"}},
                {"id": "call_2", "name": "test_tool", "arguments": {"message": "Second"}},
                {"id": "call_3", "name": "test_tool", "arguments": {"message": "Third"}},
            ],
        )

        mock_llm_client.generate.side_effect = [
            multi_tool_response,
            GenerationResponse(content="All tools executed successfully."),
        ]

        messages = [Message(role=Role.USER, content="Use multiple tools")]

        response = await agentic_client.generate(messages)

        # Type narrowing - we know it's GenerationResponse when not streaming
        assert isinstance(response, GenerationResponse)
        assert response.content == "All tools executed successfully."
        assert hasattr(agentic_client.tool_executor.execute, "call_count")
        assert agentic_client.tool_executor.execute.call_count == 3  # type: ignore[attr-defined]

    async def test_tool_result_formatting(
        self, agentic_client: AgenticClient, mock_llm_client: AsyncMock
    ) -> None:
        """Test proper tool result formatting for LLM."""
        mock_response = GenerationResponse(
            content="",
            tool_calls=[
                {"id": "call_123", "name": "test_tool", "arguments": {"message": "Format test"}}
            ],
        )

        mock_llm_client.generate.side_effect = [
            mock_response,
            GenerationResponse(content="Formatted correctly."),
        ]

        messages = [Message(role=Role.USER, content="Test formatting")]

        await agentic_client.generate(messages)

        # Check that tool results were properly formatted
        second_call = mock_llm_client.generate.call_args_list[1]
        messages_sent = second_call[1]["messages"]

        # Find the tool result message
        tool_result_msg = None
        for msg in messages_sent:
            if hasattr(msg, "tool_results") and msg.tool_results:
                tool_result_msg = msg
                break

        assert tool_result_msg is not None
        assert len(tool_result_msg.tool_results) == 1
        assert tool_result_msg.tool_results[0].tool_call_id == "call_123"
        assert tool_result_msg.tool_results[0].tool_name == "test_tool"

    async def test_resource_limit_errors(
        self, agentic_client: AgenticClient, mock_llm_client: AsyncMock
    ) -> None:
        """Test resource limit error handling."""
        # Create many tool calls to hit limits
        tool_calls = [
            {"id": f"call_{i}", "name": "test_tool", "arguments": {"message": f"Call {i}"}}
            for i in range(110)  # More than default limit of 100
        ]

        mock_response = GenerationResponse(content="", tool_calls=tool_calls)

        mock_llm_client.generate.side_effect = [
            mock_response,
            GenerationResponse(content="Hit resource limits."),
        ]

        messages = [Message(role=Role.USER, content="Test limits")]

        await agentic_client.generate(messages)

        # Should execute up to limit
        assert hasattr(agentic_client.tool_executor.execute, "call_count")
        assert agentic_client.tool_executor.execute.call_count == 100  # type: ignore[attr-defined]

        # Check error messages were sent for tools beyond limit
        second_call = mock_llm_client.generate.call_args_list[1]
        messages_sent = second_call[1]["messages"]

        tool_result_msg = None
        for msg in messages_sent:
            if hasattr(msg, "tool_results") and msg.tool_results:
                tool_result_msg = msg
                break

        assert tool_result_msg is not None
        # Should have 100 successful + 10 error results
        assert len(tool_result_msg.tool_results) == 110

        # Check last 10 are errors
        for i in range(100, 110):
            result = tool_result_msg.tool_results[i]
            assert result.is_error
            assert result.error_type == ToolErrorType.RESOURCE_LIMIT

    async def test_loop_detection_errors(
        self, agentic_client: AgenticClient, mock_llm_client: AsyncMock
    ) -> None:
        """Test repeated tool call detection."""
        # Create repeated tool calls
        repeated_call = {"id": "call_1", "name": "test_tool", "arguments": {"message": "Same"}}

        responses = []
        for i in range(7):  # More than max_repeated_calls (5)
            responses.append(GenerationResponse(content="", tool_calls=[repeated_call]))
        responses.append(GenerationResponse(content="Done with loops."))

        mock_llm_client.generate.side_effect = responses

        messages = [Message(role=Role.USER, content="Test loop detection")]

        await agentic_client.generate(messages)

        # Should execute 5 times, then return errors
        assert hasattr(agentic_client.tool_executor.execute, "call_count")
        assert agentic_client.tool_executor.execute.call_count == 5  # type: ignore[attr-defined]

    async def test_streaming_with_errors(
        self, agentic_client: AgenticClient, mock_llm_client: AsyncMock, mock_tool_executor: Mock
    ) -> None:
        """Test streaming with tool errors."""
        # Make tool fail
        mock_tool_executor.execute.side_effect = Exception("Stream tool error")

        # Mock the initial streaming response
        async def mock_initial_stream() -> AsyncGenerator[StreamEvent, None]:
            yield StreamEvent(type=StreamEventType.CONTENT, content="ignored")

        # Mock responses
        call_count = 0

        async def mock_generate(**kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if kwargs.get("stream", False):
                # First call with stream=True
                return mock_initial_stream()
            else:
                # Subsequent calls from _handle_streaming_with_tools
                if call_count == 2:
                    # Return tool call
                    return GenerationResponse(
                        content="",
                        tool_calls=[
                            {"id": "call_1", "name": "test_tool", "arguments": {"message": "Fail"}}
                        ],
                    )
                else:
                    # After tool error, return final response
                    return GenerationResponse(content="Error handled in stream.")

        mock_llm_client.generate = mock_generate

        messages = [Message(role=Role.USER, content="Stream error test")]

        events = []
        stream_response = await agentic_client.generate(messages, stream=True)
        # Type narrowing - we know it's AsyncIterator when stream=True
        assert not isinstance(stream_response, GenerationResponse)
        async for event in stream_response:
            events.append(event)

        # Should have tool call and error events
        tool_events = [
            e for e in events if e.type in (StreamEventType.TOOL_CALL, StreamEventType.TOOL_RESULT)
        ]
        assert len(tool_events) >= 2

        # Find error event
        error_event = next(
            (
                e
                for e in events
                if e.type == StreamEventType.TOOL_RESULT and not e.is_tool_success()
            ),
            None,
        )
        assert error_event is not None
        assert error_event.metadata is not None
        assert error_event.metadata["error_type"] == ToolErrorType.EXECUTION_ERROR.value


@pytest.mark.integration
@pytest.mark.llm
@pytest.mark.asyncio
class TestAgenticClientWithRealLLMs:
    """Integration tests with real LLM providers."""

    def _get_required_key_fixture(self, model_id: ModelID) -> Optional[str]:
        """Get the required fixture name for a given model."""
        if model_id in [ModelID.CLAUDE_OPUS_4, ModelID.CLAUDE_SONNET_4]:
            return "require_anthropic_key"
        elif model_id in [
            ModelID.O3_PRO,
            ModelID.O3,
            ModelID.O4_MINI,
            ModelID.GPT_4O,
            ModelID.GPT_4O_MINI,
        ]:
            return "require_openai_key"
        elif model_id in [ModelID.GEMINI_2_5_PRO, ModelID.GEMINI_2_5_FLASH]:
            return "require_gemini_key"
        else:
            return None

    @pytest.mark.parametrize("model_id", REASONING_MODELS)
    async def test_reasoning_models_tool_calling(self, request: Any, model_id: ModelID) -> None:
        """Test tool calling with all reasoning models."""
        # Get the appropriate fixture based on model provider
        fixture_name = self._get_required_key_fixture(model_id)
        if fixture_name:
            request.getfixturevalue(fixture_name)

        client = AgenticClient(llm=model_id)
        await client.initialize()

        try:
            messages = [
                Message(
                    role=Role.USER,
                    content="What files are in the current directory? Just list the first 3.",
                )
            ]

            # O3-pro requires the completions API which is not yet implemented
            if model_id == ModelID.O3_PRO:
                with pytest.raises(
                    NotImplementedError,
                    match="Model o3-pro is not a chat model and requires the completions API",
                ):
                    await client.generate(messages)
            else:
                response = await client.generate(messages)

                # Type narrowing - we know it's GenerationResponse when not streaming
                assert isinstance(response, GenerationResponse)
                assert response.content
                assert len(response.content) > 0
                # Should have used list_files or similar tool
                assert client.last_tools_duration_ms >= 0
        finally:
            await client.close()

    @pytest.mark.parametrize("model_id", REASONING_MODELS)
    async def test_reasoning_models_file_operations(self, request: Any, model_id: ModelID) -> None:
        """Test file operations with all reasoning models."""
        fixture_name = self._get_required_key_fixture(model_id)
        if fixture_name:
            request.getfixturevalue(fixture_name)

        test_file = f"test_{model_id.name.lower()}.txt"
        client = AgenticClient(llm=model_id)
        await client.initialize()

        try:
            messages = [
                Message(
                    role=Role.USER,
                    content=(
                        f"Create a file called {test_file} with content 'Testing {model_id.name}'"
                    ),
                )
            ]

            # O3-pro requires the completions API which is not yet implemented
            if model_id == ModelID.O3_PRO:
                with pytest.raises(
                    NotImplementedError,
                    match="Model o3-pro is not a chat model and requires the completions API",
                ):
                    await client.generate(messages)
            else:
                response = await client.generate(messages)

                # Type narrowing - we know it's GenerationResponse when not streaming
                assert isinstance(response, GenerationResponse)

                # Gemini sometimes has issues with file operations, skip the strict assertions
                if model_id == ModelID.GEMINI_2_5_PRO and not response.content:
                    pytest.skip("Gemini returned empty content for file operations")

                assert response.content
                assert "created" in response.content.lower() or "wrote" in response.content.lower()
                assert os.path.exists(test_file)

                # Verify content
                with open(test_file, "r") as f:
                    content = f.read()
                    assert f"Testing {model_id.name}" in content
        finally:
            await client.close()
            # Cleanup
            if os.path.exists(test_file):
                os.remove(test_file)

    @pytest.mark.parametrize("model_id", REASONING_MODELS)
    async def test_reasoning_models_streaming(self, request: Any, model_id: ModelID) -> None:
        """Test streaming capability with all reasoning models."""
        fixture_name = self._get_required_key_fixture(model_id)
        if fixture_name:
            request.getfixturevalue(fixture_name)

        client = AgenticClient(llm=model_id)
        await client.initialize()

        try:
            messages = [Message(role=Role.USER, content="Count from 1 to 3")]

            # O3-pro requires the completions API which is not yet implemented
            if model_id == ModelID.O3_PRO:
                with pytest.raises(
                    NotImplementedError,
                    match="Model o3-pro is not a chat model and requires the completions API",
                ):
                    result = await client.generate(messages, stream=True)
                    # Type narrowing - if we get here, it's an AsyncIterator
                    assert not isinstance(result, GenerationResponse)
                    async for _ in result:
                        pass
            # Gemini doesn't support streaming yet
            elif model_id == ModelID.GEMINI_2_5_PRO:
                with pytest.raises(
                    NotImplementedError, match="Streaming not yet implemented for Gemini client"
                ):
                    result = await client.generate(messages, stream=True)
                    # Type narrowing - if we get here, it's an AsyncIterator
                    assert not isinstance(result, GenerationResponse)
                    async for _ in result:
                        pass
            else:
                events = []
                result = await client.generate(messages, stream=True)
                # Type narrowing - we know it's AsyncIterator when stream=True
                assert not isinstance(result, GenerationResponse)
                async for event in result:
                    events.append(event)

                # Should have content events
                content_events = [e for e in events if e.type == StreamEventType.CONTENT]
                assert len(content_events) > 0

                # Combine content
                full_content = "".join(e.content for e in content_events if e.content)
                assert "1" in full_content and "3" in full_content
        finally:
            await client.close()

    async def test_cross_model_consistency(self, require_all_llm_keys: None) -> None:
        """Test consistency across all reasoning models."""
        test_query = "List exactly 2 files from the current directory"

        responses: list[tuple[str, Optional[GenerationResponse]]] = []
        for model_id in REASONING_MODELS:
            client = AgenticClient(llm=model_id)
            await client.initialize()

            try:
                messages = [Message(role=Role.USER, content=test_query)]

                # O3-pro requires the completions API which is not yet implemented
                if model_id == ModelID.O3_PRO:
                    with pytest.raises(
                        NotImplementedError,
                        match="Model o3-pro is not a chat model and requires the completions API",
                    ):
                        await client.generate(messages)
                    responses.append((model_id.name, None))  # Skip O3-pro
                else:
                    response = await client.generate(messages)
                    # Type narrowing - we know it's GenerationResponse when not streaming
                    assert isinstance(response, GenerationResponse)
                    responses.append((model_id.name, response))
            finally:
                await client.close()

        # All models (except O3-pro) should give reasonable responses
        for model_name, resp in responses:
            if resp is not None:  # Skip O3-pro
                # Type narrowing - we know it's GenerationResponse when not streaming
                assert isinstance(resp, GenerationResponse)
                assert resp.content, f"{model_name} returned empty content"
                assert len(resp.content) > 10, f"{model_name} returned too short content"

    @pytest.mark.parametrize("model_id", REASONING_MODELS)
    async def test_error_recovery(self, request: Any, model_id: ModelID) -> None:
        """Test that models handle tool errors gracefully."""
        fixture_name = self._get_required_key_fixture(model_id)
        if fixture_name:
            request.getfixturevalue(fixture_name)

        client = AgenticClient(llm=model_id)
        await client.initialize()

        try:
            # Try to read a non-existent file
            messages = [
                Message(
                    role=Role.USER,
                    content=(
                        "Try to read the file /definitely/does/not/exist/file.txt "
                        "and tell me what happened"
                    ),
                )
            ]

            # O3-pro requires the completions API which is not yet implemented
            if model_id == ModelID.O3_PRO:
                with pytest.raises(
                    NotImplementedError,
                    match="Model o3-pro is not a chat model and requires the completions API",
                ):
                    await client.generate(messages)
            else:
                response = await client.generate(messages)

                # Type narrowing - we know it's GenerationResponse when not streaming
                assert isinstance(response, GenerationResponse)
                assert response.content
                # Should mention the error
                assert any(
                    word in response.content.lower() for word in ["not", "error", "exist", "found"]
                )
        finally:
            await client.close()

    async def test_model_selection_helper(self) -> None:
        """Test using model selection helper functions."""
        # Get best reasoning model with constraints
        model = get_reasoning_model(
            min_context_window=100000,
            max_cost_per_1k_input=0.02,  # Limit cost
        )

        # Should return a valid model from REASONING_MODELS
        assert any(model.model_id == m.value for m in REASONING_MODELS)
        assert model.context_window >= 100000
        if model.cost_per_1k_input:
            assert model.cost_per_1k_input <= 0.02

    async def test_extended_thinking_models(self, require_all_llm_keys: None) -> None:
        """Test models with extended thinking capability."""
        # Filter models that have extended thinking
        from client.models import ModelCapability, get_model

        extended_thinking_models = [
            m
            for m in REASONING_MODELS
            if ModelCapability.EXTENDED_THINKING in get_model(m.value).capabilities
        ]

        for model_id in extended_thinking_models:
            client = AgenticClient(llm=model_id)
            await client.initialize()

            try:
                messages = [Message(role=Role.USER, content="What is 47 * 23? Think step by step.")]

                # O3-pro requires the completions API which is not yet implemented
                if model_id == ModelID.O3_PRO:
                    with pytest.raises(
                        NotImplementedError,
                        match="Model o3-pro is not a chat model and requires the completions API",
                    ):
                        await client.generate(messages)
                else:
                    response = await client.generate(messages)

                    # Type narrowing - we know it's GenerationResponse when not streaming
                    assert isinstance(response, GenerationResponse)
                    assert response.content
                    assert "1081" in response.content  # Correct answer
            finally:
                await client.close()

    @pytest.mark.parametrize("model_id", REASONING_MODELS[:2])  # Test first 2 models to save time
    async def test_complex_multi_tool_workflow(self, request: Any, model_id: ModelID) -> None:
        """Test complex workflows requiring multiple tool calls."""
        fixture_name = self._get_required_key_fixture(model_id)
        if fixture_name:
            request.getfixturevalue(fixture_name)

        test_dir = f"test_dir_{model_id.name.lower()}"
        test_file = f"{test_dir}/data.txt"

        client = AgenticClient(llm=model_id)
        await client.initialize()

        try:
            # Complex workflow: create dir, create file, read it, list dir
            messages = [
                Message(
                    role=Role.USER,
                    content=f"""Please do the following:
                1. Create a directory called {test_dir}
                2. Create a file {test_file} with content 'Test data for {model_id.name}'
                3. Read the file back to confirm
                4. List the contents of the directory
                """,
                )
            ]

            # O3-pro requires the completions API which is not yet implemented
            if model_id == ModelID.O3_PRO:
                with pytest.raises(
                    NotImplementedError,
                    match="Model o3-pro is not a chat model and requires the completions API",
                ):
                    await client.generate(messages)
            else:
                response = await client.generate(messages)

                # Type narrowing - we know it's GenerationResponse when not streaming
                assert isinstance(response, GenerationResponse)
                assert response.content
                # Should mention successful completion of all steps
                assert client.last_tools_duration_ms > 0

                # Verify the workflow completed
                assert os.path.exists(test_dir)
                assert os.path.exists(test_file)
        finally:
            await client.close()
            # Cleanup
            if os.path.exists(test_file):
                os.remove(test_file)
            if os.path.exists(test_dir):
                os.rmdir(test_dir)
