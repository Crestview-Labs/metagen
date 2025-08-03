"""Tests for Google MCP tool infrastructure.

This module tests the MCP server infrastructure for Google tools,
including tool discovery, schemas, and direct execution without agents.
"""

import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio

from client.mcp_server import MCPServer
from common.types import ToolCall
from tools.registry import get_tool_executor


@pytest.mark.integration
class TestGoogleMCPInfrastructure:
    """Test Google tools MCP infrastructure without agents."""

    @pytest_asyncio.fixture
    async def google_mcp_server(self) -> AsyncGenerator[MCPServer, None]:
        """Create MCP server with Google tools."""
        server = MCPServer(
            server_path="tools/mcp_server.py",
            env_vars={"PYTHONPATH": ".", "MCP_TOOLS": "gmail,gdrive,gcal"},
        )
        try:
            await server.start()
            yield server
        finally:
            await server.stop()

    async def test_google_mcp_server_startup(self, google_mcp_server: MCPServer) -> None:
        """Test that MCP server starts successfully with Google tools."""
        assert google_mcp_server.is_running
        assert google_mcp_server._initialized

    async def test_google_tools_discovery(self, google_mcp_server: MCPServer) -> None:
        """Test that Google tools are discovered by the MCP server."""
        tools = google_mcp_server.get_tools()
        tool_names = [tool["name"] for tool in tools]

        # Should have Gmail tools
        gmail_tools = [name for name in tool_names if "gmail" in name.lower()]
        assert len(gmail_tools) > 0, f"No Gmail tools found. Available tools: {tool_names}"

        # Should have Drive tools
        drive_tools = [
            name for name in tool_names if "drive" in name.lower() or "gdrive" in name.lower()
        ]
        assert len(drive_tools) > 0, f"No Drive tools found. Available tools: {tool_names}"

        # Should have Calendar tools
        calendar_tools = [
            name for name in tool_names if "calendar" in name.lower() or "gcal" in name.lower()
        ]
        assert len(calendar_tools) > 0, f"No Calendar tools found. Available tools: {tool_names}"

    async def test_google_auth_status_tool(self, google_mcp_server: MCPServer) -> None:
        """Test that google_auth_status tool is available."""
        tools = google_mcp_server.get_tools()
        auth_tools = [tool for tool in tools if tool["name"] == "google_auth_status"]

        assert len(auth_tools) == 1, "google_auth_status tool not found"
        auth_tool = auth_tools[0]

        # Check tool schema
        assert "description" in auth_tool
        assert "auth" in auth_tool["description"].lower()

    async def test_gmail_tool_schemas(self, google_mcp_server: MCPServer) -> None:
        """Test Gmail tool schemas are properly defined."""
        tools = google_mcp_server.get_tools()

        # Find a Gmail search tool
        gmail_search_tools = [
            tool
            for tool in tools
            if "gmail" in tool["name"].lower() and "search" in tool["name"].lower()
        ]

        if gmail_search_tools:
            search_tool = gmail_search_tools[0]
            assert "input_schema" in search_tool

            # Should have some parameters for search
            schema = search_tool.get("input_schema", {})
            if "properties" in schema:
                # Common search parameters
                props = schema["properties"]
                # Different tools might have different params, just check it has some
                assert len(props) > 0, "Gmail search tool has no parameters"

    async def test_direct_google_auth_check(self, google_mcp_server: MCPServer) -> None:
        """Test direct execution of google_auth_status tool."""
        # Register MCP server with tool registry
        # registry = get_tool_registry()  # unused
        executor = get_tool_executor()
        executor.register_mcp_servers([google_mcp_server])

        # Execute google_auth_status directly
        tool_call = ToolCall(id=str(uuid.uuid4()), name="google_auth_status", arguments={})
        result = await executor.execute(tool_call)

        assert not result.is_error, f"Tool execution failed: {result.error}"
        assert result.content
        # Should return auth status
        assert "auth" in result.content.lower() or "token" in result.content.lower()

    async def test_gmail_search_without_auth(self, google_mcp_server: MCPServer) -> None:
        """Test Gmail search tool handles missing auth gracefully."""
        # Register MCP server with tool registry
        # registry = get_tool_registry()  # unused
        executor = get_tool_executor()
        executor.register_mcp_servers([google_mcp_server])

        # Try to search emails without auth
        tools = google_mcp_server.get_tools()
        gmail_search_tools = [
            tool
            for tool in tools
            if "gmail" in tool["name"].lower() and "search" in tool["name"].lower()
        ]

        if gmail_search_tools:
            tool_name = gmail_search_tools[0]["name"]
            tool_call = ToolCall(
                id=str(uuid.uuid4()), name=tool_name, arguments={"query": "test", "max_results": 5}
            )
            result = await executor.execute(tool_call)

            # Should either work (if token exists) or fail gracefully
            if result.is_error:
                assert result.error is not None
                assert any(
                    word in result.error.lower()
                    for word in ["auth", "token", "permission", "credentials"]
                )

    async def test_multiple_google_tool_types(self, google_mcp_server: MCPServer) -> None:
        """Test that multiple types of Google tools are available."""
        tools = google_mcp_server.get_tools()
        tool_names = [tool["name"] for tool in tools]

        # Categorize tools
        tool_categories: dict[str, list[str]] = {
            "auth": [],
            "gmail": [],
            "drive": [],
            "calendar": [],
        }

        for name in tool_names:
            name_lower = name.lower()
            if "auth" in name_lower:
                tool_categories["auth"].append(name)
            elif "gmail" in name_lower or "email" in name_lower:
                tool_categories["gmail"].append(name)
            elif "drive" in name_lower or "gdrive" in name_lower:
                tool_categories["drive"].append(name)
            elif "calendar" in name_lower or "gcal" in name_lower or "event" in name_lower:
                tool_categories["calendar"].append(name)

        # Should have tools in multiple categories
        non_empty_categories = [cat for cat, tools in tool_categories.items() if tools]
        assert len(non_empty_categories) >= 3, (
            f"Expected tools in at least 3 categories, found {len(non_empty_categories)}: "
            f"{non_empty_categories}"
        )

    async def test_tool_error_handling(self, google_mcp_server: MCPServer) -> None:
        """Test that tools handle errors gracefully."""
        # registry = get_tool_registry()  # unused
        executor = get_tool_executor()
        executor.register_mcp_servers([google_mcp_server])

        # Try to execute a tool with invalid parameters
        tools = google_mcp_server.get_tools()
        if tools:
            tool = tools[0]
            # Execute with intentionally wrong parameters
            tool_call = ToolCall(
                id=str(uuid.uuid4()),
                name=tool["name"],
                arguments={"invalid_param": "invalid_value"},
            )
            result = await executor.execute(tool_call)

            # Should handle gracefully
            assert result.tool_name == tool["name"]
            # May or may not be an error depending on the tool's parameter handling
            if result.is_error:
                assert result.error is not None
