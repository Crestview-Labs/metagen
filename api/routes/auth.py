"""Authentication API routes."""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from auth.google_auth import MetagenGoogleAuth

from ..models.auth import AuthLoginRequest, AuthResponse, AuthStatus

logger = logging.getLogger(__name__)

auth_router = APIRouter()


@auth_router.get("/auth/status", response_model=AuthStatus)
async def get_auth_status() -> AuthStatus:
    """Get current authentication status."""
    try:
        logger.info("🔐 Checking authentication status...")

        # Create Google auth instance
        google_auth = MetagenGoogleAuth()

        # Check authentication
        is_authenticated = await google_auth.check_authentication()

        status = AuthStatus(
            authenticated=is_authenticated,
            provider="google" if is_authenticated else None,
            services=["gmail", "drive", "calendar"] if is_authenticated else [],
        )

        if is_authenticated:
            # Get user info
            user_info = await google_auth.get_user_info()
            if user_info:
                status.user_info = user_info

        logger.info(f"🔐 Authentication status: {is_authenticated}")
        return status

    except Exception as e:
        logger.error(f"❌ Auth status error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to check authentication: {str(e)}")


@auth_router.post("/auth/login", response_model=AuthResponse)
async def login(request: AuthLoginRequest = AuthLoginRequest()) -> AuthResponse:
    """Initiate Google OAuth login flow."""
    try:
        logger.info(f"🔐 Starting OAuth login flow... (force={request.force})")

        # Create Google auth instance
        google_auth = MetagenGoogleAuth()

        # Check if we should force authentication or if we're already authenticated
        if request.force:
            # Force re-authentication by removing existing credentials
            await google_auth.revoke_authentication()
            is_authenticated = False
        else:
            is_authenticated = await google_auth.check_authentication()

        if is_authenticated:
            # Already authenticated, no need to start OAuth flow
            success = True
            auth_url = None
        else:
            # Need to authenticate - get the auth URL
            auth_url, _, _ = google_auth.get_auth_url()
            success = False

            if auth_url:
                # Start the OAuth server in the background
                # This will open the browser and handle the callback
                asyncio.create_task(google_auth.authenticate_with_url(return_url=False))

        if success:
            # Get user info
            user_info = await google_auth.get_user_info()

            return AuthResponse(
                success=True,
                message="Authentication successful",
                status=AuthStatus(
                    authenticated=True,
                    provider="google",
                    services=["gmail", "drive", "calendar"],
                    user_info=user_info,
                ),
                auth_url=None,  # Already authenticated, no URL needed
            )
        else:
            # Need to authenticate - return the auth URL
            if auth_url:
                return AuthResponse(
                    success=False,
                    message="Please complete authentication in your browser",
                    auth_url=auth_url,
                    status=AuthStatus(authenticated=False, provider=None, services=[]),
                )
            else:
                return AuthResponse(
                    success=False,
                    message="Failed to generate authentication URL",
                    auth_url=None,
                    status=AuthStatus(authenticated=False, provider=None, services=[]),
                )

    except FileNotFoundError as e:
        logger.error(f"❌ Auth setup error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Auth login error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@auth_router.post("/auth/logout", response_model=AuthResponse)
async def logout() -> AuthResponse:
    """Logout and revoke authentication."""
    try:
        logger.info("🔐 Logging out...")

        # Create Google auth instance
        google_auth = MetagenGoogleAuth()

        # Revoke authentication
        success = await google_auth.revoke_authentication()

        return AuthResponse(
            success=success,
            message="Logout successful" if success else "Logout failed",
            status=AuthStatus(authenticated=False, provider=None, services=[]),
        )

    except Exception as e:
        logger.error(f"❌ Auth logout error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Logout failed: {str(e)}")
