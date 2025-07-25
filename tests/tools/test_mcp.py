"""Test MCP server infrastructure and tool execution."""

import asyncio
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio

from client.agentic_client import AgenticClient
from client.base_client import GenerationResponse, Message, Role
from client.mcp_server import MCPServer
from client.models import ModelID
from memory.storage.manager import MemoryManager
from memory.storage.sqlite_backend import SQLiteBackend
from tools.registry import get_tool_registry


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPInfrastructure:
    """Test MCP server and tool infrastructure."""

    @pytest_asyncio.fixture
    async def memory_manager(self, tmp_path: Any) -> AsyncGenerator[MemoryManager, None]:
        """Create memory manager with test data."""
        test_db = tmp_path / "test_mcp.db"
        backend = SQLiteBackend(f"sqlite+aiosqlite:///{test_db}")
        manager = MemoryManager(backend)
        await manager.initialize()

        # Add test data
        await manager.record_conversation_turn(
            user_query="I'm working on a machine learning project with TensorFlow",
            agent_response=(
                "That's great! TensorFlow is excellent for ML. What kind of model are you building?"
            ),
            agent_id="test-agent",
        )
        await manager.record_conversation_turn(
            user_query="I'm building a recommendation system for an e-commerce platform",
            agent_response=(
                "Recommendation systems are very useful! "
                "Are you using collaborative filtering or content-based filtering?"
            ),
            agent_id="test-agent",
        )

        yield manager
        await manager.close()

    @pytest_asyncio.fixture
    async def mcp_server(self) -> AsyncGenerator[MCPServer, None]:
        """Create and start MCP server."""
        server = MCPServer(
            server_path="tools/mcp_server.py",
            env_vars={
                "PYTHONPATH": ".",
                "MCP_TOOLS": "gmail,gdrive",  # Just a few tools for testing
            },
        )
        try:
            await server.start()
            yield server
        finally:
            await server.stop()

    async def test_mcp_server_lifecycle(self, mcp_server: MCPServer) -> None:
        """Test MCP server can start and stop properly."""
        assert mcp_server.is_running

        # Get tools from server
        tools = mcp_server.get_tools()
        assert len(tools) > 0

        # Check that we have the expected tools
        tool_names = [tool["name"] for tool in tools]
        assert any("gmail" in name for name in tool_names)
        assert any("drive" in name for name in tool_names)

    async def test_mcp_server_restart(self) -> None:
        """Test MCP server can be restarted."""
        server = MCPServer(server_path="tools/mcp_server.py", env_vars={"PYTHONPATH": "."})

        # Start server
        await server.start()
        assert server.is_running

        # Stop server
        await server.stop()
        assert not server.is_running

        # Restart server
        await server.start()
        assert server.is_running

        # Clean up
        await server.stop()

    async def test_tool_registry_with_mcp(self, mcp_server: MCPServer) -> None:
        """Test tool registry can discover MCP tools."""
        registry = get_tool_registry()

        # Discover tools
        await registry.discover_and_register_tools(
            core_tools_dir="tools/core", mcp_servers=[mcp_server]
        )

        # Check we have both core and MCP tools
        all_tools = registry.get_all_tools()
        assert len(all_tools) > 0

        # Verify we have both types
        tool_names = [t["name"] for t in all_tools]
        core_tools = [
            name
            for name in tool_names
            if any(core in name for core in ["read_file", "write_file", "search_files"])
        ]
        mcp_tools = [name for name in tool_names if any(mcp in name for mcp in ["gmail", "drive"])]

        assert len(core_tools) > 0, "Should have core tools"
        assert len(mcp_tools) > 0, "Should have MCP tools"

    async def test_agentic_client_with_mcp(
        self, mcp_server: MCPServer, memory_manager: MemoryManager, require_anthropic_key: Any
    ) -> None:
        """Test AgenticClient can use MCP tools."""
        client = AgenticClient(llm=ModelID.CLAUDE_SONNET_4, mcp_servers=[mcp_server])

        # Initialize with memory manager dependency
        await client.initialize(
            tool_dependencies={"memory_manager": memory_manager, "llm_client": client}
        )

        try:
            # Get available tools
            tools = await client.get_available_tools()
            assert len(tools) > 0

            # Test a simple query
            messages = [Message(role=Role.USER, content="What tools do you have available?")]

            response = await client.generate(messages, max_tokens=1000)
            # Type narrowing - generate returns GenerationResponse when stream=False
            assert isinstance(response, GenerationResponse)
            assert response.content
            assert len(response.content) > 0

        finally:
            await client.close()

    async def test_mcp_error_handling(self) -> None:
        """Test MCP server error handling."""
        # Create server with invalid command
        server = MCPServer(server_path="this-command-does-not-exist.py")

        # Should raise exception when trying to start
        with pytest.raises(Exception):
            await server.start()

        assert not server.is_running

    async def test_concurrent_mcp_servers(self) -> None:
        """Test running multiple MCP servers concurrently."""
        servers = []

        # Create multiple servers with different tools
        for i, tool_names in enumerate([["gmail"], ["gdrive"], ["gcal"]]):
            server = MCPServer(
                server_path="tools/mcp_server.py",
                env_vars={"PYTHONPATH": ".", "MCP_TOOLS": ",".join(tool_names)},
            )
            servers.append(server)

        try:
            # Start all servers
            await asyncio.gather(*[s.start() for s in servers])

            # Verify all are running
            for server in servers:
                assert server.is_running
                tools = server.get_tools()
                assert len(tools) > 0

        finally:
            # Stop all servers
            await asyncio.gather(*[s.stop() for s in servers])

    async def test_mcp_tool_execution_timeout(self, mcp_server: MCPServer) -> None:
        """Test MCP tool execution with timeout."""
        # This would test timeout handling, but requires a tool that can be made to timeout
        # For now, just verify the server is responsive
        tools = mcp_server.get_tools()
        assert len(tools) > 0

        # Could add a test tool that sleeps to test timeout handling
