"""Integration tests for auth API endpoints using FastAPI TestClient.

These tests use FastAPI's TestClient which automatically handles the server lifecycle.
No actual server needs to be running - TestClient creates an in-process test server.
"""

import pytest
from fastapi.testclient import TestClient

from api.models.auth import AuthLoginRequest, AuthResponse, AuthStatus
from api.server import app

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def client():
    """Create a test client using FastAPI's TestClient.

    This automatically handles the server lifecycle - no need to run a real server.
    """
    return TestClient(app)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestAuth:
    """Integration tests for auth endpoints using FastAPI TestClient."""

    def test_auth_status_endpoint(self, client):
        """Test auth status endpoint returns AuthStatus model."""
        response = client.get("/api/auth/status")

        assert response.status_code == 200

        # Parse response as AuthStatus model
        status = AuthStatus(**response.json())

        # Now we have typed access
        assert isinstance(status.authenticated, bool)
        assert status.provider is None or isinstance(status.provider, str)
        assert isinstance(status.services, list)
        assert status.user_info is None or isinstance(status.user_info, dict)

    def test_auth_login_endpoint(self, client):
        """Test auth login endpoint with AuthLoginRequest."""
        request = AuthLoginRequest(force=False)

        response = client.post("/api/auth/login", json=request.model_dump())

        assert response.status_code == 200

        # Parse response as AuthResponse model
        auth_response = AuthResponse(**response.json())

        # Now we have typed access
        assert isinstance(auth_response.success, bool)
        assert auth_response.auth_url is None or isinstance(auth_response.auth_url, str)
        assert auth_response.message is None or isinstance(auth_response.message, str)

        # Status field should be AuthStatus or None
        if auth_response.status:
            assert isinstance(auth_response.status.authenticated, bool)

    def test_auth_login_force(self, client):
        """Test auth login with force=True."""
        request = AuthLoginRequest(force=True)

        response = client.post("/api/auth/login", json=request.model_dump())

        assert response.status_code == 200

        auth_response = AuthResponse(**response.json())
        assert isinstance(auth_response.success, bool)

    def test_auth_logout_endpoint(self, client):
        """Test auth logout endpoint."""
        response = client.post("/api/auth/logout")

        assert response.status_code == 200

        # Logout returns a dict with success, message, and status
        data = response.json()
        assert isinstance(data["success"], bool)
        assert "message" in data

        # Status should be parseable as AuthStatus
        if "status" in data:
            status = AuthStatus(**data["status"])
            assert status.authenticated is False

    def test_auth_callback_endpoint(self, client):
        """Test auth callback endpoint structure."""
        # Callback requires URL and state parameters
        response = client.get("/api/auth/callback?url=test&state=test")

        # May return various status codes depending on state (404 if not implemented)
        assert response.status_code in [200, 400, 404, 500]

        if response.status_code != 404:
            data = response.json()
            assert "success" in data


# ============================================================================
# MODEL TESTS
# ============================================================================


class TestAuthModels:
    """Test auth-related Pydantic models."""

    def test_auth_status_model(self):
        """Test AuthStatus model."""
        status = AuthStatus(
            authenticated=True,
            provider="google",
            services=["gmail", "drive"],
            user_info={"email": "test@example.com", "name": "Test User"},
        )

        assert status.authenticated is True
        assert status.provider == "google"
        assert len(status.services) == 2
        assert status.user_info["email"] == "test@example.com"

    def test_auth_status_unauthenticated(self):
        """Test AuthStatus model for unauthenticated state."""
        status = AuthStatus(authenticated=False, provider=None, services=[], user_info=None)

        assert status.authenticated is False
        assert status.provider is None
        assert len(status.services) == 0
        assert status.user_info is None

    def test_auth_login_request_model(self):
        """Test AuthLoginRequest model."""
        request = AuthLoginRequest(force=True)
        assert request.force is True

        request_default = AuthLoginRequest()
        assert request_default.force is False

    def test_auth_response_model(self):
        """Test AuthResponse model."""
        status = AuthStatus(authenticated=True, services=["gmail"], provider="google")

        response = AuthResponse(
            success=True,
            auth_url="https://oauth.example.com/authorize",
            message="Login successful",
            status=status,
        )

        assert response.success is True
        assert response.auth_url == "https://oauth.example.com/authorize"
        assert response.message == "Login successful"
        assert response.status.authenticated is True

    def test_auth_response_optional_fields(self):
        """Test AuthResponse with optional fields."""
        response = AuthResponse(success=False)

        assert response.success is False
        assert response.auth_url is None
        assert response.message is None
        assert response.status is None
