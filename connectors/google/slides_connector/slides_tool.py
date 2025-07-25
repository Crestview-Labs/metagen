"""Google Slides tool implementation for MCP server."""

import logging
from typing import Any, Optional

from connectors.google.auth import AsyncGoogleOAuthHandler
from connectors.google.slides_connector.slides_service_async import SlidesServiceAsync

logger = logging.getLogger(__name__)


class SlidesConnectorTool:
    """Tool for interacting with Google Slides API."""

    def __init__(self, oauth_handler: Optional[AsyncGoogleOAuthHandler] = None):
        """Initialize the Google Slides connector tool.

        Args:
            oauth_handler: OAuth handler for authentication
        """
        self.oauth_handler = oauth_handler or AsyncGoogleOAuthHandler()
        self.slides_service = SlidesServiceAsync(oauth_handler)
        logger.debug("Initialized SlidesConnectorTool")

    async def is_authenticated(self, user_id: str = "default_user") -> bool:
        """Check if user is authenticated for Google Slides."""
        try:
            credentials = await self.oauth_handler.load_credentials(user_id)
            return credentials is not None
        except Exception as e:
            logger.error(f"Error checking authentication status: {str(e)}")
            return False

    async def get_presentation(self, user_id: str, presentation_id: str) -> dict[str, Any]:
        """
        Get a Google Slides presentation by ID.

        Args:
            user_id: User identifier for credentials
            presentation_id: The Google Slides presentation ID

        Returns:
            Dictionary containing presentation data
        """
        logger.info(f"Getting presentation {presentation_id} for user {user_id}")

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "presentation_id": presentation_id,
                "presentation": None,
            }

        try:
            return await self.slides_service.get_presentation(presentation_id, user_id)
        except Exception as e:
            logger.error(f"Error getting presentation {presentation_id}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "presentation_id": presentation_id,
                "presentation": None,
            }

    async def create_presentation(self, user_id: str, title: str) -> dict[str, Any]:
        """
        Create a new Google Slides presentation.

        Args:
            user_id: User identifier for credentials
            title: Title for the new presentation

        Returns:
            Dictionary containing created presentation data
        """
        logger.info(f"Creating presentation '{title}' for user {user_id}")

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "title": title,
                "presentation": None,
            }

        try:
            return await self.slides_service.create_presentation(title, user_id)
        except Exception as e:
            logger.error(f"Error creating presentation '{title}': {str(e)}")
            return {"success": False, "error": str(e), "title": title, "presentation": None}

    async def create_slide(
        self, user_id: str, presentation_id: str, slide_layout_reference: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Create a new slide in a Google Slides presentation.

        Args:
            user_id: User identifier for credentials
            presentation_id: The Google Slides presentation ID
            slide_layout_reference: Layout reference for the slide (optional)

        Returns:
            Dictionary containing created slide data
        """
        logger.info(f"Creating slide in presentation {presentation_id} for user {user_id}")

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "presentation_id": presentation_id,
            }

        try:
            return await self.slides_service.create_slide(
                presentation_id, slide_layout_reference, user_id
            )
        except Exception as e:
            logger.error(f"Error creating slide in presentation {presentation_id}: {str(e)}")
            return {"success": False, "error": str(e), "presentation_id": presentation_id}

    async def add_text_to_slide(
        self, user_id: str, presentation_id: str, slide_id: str, text: str
    ) -> dict[str, Any]:
        """
        Add text to a slide in a Google Slides presentation.

        Args:
            user_id: User identifier for credentials
            presentation_id: The Google Slides presentation ID
            slide_id: The slide ID to add text to
            text: Text to add

        Returns:
            Dictionary containing text addition results
        """
        logger.info(
            f"Adding text to slide {slide_id} in presentation {presentation_id} for user {user_id}"
        )

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "presentation_id": presentation_id,
                "slide_id": slide_id,
            }

        try:
            return await self.slides_service.add_text_to_slide(
                presentation_id, slide_id, text, user_id
            )
        except Exception as e:
            logger.error(
                f"Error adding text to slide {slide_id} in presentation {presentation_id}: {str(e)}"
            )
            return {
                "success": False,
                "error": str(e),
                "presentation_id": presentation_id,
                "slide_id": slide_id,
            }

    async def replace_text_in_presentation(
        self, user_id: str, presentation_id: str, find_text: str, replace_text: str
    ) -> dict[str, Any]:
        """
        Replace all occurrences of text in a Google Slides presentation.

        Args:
            user_id: User identifier for credentials
            presentation_id: The Google Slides presentation ID
            find_text: Text to find and replace
            replace_text: Text to replace with

        Returns:
            Dictionary containing replace results
        """
        logger.info(
            f"Replacing text in presentation {presentation_id}: '{find_text}' -> "
            f"'{replace_text}' for user {user_id}"
        )

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "presentation_id": presentation_id,
            }

        try:
            return await self.slides_service.replace_text_in_presentation(
                presentation_id, find_text, replace_text, user_id
            )
        except Exception as e:
            logger.error(f"Error replacing text in presentation {presentation_id}: {str(e)}")
            return {"success": False, "error": str(e), "presentation_id": presentation_id}

    async def duplicate_slide(
        self, user_id: str, presentation_id: str, slide_id: str
    ) -> dict[str, Any]:
        """
        Duplicate a slide in a Google Slides presentation.

        Args:
            user_id: User identifier for credentials
            presentation_id: The Google Slides presentation ID
            slide_id: The slide ID to duplicate

        Returns:
            Dictionary containing duplication results
        """
        logger.info(
            f"Duplicating slide {slide_id} in presentation {presentation_id} for user {user_id}"
        )

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "presentation_id": presentation_id,
                "slide_id": slide_id,
            }

        try:
            return await self.slides_service.duplicate_slide(presentation_id, slide_id, user_id)
        except Exception as e:
            logger.error(
                f"Error duplicating slide {slide_id} in presentation {presentation_id}: {str(e)}"
            )
            return {
                "success": False,
                "error": str(e),
                "presentation_id": presentation_id,
                "slide_id": slide_id,
            }

    async def delete_slide(
        self, user_id: str, presentation_id: str, slide_id: str
    ) -> dict[str, Any]:
        """
        Delete a slide from a Google Slides presentation.

        Args:
            user_id: User identifier for credentials
            presentation_id: The Google Slides presentation ID
            slide_id: The slide ID to delete

        Returns:
            Dictionary containing deletion results
        """
        logger.info(
            f"Deleting slide {slide_id} from presentation {presentation_id} for user {user_id}"
        )

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "presentation_id": presentation_id,
                "slide_id": slide_id,
            }

        try:
            return await self.slides_service.delete_slide(presentation_id, slide_id, user_id)
        except Exception as e:
            logger.error(
                f"Error deleting slide {slide_id} from presentation {presentation_id}: {str(e)}"
            )
            return {
                "success": False,
                "error": str(e),
                "presentation_id": presentation_id,
                "slide_id": slide_id,
            }
