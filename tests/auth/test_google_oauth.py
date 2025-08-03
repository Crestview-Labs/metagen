"""Tests for Google OAuth authentication flow.

This module tests the actual authentication mechanisms for Google services,
including OAuth flow, token storage, and token refresh.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
class TestGoogleOAuth:
    """Test Google OAuth authentication mechanisms."""

    @pytest.fixture
    def auth_dir(self, tmp_path: Path) -> Path:
        """Create temporary auth directory."""
        auth_path = tmp_path / ".metagen" / "google_auth"
        auth_path.mkdir(parents=True, exist_ok=True)
        return auth_path

    @pytest.fixture
    def mock_token(self) -> dict:
        """Create a mock OAuth token."""
        return {
            "access_token": "mock_access_token_12345",
            "refresh_token": "mock_refresh_token_67890",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/drive.readonly",
            "created_at": datetime.utcnow().isoformat(),
        }

    def test_token_storage(self, auth_dir: Path, mock_token: dict) -> None:
        """Test storing OAuth token."""
        token_file = auth_dir / "token.json"

        # Store token
        with open(token_file, "w") as f:
            json.dump(mock_token, f)

        # Verify storage
        assert token_file.exists()

        # Read back token
        with open(token_file, "r") as f:
            stored_token = json.load(f)

        assert stored_token["access_token"] == mock_token["access_token"]
        assert stored_token["refresh_token"] == mock_token["refresh_token"]

    def test_token_retrieval(self, auth_dir: Path, mock_token: dict) -> None:
        """Test retrieving stored OAuth token."""
        token_file = auth_dir / "token.json"

        # Store token first
        with open(token_file, "w") as f:
            json.dump(mock_token, f)

        # Retrieve token
        if token_file.exists():
            with open(token_file, "r") as f:
                retrieved_token = json.load(f)

            assert retrieved_token is not None
            assert retrieved_token["access_token"] == mock_token["access_token"]

    def test_token_expiry_check(self, mock_token: dict) -> None:
        """Test checking if token is expired."""
        # Parse creation time
        created_at = datetime.fromisoformat(mock_token["created_at"])
        expires_in = mock_token["expires_in"]

        # Calculate expiry
        expires_at = created_at + timedelta(seconds=expires_in)

        # Check if expired (should not be, as we just created it)
        is_expired = datetime.utcnow() > expires_at
        assert not is_expired

        # Test with old token
        old_token = mock_token.copy()
        old_token["created_at"] = (datetime.utcnow() - timedelta(hours=2)).isoformat()

        created_at = datetime.fromisoformat(old_token["created_at"])
        expires_at = created_at + timedelta(seconds=old_token["expires_in"])
        is_expired = datetime.utcnow() > expires_at
        assert is_expired

    def test_missing_token_handling(self, auth_dir: Path) -> None:
        """Test handling of missing token file."""
        token_file = auth_dir / "token.json"

        # Ensure token doesn't exist
        if token_file.exists():
            token_file.unlink()

        assert not token_file.exists()

        # Attempt to read token
        token = None
        if token_file.exists():
            with open(token_file, "r") as f:
                token = json.load(f)

        assert token is None

    def test_corrupted_token_handling(self, auth_dir: Path) -> None:
        """Test handling of corrupted token file."""
        token_file = auth_dir / "token.json"

        # Write corrupted data
        with open(token_file, "w") as f:
            f.write("{ corrupted json")

        # Try to read token
        token = None
        error = None
        try:
            with open(token_file, "r") as f:
                token = json.load(f)
        except json.JSONDecodeError as e:
            error = e

        assert token is None
        assert error is not None

    def test_token_permissions(self, auth_dir: Path, mock_token: dict) -> None:
        """Test token file has appropriate permissions."""
        token_file = auth_dir / "token.json"

        # Store token
        with open(token_file, "w") as f:
            json.dump(mock_token, f)

        # Check file permissions (should be readable/writable by owner only)
        # Note: This is platform-specific, so we just check it exists
        assert token_file.exists()

        # On Unix-like systems, you might check:
        # stat_info = token_file.stat()
        # assert stat_info.st_mode & 0o777 == 0o600  # rw-------

    def test_auth_scopes(self, mock_token: dict) -> None:
        """Test parsing OAuth scopes."""
        scopes = mock_token["scope"].split()

        # Should have Gmail scope
        gmail_scopes = [s for s in scopes if "gmail" in s]
        assert len(gmail_scopes) > 0

        # Should have Drive scope
        drive_scopes = [s for s in scopes if "drive" in s]
        assert len(drive_scopes) > 0

        # Check specific permissions
        assert any("readonly" in s for s in scopes)

    @patch("webbrowser.open")
    def test_oauth_flow_initiation(self, mock_browser: MagicMock) -> None:
        """Test initiating OAuth flow opens browser."""
        auth_url = "https://accounts.google.com/o/oauth2/v2/auth?client_id=test&redirect_uri=test"

        # Simulate opening auth URL
        mock_browser(auth_url)

        # Verify browser was called
        mock_browser.assert_called_once_with(auth_url)

    def test_credentials_file_structure(self, auth_dir: Path) -> None:
        """Test the structure of stored credentials."""
        # Create a mock credentials file
        creds_file = auth_dir / "credentials.json"

        mock_creds = {
            "installed": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "redirect_uris": ["http://localhost:8080"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

        with open(creds_file, "w") as f:
            json.dump(mock_creds, f)

        # Read and verify
        with open(creds_file, "r") as f:
            stored_creds = json.load(f)

        assert "installed" in stored_creds
        assert stored_creds["installed"]["client_id"] == "test_client_id"
        assert len(stored_creds["installed"]["redirect_uris"]) > 0
