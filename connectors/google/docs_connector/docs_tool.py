"""Google Docs tool implementation for MCP server."""

import logging
from typing import Any, Optional

from connectors.google.auth import AsyncGoogleOAuthHandler
from connectors.google.docs_connector.docs_service_async import DocsServiceAsync

logger = logging.getLogger(__name__)


class DocsConnectorTool:
    """Tool for interacting with Google Docs API."""

    def __init__(self, oauth_handler: Optional[AsyncGoogleOAuthHandler] = None):
        """Initialize the Google Docs connector tool.

        Args:
            oauth_handler: OAuth handler for authentication
        """
        self.oauth_handler = oauth_handler or AsyncGoogleOAuthHandler()
        self.docs_service = DocsServiceAsync(oauth_handler)
        logger.debug("Initialized DocsConnectorTool")

    async def is_authenticated(self, user_id: str = "default_user") -> bool:
        """Check if user is authenticated for Google Docs."""
        try:
            credentials = await self.oauth_handler.load_credentials(user_id)
            return credentials is not None
        except Exception as e:
            logger.error(f"Error checking authentication status: {str(e)}")
            return False

    async def get_document(self, user_id: str, document_id: str) -> dict[str, Any]:
        """
        Get a Google Docs document by ID.

        Args:
            user_id: User identifier for credentials
            document_id: The Google Docs document ID

        Returns:
            Dictionary containing document data
        """
        logger.info(f"Getting document {document_id} for user {user_id}")

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "document_id": document_id,
                "document": None,
            }

        try:
            return await self.docs_service.get_document(document_id, user_id)
        except Exception as e:
            logger.error(f"Error getting document {document_id}: {str(e)}")
            return {"success": False, "error": str(e), "document_id": document_id, "document": None}

    async def create_document(self, user_id: str, title: str) -> dict[str, Any]:
        """
        Create a new Google Docs document.

        Args:
            user_id: User identifier for credentials
            title: Title for the new document

        Returns:
            Dictionary containing created document data
        """
        logger.info(f"Creating document '{title}' for user {user_id}")

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "title": title,
                "document": None,
            }

        try:
            return await self.docs_service.create_document(title, user_id)
        except Exception as e:
            logger.error(f"Error creating document '{title}': {str(e)}")
            return {"success": False, "error": str(e), "title": title, "document": None}

    async def get_document_content(self, user_id: str, document_id: str) -> dict[str, Any]:
        """
        Get the text content of a Google Docs document.

        Args:
            user_id: User identifier for credentials
            document_id: The Google Docs document ID

        Returns:
            Dictionary containing document text content
        """
        logger.info(f"Getting content from document {document_id} for user {user_id}")

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "document_id": document_id,
                "text_content": "",
            }

        try:
            return await self.docs_service.get_document_content(document_id, user_id)
        except Exception as e:
            logger.error(f"Error getting content from document {document_id}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "document_id": document_id,
                "text_content": "",
            }

    async def insert_text(
        self, user_id: str, document_id: str, text: str, index: int = 1
    ) -> dict[str, Any]:
        """
        Insert text into a Google Docs document.

        Args:
            user_id: User identifier for credentials
            document_id: The Google Docs document ID
            text: Text to insert
            index: Location to insert text (default: 1, beginning of document)

        Returns:
            Dictionary containing insert results
        """
        logger.info(
            f"Inserting text into document {document_id} at index {index} for user {user_id}"
        )

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "document_id": document_id,
            }

        try:
            return await self.docs_service.insert_text(document_id, text, index, user_id)
        except Exception as e:
            logger.error(f"Error inserting text into document {document_id}: {str(e)}")
            return {"success": False, "error": str(e), "document_id": document_id}

    async def replace_text(
        self, user_id: str, document_id: str, find_text: str, replace_text: str
    ) -> dict[str, Any]:
        """
        Replace all occurrences of text in a Google Docs document.

        Args:
            user_id: User identifier for credentials
            document_id: The Google Docs document ID
            find_text: Text to find and replace
            replace_text: Text to replace with

        Returns:
            Dictionary containing replace results
        """
        logger.info(
            f"Replacing text in document {document_id}: '{find_text}' -> "
            f"'{replace_text}' for user {user_id}"
        )

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "document_id": document_id,
            }

        try:
            return await self.docs_service.replace_text(
                document_id, find_text, replace_text, user_id
            )
        except Exception as e:
            logger.error(f"Error replacing text in document {document_id}: {str(e)}")
            return {"success": False, "error": str(e), "document_id": document_id}
