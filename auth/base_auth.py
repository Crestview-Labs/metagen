"""Base authentication provider interface for metagen."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional


class BaseAuthProvider(ABC):
    """Base class for authentication providers (Google, Microsoft, etc.)"""

    def __init__(self, user_id: str = "default_user"):
        self.user_id = user_id
        self.tokens_dir = Path.home() / ".metagen" / "tokens"
        self.tokens_dir.mkdir(parents=True, exist_ok=True)

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the authentication provider (e.g., 'google', 'microsoft')"""
        pass

    @property
    @abstractmethod
    def scopes(self) -> list:
        """Required OAuth scopes for this provider"""
        pass

    @abstractmethod
    async def authenticate(self) -> bool:
        """Run the OAuth flow and return True if successful"""
        pass

    @abstractmethod
    async def check_authentication(self) -> bool:
        """Check if user is currently authenticated"""
        pass

    @abstractmethod
    async def revoke_authentication(self) -> bool:
        """Revoke stored authentication"""
        pass

    @abstractmethod
    async def get_user_info(self) -> Optional[dict[str, Any]]:
        """Get basic user information (email, name, etc.)"""
        pass

    def get_token_file_path(self) -> Path:
        """Get the path to the token file for this provider"""
        return self.tokens_dir / f"{self.user_id}_{self.provider_name}_token.json"
