"""Authentication-related API models."""

from typing import Optional

from pydantic import BaseModel


class AuthStatus(BaseModel):
    """Authentication status response."""

    authenticated: bool
    user_info: Optional[dict[str, str]] = None
    services: list[str] = []
    provider: Optional[str] = None


class AuthLoginRequest(BaseModel):
    """Authentication login request."""

    force: Optional[bool] = False


class AuthResponse(BaseModel):
    """Authentication operation response."""

    success: bool
    message: str
    auth_url: Optional[str] = None  # For OAuth flow initiation
    status: Optional[AuthStatus] = None
