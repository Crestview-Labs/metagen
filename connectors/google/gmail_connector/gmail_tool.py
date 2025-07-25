"""
Gmail Connector Tool - MCP-compatible tool for Gmail operations
"""

from typing import Any, Optional

from connectors.google.auth import AsyncGoogleOAuthHandler

from .gmail_service_async import AsyncGmailService


class GmailConnectorTool:
    """
    MCP-compatible Gmail connector tool for searching and managing emails.

    This tool provides methods to:
    - Search emails with Gmail query syntax
    - Get individual email details
    - List Gmail labels
    - Get user profile information
    """

    def __init__(self, oauth_handler: Optional[AsyncGoogleOAuthHandler] = None):
        self.oauth_handler = oauth_handler or AsyncGoogleOAuthHandler()
        self.gmail_service = AsyncGmailService(self.oauth_handler)
        self.name = "gmail_connector"
        self.description = "Search and access Gmail emails"

    async def search_emails(
        self, user_id: str = "default_user", query: str = "", max_results: int = 10
    ) -> dict[str, Any]:
        """
        Search Gmail emails using Gmail query syntax.

        Args:
            user_id: User identifier (default: "default_user")
            query: Gmail search query (e.g., "from:john@example.com", "subject:invoice")
            max_results: Maximum number of emails to return (default: 10)

        Returns:
            Dict containing count and list of matching emails
        """
        try:
            return await self.gmail_service.search_messages(user_id, query, max_results)
        except Exception as e:
            return {"error": str(e), "count": 0, "messages": []}

    async def get_email(
        self, user_id: str = "default_user", message_id: str = ""
    ) -> dict[str, Any]:
        """
        Get detailed information about a specific email.

        Args:
            user_id: User identifier (default: "default_user")
            message_id: Gmail message ID

        Returns:
            Dict containing email details including full body
        """
        try:
            return await self.gmail_service.get_message(user_id, message_id)
        except Exception as e:
            return {"error": str(e)}

    async def get_labels(self, user_id: str = "default_user") -> dict[str, Any]:
        """
        Get all Gmail labels for the user.

        Args:
            user_id: User identifier (default: "default_user")

        Returns:
            Dict containing list of labels
        """
        try:
            labels = await self.gmail_service.get_labels(user_id)
            return {"labels": labels}
        except Exception as e:
            return {"error": str(e), "labels": []}

    async def get_profile(self, user_id: str = "default_user") -> dict[str, Any]:
        """
        Get Gmail profile information for the user.

        Args:
            user_id: User identifier (default: "default_user")

        Returns:
            Dict containing profile information
        """
        # Don't catch exceptions here - let them propagate to the caller
        # so the auth_status endpoint can handle token expiration properly
        return await self.gmail_service.get_profile(user_id)

    async def is_authenticated(self, user_id: str = "default_user") -> bool:
        """
        Check if the user is authenticated with Gmail.

        Args:
            user_id: User identifier (default: "default_user")

        Returns:
            True if authenticated, False otherwise
        """
        try:
            credentials = await self.oauth_handler.load_credentials(user_id)
            return credentials is not None
        except Exception:
            return False

    def get_tool_definition(self) -> dict[str, Any]:
        """
        Get MCP-compatible tool definition.

        Returns:
            Tool definition dict for MCP registration
        """
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["search", "get_email", "get_labels", "get_profile", "check_auth"],
                        "description": "Action to perform",
                    },
                    "user_id": {
                        "type": "string",
                        "default": "default_user",
                        "description": "User identifier",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query for Gmail (required for search action)",
                    },
                    "message_id": {
                        "type": "string",
                        "description": "Gmail message ID (required for get_email action)",
                    },
                    "max_results": {
                        "type": "integer",
                        "default": 10,
                        "description": "Maximum results to return for search",
                    },
                },
                "required": ["action"],
            },
        }

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        """
        Execute tool action based on parameters.

        Args:
            **kwargs: Action parameters

        Returns:
            Result of the requested action
        """
        action = kwargs.get("action")
        user_id = kwargs.get("user_id", "default_user")

        if action == "search":
            query = kwargs.get("query", "")
            max_results = kwargs.get("max_results", 10)
            return await self.search_emails(user_id, query, max_results)

        elif action == "get_email":
            message_id = kwargs.get("message_id", "")
            if not message_id:
                return {"error": "message_id is required for get_email action"}
            return await self.get_email(user_id, message_id)

        elif action == "get_labels":
            return await self.get_labels(user_id)

        elif action == "get_profile":
            return await self.get_profile(user_id)

        elif action == "check_auth":
            is_auth = await self.is_authenticated(user_id)
            return {"authenticated": is_auth}

        else:
            return {"error": f"Unknown action: {action}"}
