"""Tests for the ToolExecutor component.

This module tests the tool executor functionality including
interceptors, error handling, and result formatting.
"""

import asyncio
import uuid
from typing import Any, Optional
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import BaseModel

from client.mcp_server import MCPServer
from common.types import ToolCall, ToolCallResult, ToolErrorType
from tools.base import BaseCoreTool
from tools.registry import ToolExecutor


class MockToolInput(BaseModel):
    """Input schema for mock tool."""

    input: str = "default"
    fail: bool = False


class MockToolOutput(BaseModel):
    """Output schema for mock tool."""

    result: str
    metadata: dict = {}


class MockTool(BaseCoreTool):
    """Mock tool for testing."""

    def __init__(self, name: str = "mock_tool"):
        super().__init__(
            name=name,
            description="A mock tool for testing",
            input_schema=MockToolInput,
            output_schema=MockToolOutput,
        )
        self.execute_called = False
        self.last_params: Optional[dict[str, Any]] = None

    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """Execute tool implementation."""
        # Cast to the specific type we expect
        assert isinstance(input_data, MockToolInput)
        mock_input: MockToolInput = input_data
        self.execute_called = True
        self.last_params = mock_input.model_dump()

        if mock_input.fail:
            raise RuntimeError("Simulated failure")

        return MockToolOutput(
            result=f"Mock result: {mock_input.input}",
            metadata={"mock": True, "params": mock_input.model_dump()},
        )


@pytest.mark.unit
class TestToolExecutor:
    """Test ToolExecutor functionality."""

    @pytest.fixture
    def executor(self) -> ToolExecutor:
        """Create a fresh ToolExecutor instance."""
        return ToolExecutor()

    @pytest.fixture
    def mock_tool(self) -> MockTool:
        """Create a mock tool."""
        return MockTool()

    async def test_register_and_execute_core_tool(
        self, executor: ToolExecutor, mock_tool: MockTool
    ) -> None:
        """Test registering and executing a core tool."""
        # Register the tool
        executor.register_core_tool(mock_tool)
        assert "mock_tool" in executor.core_tools

        # Execute the tool
        tool_call = ToolCall(
            id=str(uuid.uuid4()), name="mock_tool", arguments={"input": "test data"}
        )
        result = await executor.execute(tool_call)

        assert mock_tool.execute_called
        assert mock_tool.last_params is not None
        assert mock_tool.last_params["input"] == "test data"
        assert not result.is_error
        assert "test data" in result.content
        # The metadata structure may be different due to BaseCoreTool's handling
        assert result.tool_name == "mock_tool"

    async def test_execute_nonexistent_tool(self, executor: ToolExecutor) -> None:
        """Test executing a tool that doesn't exist."""
        tool_call = ToolCall(id=str(uuid.uuid4()), name="nonexistent_tool", arguments={})
        result = await executor.execute(tool_call)

        assert result.is_error
        assert result.error_type == ToolErrorType.INVALID_ARGS
        assert result.error is not None
        assert "not found" in result.error.lower()

    async def test_tool_execution_error_handling(
        self, executor: ToolExecutor, mock_tool: MockTool
    ) -> None:
        """Test handling of tool execution errors."""
        executor.register_core_tool(mock_tool)

        # Execute with failure flag
        tool_call = ToolCall(id=str(uuid.uuid4()), name="mock_tool", arguments={"fail": True})
        result = await executor.execute(tool_call)

        assert result.is_error
        assert result.error_type == ToolErrorType.EXECUTION_ERROR
        assert result.error is not None
        assert "Simulated failure" in result.error

    async def test_interceptor_blocks_execution(
        self, executor: ToolExecutor, mock_tool: MockTool
    ) -> None:
        """Test that interceptors can block tool execution."""
        executor.register_core_tool(mock_tool)

        # Create an interceptor that handles the call
        async def blocking_interceptor(
            tool_name: str, params: dict[str, Any]
        ) -> Optional[ToolCallResult]:
            return ToolCallResult(
                tool_name=tool_name,
                tool_call_id="",  # Will be set by executor
                content="Intercepted!",
                is_error=False,
                error=None,
                error_type=None,
                user_display="This was intercepted",
                metadata={"intercepted": True},
            )

        executor.register_interceptor("mock_tool", blocking_interceptor)

        # Execute the tool
        tool_call = ToolCall(id=str(uuid.uuid4()), name="mock_tool", arguments={"input": "test"})
        result = await executor.execute(tool_call)

        # Tool should not have been called
        assert not mock_tool.execute_called
        assert result.content == "Intercepted!"
        assert result.metadata["intercepted"] is True

    async def test_interceptor_allows_execution(
        self, executor: ToolExecutor, mock_tool: MockTool
    ) -> None:
        """Test that interceptors can allow tool execution."""
        executor.register_core_tool(mock_tool)

        # Create an interceptor that returns None (allows execution)
        async def passthrough_interceptor(
            tool_name: str, params: dict[str, Any]
        ) -> Optional[ToolCallResult]:
            # Could do logging, validation, etc. here
            return None

        executor.register_interceptor("mock_tool", passthrough_interceptor)

        # Execute the tool
        tool_call = ToolCall(id=str(uuid.uuid4()), name="mock_tool", arguments={"input": "test"})
        result = await executor.execute(tool_call)

        # Tool should have been called normally
        assert mock_tool.execute_called
        assert "test" in result.content

    async def test_interceptor_error_handling(
        self, executor: ToolExecutor, mock_tool: MockTool
    ) -> None:
        """Test that interceptor errors don't break execution."""
        executor.register_core_tool(mock_tool)

        # Create an interceptor that raises an error
        async def failing_interceptor(
            tool_name: str, params: dict[str, Any]
        ) -> Optional[ToolCallResult]:
            raise RuntimeError("Interceptor failed!")

        executor.register_interceptor("mock_tool", failing_interceptor)

        # Execute the tool - should proceed despite interceptor failure
        tool_call = ToolCall(id=str(uuid.uuid4()), name="mock_tool", arguments={"input": "test"})
        result = await executor.execute(tool_call)

        # Tool should have been called normally
        assert mock_tool.execute_called
        assert "test" in result.content

    async def test_remove_interceptor(self, executor: ToolExecutor, mock_tool: MockTool) -> None:
        """Test removing an interceptor."""
        executor.register_core_tool(mock_tool)

        # Add interceptor
        async def interceptor(tool_name: str, params: dict[str, Any]) -> Optional[ToolCallResult]:
            return ToolCallResult(
                tool_name=tool_name,
                tool_call_id="",  # Will be set by executor
                content="Intercepted!",
                is_error=False,
                error=None,
                error_type=None,
                user_display="Intercepted",
                metadata={},
            )

        executor.register_interceptor("mock_tool", interceptor)

        # Verify interceptor works
        tool_call = ToolCall(id=str(uuid.uuid4()), name="mock_tool", arguments={"input": "test"})
        result = await executor.execute(tool_call)
        assert result.content == "Intercepted!"

        # Remove interceptor
        executor.remove_interceptor("mock_tool")

        # Now execution should go through normally
        tool_call = ToolCall(id=str(uuid.uuid4()), name="mock_tool", arguments={"input": "test"})
        result = await executor.execute(tool_call)
        assert mock_tool.execute_called
        assert "test" in result.content

    async def test_multiple_tools(self, executor: ToolExecutor) -> None:
        """Test executor with multiple tools."""
        tool1 = MockTool("tool1")
        tool2 = MockTool("tool2")

        executor.register_core_tool(tool1)
        executor.register_core_tool(tool2)

        # Execute both tools
        tool_call1 = ToolCall(id=str(uuid.uuid4()), name="tool1", arguments={"input": "data1"})
        result1 = await executor.execute(tool_call1)
        tool_call2 = ToolCall(id=str(uuid.uuid4()), name="tool2", arguments={"input": "data2"})
        result2 = await executor.execute(tool_call2)

        assert tool1.execute_called
        assert tool2.execute_called
        assert "data1" in result1.content
        assert "data2" in result2.content

    async def test_concurrent_execution(self, executor: ToolExecutor) -> None:
        """Test concurrent tool execution."""
        # Create tools with different delays
        tools = [MockTool(f"tool{i}") for i in range(5)]
        for tool in tools:
            executor.register_core_tool(tool)

        # Execute all tools concurrently
        tasks = [
            executor.execute(
                ToolCall(id=str(uuid.uuid4()), name=f"tool{i}", arguments={"input": f"data{i}"})
            )
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks)

        # Verify all executed successfully
        for i, result in enumerate(results):
            assert not result.is_error
            assert f"data{i}" in result.content
            assert tools[i].execute_called

    async def test_tool_call_id_propagation(
        self, executor: ToolExecutor, mock_tool: MockTool
    ) -> None:
        """Test that tool_call_id is properly propagated through execution."""
        executor.register_core_tool(mock_tool)

        # Create tool call with specific ID
        tool_id = str(uuid.uuid4())
        tool_call = ToolCall(id=tool_id, name="mock_tool", arguments={"input": "test"})

        result = await executor.execute(tool_call)

        # Verify tool_call_id is set in result
        assert result.tool_call_id == tool_id
        assert not result.is_error

    async def test_tool_call_id_propagation_with_error(
        self, executor: ToolExecutor, mock_tool: MockTool
    ) -> None:
        """Test that tool_call_id is propagated even on errors."""
        executor.register_core_tool(mock_tool)

        # Create tool call that will fail
        tool_id = str(uuid.uuid4())
        tool_call = ToolCall(id=tool_id, name="mock_tool", arguments={"fail": True})

        result = await executor.execute(tool_call)

        # Verify tool_call_id is set even in error result
        assert result.tool_call_id == tool_id
        assert result.is_error

    async def test_tool_call_id_propagation_nonexistent(self, executor: ToolExecutor) -> None:
        """Test that tool_call_id is propagated for non-existent tools."""
        tool_id = str(uuid.uuid4())
        tool_call = ToolCall(id=tool_id, name="does_not_exist", arguments={})

        result = await executor.execute(tool_call)

        # Verify tool_call_id is set in error result
        assert result.tool_call_id == tool_id
        assert result.is_error
        assert result.error_type == ToolErrorType.INVALID_ARGS

    async def test_interceptor_preserves_tool_call_id(
        self, executor: ToolExecutor, mock_tool: MockTool
    ) -> None:
        """Test that interceptors preserve tool_call_id."""
        executor.register_core_tool(mock_tool)

        # Interceptor that doesn't set tool_call_id
        async def interceptor(tool_name: str, params: dict[str, Any]) -> Optional[ToolCallResult]:
            return ToolCallResult(
                tool_name=tool_name,
                tool_call_id="",  # Will be set by executor
                content="Intercepted",
                is_error=False,
                error=None,
                error_type=None,
                user_display="Intercepted",
                metadata={},
            )

        executor.register_interceptor("mock_tool", interceptor)

        tool_id = str(uuid.uuid4())
        tool_call = ToolCall(id=tool_id, name="mock_tool", arguments={"input": "test"})

        result = await executor.execute(tool_call)

        # Verify executor sets tool_call_id even if interceptor doesn't
        assert result.tool_call_id == tool_id

    async def test_mcp_tool_execution(self, executor: ToolExecutor) -> None:
        """Test executing tools via MCP server."""
        # Create mock MCP server
        mock_server = Mock(spec=MCPServer)
        mock_server.is_running = True
        mock_server.has_tool = Mock(return_value=True)

        # Mock MCP result format
        mock_mcp_result = Mock()
        mock_mcp_result.content = [Mock(text="MCP tool result")]
        mock_mcp_result.isError = False
        mock_server.call_tool = AsyncMock(return_value=mock_mcp_result)

        executor.register_mcp_servers([mock_server])

        # Execute MCP tool
        tool_id = str(uuid.uuid4())
        tool_call = ToolCall(id=tool_id, name="mcp_tool", arguments={"param": "value"})

        result = await executor.execute(tool_call)

        # Verify MCP server was called
        mock_server.has_tool.assert_called_with("mcp_tool")
        mock_server.call_tool.assert_called_once_with("mcp_tool", {"param": "value"})

        # Verify result
        assert not result.is_error
        assert result.content == "MCP tool result"
        assert result.tool_call_id == tool_id
        assert result.metadata.get("mcp_server") is True

    async def test_mcp_tool_error_handling(self, executor: ToolExecutor) -> None:
        """Test MCP tool error handling."""
        # Create mock MCP server
        mock_server = Mock(spec=MCPServer)
        mock_server.is_running = True
        mock_server.has_tool = Mock(return_value=True)

        # Mock MCP error result
        mock_mcp_result = Mock()
        mock_mcp_result.content = [Mock(text="MCP error message")]
        mock_mcp_result.isError = True
        mock_server.call_tool = AsyncMock(return_value=mock_mcp_result)

        executor.register_mcp_servers([mock_server])

        # Execute MCP tool
        tool_id = str(uuid.uuid4())
        tool_call = ToolCall(id=tool_id, name="mcp_tool", arguments={})

        result = await executor.execute(tool_call)

        # Verify error handling
        assert result.is_error
        assert result.error == "MCP error message"
        assert result.error_type == ToolErrorType.EXECUTION_ERROR
        assert result.tool_call_id == tool_id

    async def test_mcp_server_not_running(self, executor: ToolExecutor) -> None:
        """Test handling of MCP server that's not running."""
        # Create mock MCP server that's not running
        mock_server = Mock(spec=MCPServer)
        mock_server.is_running = False

        executor.register_mcp_servers([mock_server])

        # Try to execute tool
        tool_call = ToolCall(id=str(uuid.uuid4()), name="mcp_tool", arguments={})

        result = await executor.execute(tool_call)

        # Should return tool not found error
        assert result.is_error
        assert result.error is not None
        assert "not found" in result.error.lower()
        assert result.error_type == ToolErrorType.INVALID_ARGS

    async def test_mcp_tool_exception(self, executor: ToolExecutor) -> None:
        """Test handling of MCP tool that raises exception."""
        # Create mock MCP server
        mock_server = Mock(spec=MCPServer)
        mock_server.is_running = True
        mock_server.has_tool = Mock(return_value=True)
        mock_server.call_tool = AsyncMock(side_effect=RuntimeError("MCP connection error"))

        executor.register_mcp_servers([mock_server])

        # Execute MCP tool
        tool_id = str(uuid.uuid4())
        tool_call = ToolCall(id=tool_id, name="mcp_tool", arguments={})

        result = await executor.execute(tool_call)

        # Verify exception handling
        assert result.is_error
        assert "MCP tool execution failed" in result.content
        assert result.error is not None
        assert "MCP connection error" in result.error
        assert result.error_type == ToolErrorType.EXECUTION_ERROR
        assert result.tool_call_id == tool_id

    async def test_multiple_mcp_servers(self, executor: ToolExecutor) -> None:
        """Test tool resolution across multiple MCP servers."""
        # Create two mock MCP servers
        server1 = Mock(spec=MCPServer)
        server1.is_running = True
        server1.has_tool = Mock(side_effect=lambda name: name == "tool1")

        server2 = Mock(spec=MCPServer)
        server2.is_running = True
        server2.has_tool = Mock(side_effect=lambda name: name == "tool2")

        # Mock results
        result1 = Mock(content=[Mock(text="Result from server1")], isError=False)
        result2 = Mock(content=[Mock(text="Result from server2")], isError=False)

        server1.call_tool = AsyncMock(return_value=result1)
        server2.call_tool = AsyncMock(return_value=result2)

        executor.register_mcp_servers([server1, server2])

        # Execute tool from server2
        tool_call = ToolCall(id=str(uuid.uuid4()), name="tool2", arguments={})

        result = await executor.execute(tool_call)

        # Verify correct server was used
        server1.has_tool.assert_called_with("tool2")
        server2.has_tool.assert_called_with("tool2")
        server1.call_tool.assert_not_called()
        server2.call_tool.assert_called_once()

        assert result.content == "Result from server2"
