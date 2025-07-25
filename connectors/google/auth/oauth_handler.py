"""
OAuth handler for Google services integration in metagen.
This handles Google OAuth tokens for accessing Gmail, Drive, and Calendar APIs.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)


class AsyncGoogleOAuthHandler:
    """OAuth handler for Google services in metagen"""

    def __init__(self) -> None:
        # Use metagen token directory
        self.tokens_dir = Path.home() / ".metagen" / "tokens"
        logger.debug(f"OAuth handler using token directory: {self.tokens_dir}")

    async def load_credentials(self, user_id: str = "default_user") -> Optional[Credentials]:
        """Load stored OAuth credentials"""
        # Updated to match metagen auth naming: {user_id}_google_token.json
        token_file = self.tokens_dir / f"{user_id}_google_token.json"

        if not token_file.exists():
            logger.warning(f"No token file found at {token_file}")
            return None

        try:
            # Run file I/O in executor to keep it async
            loop = asyncio.get_event_loop()
            token_data = await loop.run_in_executor(
                None, lambda: json.loads(token_file.read_text())
            )

            # Create credentials from stored token
            credentials = Credentials(
                token=token_data.get("access_token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes"),
            )

            logger.debug("Successfully loaded credentials")
            return credentials

        except Exception as e:
            logger.error(f"Error loading credentials: {e}")
            return None

    async def store_credentials(self, user_id: str, credentials: Credentials) -> None:
        """Store OAuth credentials"""
        try:
            # Ensure directory exists
            self.tokens_dir.mkdir(parents=True, exist_ok=True)

            # Updated to match metagen auth naming: {user_id}_google_token.json
            token_file = self.tokens_dir / f"{user_id}_google_token.json"

            # Extract credential data
            token_data = {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": credentials.scopes,
            }

            # Save to file
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: token_file.write_text(json.dumps(token_data, indent=2))
            )

            logger.debug("Successfully stored credentials")

        except Exception as e:
            logger.error(f"Error storing credentials: {e}")
            raise

    async def refresh_token(self, credentials: Credentials) -> Credentials:
        """Refresh expired OAuth token"""
        try:
            # Run refresh in executor to keep it async
            loop = asyncio.get_event_loop()

            def _refresh() -> Credentials:
                if credentials.expired and credentials.refresh_token:
                    credentials.refresh(Request())
                return credentials

            refreshed_creds = await loop.run_in_executor(None, _refresh)
            logger.debug("Successfully refreshed credentials")
            return refreshed_creds  # type: ignore[no-any-return]

        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            raise ValueError(f"Failed to refresh token: {str(e)}")

    async def revoke_authentication(self, user_id: str = "default_user") -> bool:
        """Revoke stored authentication"""
        try:
            token_file = self.tokens_dir / f"{user_id}_google_token.json"
            if token_file.exists():
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, token_file.unlink)
                logger.debug("Successfully revoked authentication")
            return True
        except Exception as e:
            logger.error(f"Error revoking authentication: {e}")
            return False
