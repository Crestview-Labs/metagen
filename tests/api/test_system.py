"""Integration tests for system API endpoints using FastAPI TestClient.

These tests use FastAPI's TestClient which automatically handles the server lifecycle.
No actual server needs to be running - TestClient creates an in-process test server.
"""

import pytest
from fastapi.testclient import TestClient

from api.models.system import SystemInfo, ToolInfo, ToolsResponse
from api.server import app

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def client() -> TestClient:
    """Create a test client using FastAPI's TestClient.

    This automatically handles the server lifecycle - no need to run a real server.
    """
    return TestClient(app)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestSystem:
    """Integration tests for system endpoints using FastAPI TestClient."""

    def test_system_info_endpoint(self, client: TestClient) -> None:
        """Test system info endpoint returns SystemInfo model."""
        response = client.get("/api/system/info")

        if response.status_code == 200:
            # Parse response as SystemInfo model
            info = SystemInfo(**response.json())

            # Now we can use typed access
            assert info.agent_name
            assert info.model
            assert isinstance(info.tools, list)
            assert info.tool_count >= 0
            assert info.memory_path
            assert isinstance(info.initialized, bool)

            # Tools are ToolInfo objects
            for tool in info.tools:
                assert isinstance(tool.name, str)
                assert isinstance(tool.description, str)
                assert isinstance(tool.input_schema, dict)
        elif response.status_code == 503:
            # Manager not initialized
            assert response.json()["detail"]

    def test_health_check_endpoint(self, client: TestClient) -> None:
        """Test health check endpoint."""
        response = client.get("/api/system/health")

        assert response.status_code == 200
        data = response.json()

        # Health check returns a specific structure
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        assert data["timestamp"]

        if "components" in data:
            components = data["components"]
            assert isinstance(components, dict)

    def test_tools_listing_endpoint(self, client: TestClient) -> None:
        """Test tools listing endpoint returns ToolsResponse model."""
        response = client.get("/api/tools")

        if response.status_code == 200:
            # Parse response as ToolsResponse model
            tools_response = ToolsResponse(**response.json())

            # Now we have typed access
            assert isinstance(tools_response.tools, list)
            assert tools_response.count == len(tools_response.tools)

            # Each tool is a ToolInfo object
            for tool in tools_response.tools:
                assert tool.name
                assert tool.description
                assert isinstance(tool.input_schema, dict)
        elif response.status_code == 503:
            # Manager or MetaAgent not initialized
            assert response.json()["detail"]

    def test_google_tools_endpoint(self, client: TestClient) -> None:
        """Test Google tools endpoint."""
        response = client.get("/api/tools/google")

        if response.status_code == 200:
            data = response.json()

            # Parse tools as ToolInfo objects
            google_tools = [ToolInfo(**tool) for tool in data["tools"]]

            assert data["count"] == len(google_tools)

            services = data["services"]
            gmail_tools = [ToolInfo(**tool) for tool in services["gmail"]]
            drive_tools = [ToolInfo(**tool) for tool in services["drive"]]
            calendar_tools = [ToolInfo(**tool) for tool in services["calendar"]]

            # Verify counts match
            total_google_tools = len(gmail_tools) + len(drive_tools) + len(calendar_tools)
            assert data["count"] == total_google_tools

            # All tools should be valid ToolInfo objects
            for tool in google_tools:
                assert tool.name
                assert tool.description
        elif response.status_code == 503:
            # Manager or MetaAgent not initialized
            assert response.json()["detail"]


# ============================================================================
# MODEL TESTS
# ============================================================================


class TestSystemModels:
    """Test system-related Pydantic models."""

    def test_tool_info_model(self) -> None:
        """Test ToolInfo model."""
        tool = ToolInfo(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
        )

        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.input_schema["type"] == "object"

    def test_tools_response_model(self) -> None:
        """Test ToolsResponse model."""
        tool = ToolInfo(name="tool1", description="Tool 1", input_schema={})

        response = ToolsResponse(tools=[tool], count=1)

        assert len(response.tools) == 1
        assert response.count == 1
        assert response.tools[0].name == "tool1"

    def test_system_info_model(self) -> None:
        """Test SystemInfo model."""
        tool = ToolInfo(name="tool1", description="Tool 1", input_schema={})

        info = SystemInfo(
            agent_name="TestAgent",
            model="claude-opus-4",
            tools=[tool],
            tool_count=1,
            memory_path="/path/to/memory.db",
            initialized=True,
        )

        assert info.agent_name == "TestAgent"
        assert info.model == "claude-opus-4"
        assert len(info.tools) == 1
        assert info.tool_count == 1
        assert info.memory_path == "/path/to/memory.db"
        assert info.initialized is True
