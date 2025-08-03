"""Tests for agent integration with Google MCP tools.

This module tests how agents (particularly MetaAgent) interact with
Google tools through MCP, including tool discovery, capability description,
and usage patterns.
"""

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio

from agents.memory import MemoryManager
from agents.meta_agent import MetaAgent
from client.mcp_server import MCPServer
from client.models import ModelID
from common.messages import AgentMessage, UserMessage
from tools.registry import get_tool_executor, get_tool_registry


@pytest.mark.integration
@pytest.mark.llm
class TestAgentGoogleToolIntegration:
    """Test how agents interact with Google tools via MCP."""

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

    # Use memory_manager fixture from conftest.py

    @pytest_asyncio.fixture
    async def meta_agent_with_google_tools(
        self, google_mcp_server: MCPServer, memory_manager: MemoryManager
    ) -> AsyncGenerator[MetaAgent, None]:
        """Create MetaAgent with Google tools available."""
        # Register MCP server with tool registry
        executor = get_tool_executor()
        registry = get_tool_registry()
        executor.register_mcp_servers([google_mcp_server])

        # Get available tools from registry and convert to Tool objects
        tool_dicts = registry.get_all_tools()
        from tools.base import Tool

        available_tools = [Tool.from_dict(tool_dict) for tool_dict in tool_dicts]

        # Create MetaAgent with llm_config
        agent = MetaAgent(
            agent_id="test-meta-agent",
            memory_manager=memory_manager,
            llm_config={
                "llm": ModelID.CLAUDE_SONNET_4,
                "api_key": os.getenv("ANTHROPIC_API_KEY"),
                "max_iterations": 10,
                "max_tools_per_turn": 50,
            },
            available_tools=available_tools,
        )

        await agent.initialize()

        yield agent

    async def test_agent_discovers_google_tools(
        self, meta_agent_with_google_tools: MetaAgent
    ) -> None:
        """Test that agent can discover available Google tools."""
        # Get available tools using the public method
        tools = await meta_agent_with_google_tools.get_available_tools()
        tool_names = [tool.name for tool in tools]

        # Should include Google tools
        google_tools = [
            name
            for name in tool_names
            if any(word in name.lower() for word in ["gmail", "gdrive", "gcal", "google"])
        ]

        assert len(google_tools) > 0, f"No Google tools found. Available: {tool_names}"

    async def test_agent_lists_gmail_capabilities(
        self, meta_agent_with_google_tools: MetaAgent
    ) -> None:
        """Test agent can describe Gmail capabilities."""
        response = ""
        user_message = UserMessage(
            content="What Gmail operations can you perform? List the specific tools available."
        )
        async for message in meta_agent_with_google_tools.stream_chat(user_message):
            if isinstance(message, AgentMessage):
                response += message.content

        # Should mention Gmail
        assert "gmail" in response.lower()

        # Should mention specific capabilities
        capabilities = ["send", "search", "read", "email", "message", "inbox"]
        assert any(cap in response.lower() for cap in capabilities), (
            f"Expected Gmail capabilities in response: {response}"
        )

    async def test_agent_describes_drive_operations(
        self, meta_agent_with_google_tools: MetaAgent
    ) -> None:
        """Test agent can describe Google Drive operations."""
        response = ""
        user_message = UserMessage(content="What Google Drive operations are available to you?")
        async for message in meta_agent_with_google_tools.stream_chat(user_message):
            if isinstance(message, AgentMessage):
                response += message.content

        # Should mention Drive
        assert "drive" in response.lower()

        # Should mention specific operations
        operations = ["file", "folder", "upload", "download", "create", "list", "search"]
        assert any(op in response.lower() for op in operations), (
            f"Expected Drive operations in response: {response}"
        )

    async def test_agent_describes_calendar_capabilities(
        self, meta_agent_with_google_tools: MetaAgent
    ) -> None:
        """Test agent can describe Calendar capabilities."""
        response = ""
        user_message = UserMessage(content="What calendar operations can you help me with?")
        async for message in meta_agent_with_google_tools.stream_chat(user_message):
            if isinstance(message, AgentMessage):
                response += message.content

        # Should mention calendar or events
        assert any(word in response.lower() for word in ["calendar", "event"])

        # Should mention specific capabilities
        capabilities = ["create", "list", "update", "delete", "schedule", "meeting"]
        assert any(cap in response.lower() for cap in capabilities), (
            f"Expected calendar capabilities in response: {response}"
        )

    async def test_agent_checks_google_auth_status(
        self, meta_agent_with_google_tools: MetaAgent
    ) -> None:
        """Test agent can check Google authentication status."""
        response = ""
        tool_used = False
        stages_seen = []

        # Try a more explicit request that should definitely use a tool
        user_message = UserMessage(
            content="Use the gmail_search tool to search for emails with the query 'test'"
        )
        from common.messages import ToolStartedMessage

        async for message in meta_agent_with_google_tools.stream_chat(user_message):
            stages_seen.append(type(message).__name__)
            if isinstance(message, ToolStartedMessage):
                tool_used = True
            elif isinstance(message, AgentMessage):
                response += message.content

        # Should have used a tool
        assert tool_used, f"Agent should have used a tool. Stages seen: {stages_seen}"

        # Should mention search or email
        assert any(
            word in response.lower() for word in ["search", "email", "gmail", "found", "results"]
        )

    async def test_agent_handles_missing_auth_gracefully(
        self, meta_agent_with_google_tools: MetaAgent
    ) -> None:
        """Test agent handles missing authentication gracefully."""
        response = ""

        user_message = UserMessage(content="Search my Gmail for messages from last week")
        async for message in meta_agent_with_google_tools.stream_chat(user_message):
            if isinstance(message, AgentMessage):
                response += message.content

        # If not authenticated, should mention auth/permission
        # If authenticated, should mention search results
        assert any(
            phrase in response.lower()
            for phrase in [
                "auth",
                "permission",
                "access",
                "token",
                "credentials",
                "found",
                "email",
                "message",
                "no results",
            ]
        )

    @pytest.mark.skipif(
        not os.path.exists(os.path.expanduser("~/.metagen/google_auth/token.json")),
        reason="Google auth token not found - run /auth google first",
    )
    async def test_agent_uses_gmail_search_with_auth(
        self, meta_agent_with_google_tools: MetaAgent
    ) -> None:
        """Test agent can search Gmail when authenticated."""
        response = ""
        tool_calls = []

        user_message = UserMessage(content="Search my emails for 'test' from the last 7 days")
        from common.messages import ToolCallMessage

        async for message in meta_agent_with_google_tools.stream_chat(user_message):
            if isinstance(message, ToolCallMessage):
                for tool_call in message.tool_calls:
                    tool_calls.append(tool_call.tool_name)
            elif isinstance(message, AgentMessage):
                response += message.content

        # Should have used a Gmail search tool
        gmail_tools_used = [t for t in tool_calls if t and "gmail" in t.lower()]
        assert len(gmail_tools_used) > 0, f"No Gmail tools used. Tools called: {tool_calls}"

        # Should report results
        assert any(
            phrase in response.lower()
            for phrase in ["found", "email", "message", "no results", "search"]
        )

    async def test_agent_suggests_authentication(
        self, meta_agent_with_google_tools: MetaAgent
    ) -> None:
        """Test agent suggests authentication when needed."""
        response = ""

        user_message = UserMessage(
            content="I want to send an email but I'm not sure if I'm authenticated"
        )
        async for message in meta_agent_with_google_tools.stream_chat(user_message):
            if isinstance(message, AgentMessage):
                response += message.content

        # Should check or mention authentication
        assert any(
            word in response.lower()
            for word in ["auth", "authenticate", "permission", "credentials", "token"]
        )

        # Might suggest how to authenticate
        if "not authenticated" in response.lower() or "need to authenticate" in response.lower():
            assert any(
                word in response.lower() for word in ["auth", "authenticate", "login", "credential"]
            )
