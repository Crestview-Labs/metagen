"""Authentication module for metagen - supports multiple SSO providers."""

from .base_auth import BaseAuthProvider
from .google_auth import MetagenGoogleAuth

__all__ = ["MetagenGoogleAuth", "BaseAuthProvider"]
