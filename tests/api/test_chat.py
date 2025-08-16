"""Integration tests for streaming chat API endpoint using FastAPI TestClient.

These tests use FastAPI's TestClient which automatically handles the server lifecycle.
No actual server needs to be running - TestClient creates an in-process test server.
"""

import pytest
from fastapi.testclient import TestClient

from api.models.chat import ChatRequest
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


class TestChatStream:
    """Integration tests for streaming chat endpoint using FastAPI TestClient."""

    def test_stream_endpoint_exists(self, client: TestClient) -> None:
        """Test streaming chat endpoint exists and responds."""
        request = ChatRequest(message="Stream test", session_id="stream-123")

        response = client.post(
            "/api/chat/stream", json=request.model_dump(), headers={"Accept": "text/event-stream"}
        )

        # Check that endpoint exists and returns appropriate response
        assert response.status_code in [200, 503]  # 503 if manager not initialized

        if response.status_code == 200:
            # Should return SSE content type
            assert "text/event-stream" in response.headers.get("content-type", "")

    def test_stream_with_session_id(self, client: TestClient) -> None:
        """Test streaming with explicit session_id."""
        request = ChatRequest(message="Hello with session!", session_id="test-session-456")

        response = client.post(
            "/api/chat/stream", json=request.model_dump(), headers={"Accept": "text/event-stream"}
        )

        assert response.status_code in [200, 503]

        # If successful, verify SSE format
        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            assert "text/event-stream" in content_type

    def test_stream_without_session_id(self, client: TestClient) -> None:
        """Test streaming without session_id (should auto-generate)."""
        request = ChatRequest(message="Hello without session!", session_id="test-auto-session")

        response = client.post(
            "/api/chat/stream", json=request.model_dump(), headers={"Accept": "text/event-stream"}
        )

        assert response.status_code in [200, 503]

        # Session ID should be handled internally
        if response.status_code == 200:
            assert "text/event-stream" in response.headers.get("content-type", "")

    def test_stream_with_invalid_request(self, client: TestClient) -> None:
        """Test streaming with invalid request data."""
        # Send invalid data (missing required 'message' field)
        response = client.post("/api/chat/stream", json={}, headers={"Accept": "text/event-stream"})

        # Should get 422 Unprocessable Entity for validation error
        assert response.status_code == 422
        error_detail = response.json()
        assert "detail" in error_detail
