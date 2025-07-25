"""Google OAuth authentication for metagen - shared between CLI and UI."""

import asyncio
import json
import logging
import os
import secrets
import webbrowser
from typing import Any, Optional

from aiohttp import web
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from .base_auth import BaseAuthProvider

logger = logging.getLogger(__name__)


class MetagenGoogleAuth(BaseAuthProvider):
    """Google OAuth implementation for metagen (shared between CLI and UI)"""

    def __init__(self, user_id: str = "default_user", client_secrets_path: Optional[str] = None):
        super().__init__(user_id)
        self.client_secrets_file: Optional[str]

        # Look for client_secrets.json
        if client_secrets_path:
            self.client_secrets_file = client_secrets_path
        else:
            # Try common locations
            possible_paths = [
                "client_secrets.json",  # Current directory
                "auth/client_secrets.json",  # Auth directory
                "../client_secrets.json",  # Parent directory
            ]

            self.client_secrets_file = None
            for path in possible_paths:
                if os.path.exists(path):
                    self.client_secrets_file = path
                    break

        if not self.client_secrets_file or not os.path.exists(self.client_secrets_file):
            raise FileNotFoundError(
                "client_secrets.json not found. Please:\n"
                "1. Go to https://console.cloud.google.com/\n"
                "2. Create a project and enable Gmail, Drive, Calendar APIs\n"
                "3. Create OAuth 2.0 credentials (Web application)\n"
                "4. Add redirect URI: http://localhost:8000/oauth/callback\n"
                "5. Download as client_secrets.json and place in metagen directory"
            )

        # TODO: Read redirect_uri and port directly from client_secrets.json
        # instead of hardcoding. This would make the configuration more flexible
        # and avoid mismatches between the app and Google OAuth settings.
        self.redirect_uri = "http://localhost:8000/oauth/callback"
        self.port = 8000

        logger.debug(f"Google auth initialized for user {user_id}")

    @property
    def provider_name(self) -> str:
        return "google"

    @property
    def scopes(self) -> list:
        """Google API scopes for Gmail, Drive, Calendar, Docs, Sheets, and Slides"""
        return [
            "openid",  # Required when using userinfo scopes
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/documents",  # Google Docs
            "https://www.googleapis.com/auth/spreadsheets",  # Google Sheets
            "https://www.googleapis.com/auth/presentations",  # Google Slides
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ]

    def get_auth_url(self) -> tuple[Optional[str], Optional[Flow], Optional[str]]:
        """Get the OAuth authorization URL and flow objects"""
        try:
            # Create OAuth flow
            flow = Flow.from_client_secrets_file(
                self.client_secrets_file, scopes=self.scopes, redirect_uri=self.redirect_uri
            )

            # Generate state for security
            state = secrets.token_urlsafe(32)

            # Get authorization URL
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="false",  # Don't include previously granted scopes
                state=state,
                prompt="consent",  # Force consent to get refresh token
            )

            return auth_url, flow, state
        except Exception as e:
            logger.error(f"Error generating auth URL: {e}")
            return None, None, None

    async def authenticate(self) -> bool:
        """Run the OAuth flow (BaseAuthProvider interface)

        Returns:
            bool: True if authentication successful
        """
        success, _ = await self.authenticate_with_url(return_url=False)
        return success

    async def authenticate_with_url(self, return_url: bool = False) -> tuple[bool, Optional[str]]:
        """Run the OAuth flow with optional URL return

        Args:
            return_url: If True, return the auth URL without opening browser

        Returns:
            Tuple of (success, auth_url)
        """
        logger.info("Starting Google OAuth authentication...")

        # Check if already authenticated with valid tokens
        if await self.check_authentication():
            logger.info("Already authenticated with Google!")
            return True, None

        # If we reach here, either no credentials exist or they're invalid
        logger.info("Need to authenticate with Google...")

        try:
            # Get auth URL and flow objects
            auth_url, flow, state = self.get_auth_url()

            if not auth_url or not flow or not state:
                logger.error("Failed to generate authentication URL")
                return False, None

            logger.info(f"Auth URL: {auth_url}")

            # If only URL is requested, return it without starting server
            if return_url:
                logger.info("Returning auth URL for external handling")
                return False, auth_url

            # Start local server to receive callback
            app = web.Application()
            app["flow"] = flow
            app["state"] = state
            app["auth_complete"] = False
            app["credentials"] = None

            app.router.add_get("/oauth/callback", self._handle_callback)

            runner = web.AppRunner(app)
            await runner.setup()

            site = web.TCPSite(runner, "localhost", self.port)
            await site.start()

            # Open browser
            logger.info("Opening browser for Google authentication...")
            webbrowser.open(auth_url)

            # Wait for callback
            logger.info(f"Waiting for authentication callback on localhost:{self.port}...")

            # Wait for authentication to complete
            timeout = 300  # 5 minutes
            for _ in range(timeout):
                if app["auth_complete"]:
                    break
                await asyncio.sleep(1)
            else:
                logger.error("Authentication timed out after 5 minutes")
                await runner.cleanup()
                return False, auth_url

            await runner.cleanup()

            if app["credentials"]:
                # Store credentials
                await self._store_credentials(app["credentials"])
                logger.info("Google authentication successful!")
                return True, None
            else:
                logger.error("Authentication failed")
                return False, auth_url

        except Exception as e:
            logger.error(f"Error during authentication: {e}")
            return False, None

    async def _handle_callback(self, request: Any) -> Any:
        """Handle OAuth callback"""
        app = request.app

        # Check state parameter
        state = request.query.get("state")
        if state != app["state"]:
            logger.error("Invalid state parameter")
            return web.Response(text="Invalid state parameter", status=400)

        # Check for error
        if "error" in request.query:
            error = request.query.get("error")
            logger.error(f"OAuth error: {error}")
            app["auth_complete"] = True
            return web.Response(text=f"Authentication failed: {error}", status=400)

        # Get authorization code
        code = request.query.get("code")
        if not code:
            app["auth_complete"] = True
            return web.Response(text="No authorization code received", status=400)

        try:
            # Exchange code for credentials
            flow = app["flow"]
            flow.fetch_token(code=code)

            app["credentials"] = flow.credentials
            app["auth_complete"] = True

            return web.Response(
                text="""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Metagen Authentication</title>
                    <style>
                        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; 
                               text-align: center; padding: 50px; background: #f5f5f5; }
                        .success { color: #28a745; font-size: 24px; margin-bottom: 20px; }
                        .message { color: #666; font-size: 16px; }
                    </style>
                </head>
                <body>
                    <div class="success">✅ Authentication Successful!</div>
                    <div class="message">You can now close this window and return to metagen.</div>
                    <script>setTimeout(() => window.close(), 2000);</script>
                </body>
                </html>
            """,
                content_type="text/html",
            )

        except Exception as e:
            logger.error(f"Error exchanging code for token: {e}")
            app["auth_complete"] = True
            return web.Response(text=f"Token exchange failed: {str(e)}", status=500)

    async def _store_credentials(self, credentials: Credentials) -> None:
        """Store credentials to file"""
        token_file = self.get_token_file_path()

        token_data = {
            "access_token": credentials.token,
            "refresh_token": credentials.refresh_token,
            "token_uri": credentials.token_uri,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "scopes": credentials.scopes,
            "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
        }

        # Write to file
        with open(token_file, "w") as f:
            json.dump(token_data, f, indent=2)

        logger.info(f"Credentials stored in: {token_file}")

    async def _test_credentials_async(self, credentials: Credentials) -> dict[str, Any]:
        """Test credentials with a simple API call"""

        def _test_call() -> dict[str, Any]:
            from googleapiclient.discovery import build

            service = build("people", "v1", credentials=credentials)
            # Make a simple API call to test credentials
            result = service.people().get(resourceName="people/me", personFields="names").execute()
            return result  # type: ignore[no-any-return]

        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _test_call)

    async def check_authentication(self) -> bool:
        """Check if user is already authenticated"""
        token_file = self.get_token_file_path()

        if not token_file.exists():
            return False

        try:
            # Load and validate credentials
            with open(token_file, "r") as f:
                token_data = json.load(f)

            credentials = Credentials(
                token=token_data.get("access_token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes"),
            )

            # Try to refresh if needed
            if credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    # Update stored credentials
                    await self._store_credentials(credentials)
                    return True
                except Exception as e:
                    logger.warning(f"Token refresh failed: {e}")
                    # If refresh fails (e.g., token revoked), authentication is invalid
                    logger.info("Removing invalid credentials file")
                    try:
                        token_file.unlink()
                    except Exception:
                        pass
                    return False

            # Even if not expired, test credentials with a simple API call
            if not credentials.expired:
                try:
                    # Make async call to test credentials
                    await self._test_credentials_async(credentials)
                    return True
                except Exception as e:
                    logger.warning(f"Credentials test failed: {e}")
                    # If API call fails, credentials are invalid
                    logger.info("Removing invalid credentials file")
                    try:
                        token_file.unlink()
                    except Exception:
                        pass
                    return False

            return False

        except Exception as e:
            logger.warning(f"Error checking authentication: {e}")
            return False

    async def revoke_authentication(self) -> bool:
        """Revoke stored authentication"""
        token_file = self.get_token_file_path()

        if token_file.exists():
            try:
                token_file.unlink()
                logger.info(f"Removed Google credentials for {self.user_id}")
                return True
            except Exception as e:
                logger.error(f"Error removing credentials: {e}")
                return False
        else:
            logger.info(f"No Google credentials found for {self.user_id}")
            return True

    async def get_user_info(self) -> Optional[dict[str, Any]]:
        """Get basic user information from Google"""
        if not await self.check_authentication():
            return None

        try:
            # Load credentials
            token_file = self.get_token_file_path()
            with open(token_file, "r") as f:
                token_data = json.load(f)

            credentials = Credentials(
                token=token_data.get("access_token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes"),
            )

            # Ensure credentials are fresh before making API call
            if credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                    await self._store_credentials(credentials)
                except Exception as e:
                    logger.error(f"Failed to refresh credentials: {e}")
                    # If refresh fails, credentials are invalid
                    try:
                        token_file.unlink()
                    except Exception:
                        pass
                    return None

            # Use Google People API to get user info
            from googleapiclient.discovery import build

            def _get_user_info() -> tuple[str, str]:
                service = build("people", "v1", credentials=credentials)
                profile = (
                    service.people()
                    .get(resourceName="people/me", personFields="names,emailAddresses")
                    .execute()
                )

                name = ""
                email = ""

                names = profile.get("names", [])
                if names:
                    name = names[0].get("displayName", "")

                emails = profile.get("emailAddresses", [])
                if emails:
                    email = emails[0].get("value", "")

                return (name, email)

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            name, email = await loop.run_in_executor(None, _get_user_info)

            return {"name": name, "email": email, "provider": "google"}

        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            # If getting user info fails, credentials are likely invalid
            token_file = self.get_token_file_path()
            try:
                token_file.unlink()
                logger.info("Removed invalid credentials file")
            except Exception:
                pass
            return None
