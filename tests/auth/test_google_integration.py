"""Test Google services integration with metagen."""

import logging
import os
from typing import Any, AsyncGenerator

import pytest
import pytest_asyncio

from client.agentic_client import AgenticClient
from client.base_client import GenerationResponse, Message, Role
from client.mcp_server import MCPServer
from client.models import ModelID

# Set up test logger
logger = logging.getLogger(__name__)


@pytest.mark.integration
@pytest.mark.llm
@pytest.mark.asyncio
class TestGoogleIntegration:
    """Test Google services integration with metagen."""

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

    @pytest_asyncio.fixture
    async def agentic_client_with_google(
        self, google_mcp_server: MCPServer, require_anthropic_key: Any
    ) -> AsyncGenerator[AgenticClient, None]:
        """Create AgenticClient with Google tools."""
        client = AgenticClient(llm=ModelID.CLAUDE_SONNET_4, mcp_servers=[google_mcp_server])
        await client.initialize()
        try:
            yield client
        finally:
            await client.close()

    async def test_google_auth_status(self, agentic_client_with_google: AgenticClient) -> None:
        """Test checking Google auth status."""
        messages = [Message(role=Role.USER, content="Check my Google authentication status")]

        response = await agentic_client_with_google.generate(messages)
        assert isinstance(response, GenerationResponse)
        assert response.content
        assert "auth" in response.content.lower() or "google" in response.content.lower()
        # Should have used google_auth_status tool
        assert agentic_client_with_google.last_tools_duration_ms > 0

    async def test_gmail_capabilities(self, agentic_client_with_google: AgenticClient) -> None:
        """Test Gmail tool availability."""
        messages = [Message(role=Role.USER, content="List the Gmail tools available to me")]

        response = await agentic_client_with_google.generate(messages)
        assert isinstance(response, GenerationResponse)
        assert response.content
        assert "gmail" in response.content.lower()
        # Should mention some Gmail capabilities
        assert any(word in response.content.lower() for word in ["send", "search", "read", "email"])

    async def test_drive_capabilities(self, agentic_client_with_google: AgenticClient) -> None:
        """Test Google Drive tool availability."""
        messages = [
            Message(role=Role.USER, content="What Google Drive operations can you perform?")
        ]

        response = await agentic_client_with_google.generate(messages)
        assert isinstance(response, GenerationResponse)
        assert response.content
        assert "drive" in response.content.lower()
        # Should mention some Drive capabilities
        assert any(
            word in response.content.lower() for word in ["file", "folder", "upload", "download"]
        )

    async def test_calendar_capabilities(self, agentic_client_with_google: AgenticClient) -> None:
        """Test Google Calendar tool availability."""
        messages = [Message(role=Role.USER, content="What calendar operations are available?")]

        response = await agentic_client_with_google.generate(messages)
        assert isinstance(response, GenerationResponse)
        assert response.content
        assert "calendar" in response.content.lower() or "event" in response.content.lower()

    @pytest.mark.skipif(
        not os.path.exists(os.path.expanduser("~/.metagen/google_auth/token.json")),
        reason="Google auth token not found - run /auth google first",
    )
    async def test_gmail_search_with_auth(self, agentic_client_with_google: AgenticClient) -> None:
        """Test actual Gmail search (requires authentication)."""
        messages = [
            Message(
                role=Role.USER, content="Search my emails for the term 'test' from the last 7 days"
            )
        ]

        response = await agentic_client_with_google.generate(messages)
        assert isinstance(response, GenerationResponse)
        assert response.content
        # Should either find emails or report no results
        assert any(
            phrase in response.content.lower()
            for phrase in ["found", "email", "no results", "no emails"]
        )
        assert agentic_client_with_google.last_tools_duration_ms > 0

    async def test_error_handling_without_auth(
        self, agentic_client_with_google: AgenticClient
    ) -> None:
        """Test graceful error handling when not authenticated."""
        messages = [Message(role=Role.USER, content="Send an email to test@example.com")]

        response = await agentic_client_with_google.generate(messages)
        assert isinstance(response, GenerationResponse)
        assert response.content
        # Should mention authentication or authorization
        if "sent" not in response.content.lower():
            assert any(
                word in response.content.lower()
                for word in ["auth", "permission", "access", "token"]
            )
