"""Google Sheets tool implementation for MCP server."""

import logging
from typing import Any, Optional

from connectors.google.auth import AsyncGoogleOAuthHandler
from connectors.google.sheets_connector.sheets_service_async import SheetsServiceAsync

logger = logging.getLogger(__name__)


class SheetsConnectorTool:
    """Tool for interacting with Google Sheets API."""

    def __init__(self, oauth_handler: Optional[AsyncGoogleOAuthHandler] = None):
        """Initialize the Google Sheets connector tool.

        Args:
            oauth_handler: OAuth handler for authentication
        """
        self.oauth_handler = oauth_handler or AsyncGoogleOAuthHandler()
        self.sheets_service = SheetsServiceAsync(oauth_handler)
        logger.debug("Initialized SheetsConnectorTool")

    async def is_authenticated(self, user_id: str = "default_user") -> bool:
        """Check if user is authenticated for Google Sheets."""
        try:
            credentials = await self.oauth_handler.load_credentials(user_id)
            return credentials is not None
        except Exception as e:
            logger.error(f"Error checking authentication status: {str(e)}")
            return False

    async def get_spreadsheet(self, user_id: str, spreadsheet_id: str) -> dict[str, Any]:
        """
        Get a Google Sheets spreadsheet by ID.

        Args:
            user_id: User identifier for credentials
            spreadsheet_id: The Google Sheets spreadsheet ID

        Returns:
            Dictionary containing spreadsheet data
        """
        logger.info(f"Getting spreadsheet {spreadsheet_id} for user {user_id}")

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "spreadsheet_id": spreadsheet_id,
                "spreadsheet": None,
            }

        try:
            return await self.sheets_service.get_spreadsheet(spreadsheet_id, user_id)
        except Exception as e:
            logger.error(f"Error getting spreadsheet {spreadsheet_id}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "spreadsheet_id": spreadsheet_id,
                "spreadsheet": None,
            }

    async def create_spreadsheet(self, user_id: str, title: str) -> dict[str, Any]:
        """
        Create a new Google Sheets spreadsheet.

        Args:
            user_id: User identifier for credentials
            title: Title for the new spreadsheet

        Returns:
            Dictionary containing created spreadsheet data
        """
        logger.info(f"Creating spreadsheet '{title}' for user {user_id}")

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "title": title,
                "spreadsheet": None,
            }

        try:
            return await self.sheets_service.create_spreadsheet(title, user_id)
        except Exception as e:
            logger.error(f"Error creating spreadsheet '{title}': {str(e)}")
            return {"success": False, "error": str(e), "title": title, "spreadsheet": None}

    async def get_values(
        self, user_id: str, spreadsheet_id: str, range_name: str
    ) -> dict[str, Any]:
        """
        Get values from a Google Sheets spreadsheet range.

        Args:
            user_id: User identifier for credentials
            spreadsheet_id: The Google Sheets spreadsheet ID
            range_name: The range to retrieve (e.g., "Sheet1!A1:D10")

        Returns:
            Dictionary containing range values
        """
        logger.info(
            f"Getting values from spreadsheet {spreadsheet_id} range {range_name} "
            f"for user {user_id}"
        )

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
                "values": [],
            }

        try:
            return await self.sheets_service.get_values(spreadsheet_id, range_name, user_id)
        except Exception as e:
            logger.error(
                f"Error getting values from spreadsheet {spreadsheet_id} "
                f"range {range_name}: {str(e)}"
            )
            return {
                "success": False,
                "error": str(e),
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
                "values": [],
            }

    async def update_values(
        self, user_id: str, spreadsheet_id: str, range_name: str, values: list[list[str]]
    ) -> dict[str, Any]:
        """
        Update values in a Google Sheets spreadsheet range.

        Args:
            user_id: User identifier for credentials
            spreadsheet_id: The Google Sheets spreadsheet ID
            range_name: The range to update (e.g., "Sheet1!A1:D10")
            values: 2D array of values to update

        Returns:
            Dictionary containing update results
        """
        logger.info(
            f"Updating values in spreadsheet {spreadsheet_id} range {range_name} for user {user_id}"
        )

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
            }

        try:
            return await self.sheets_service.update_values(
                spreadsheet_id, range_name, values, user_id
            )
        except Exception as e:
            logger.error(
                f"Error updating values in spreadsheet {spreadsheet_id} "
                f"range {range_name}: {str(e)}"
            )
            return {
                "success": False,
                "error": str(e),
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
            }

    async def append_values(
        self, user_id: str, spreadsheet_id: str, range_name: str, values: list[list[str]]
    ) -> dict[str, Any]:
        """
        Append values to a Google Sheets spreadsheet.

        Args:
            user_id: User identifier for credentials
            spreadsheet_id: The Google Sheets spreadsheet ID
            range_name: The range to append to (e.g., "Sheet1!A1:D1")
            values: 2D array of values to append

        Returns:
            Dictionary containing append results
        """
        logger.info(
            f"Appending values to spreadsheet {spreadsheet_id} range {range_name} "
            f"for user {user_id}"
        )

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
            }

        try:
            return await self.sheets_service.append_values(
                spreadsheet_id, range_name, values, user_id
            )
        except Exception as e:
            logger.error(
                f"Error appending values to spreadsheet {spreadsheet_id} "
                f"range {range_name}: {str(e)}"
            )
            return {
                "success": False,
                "error": str(e),
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
            }

    async def create_sheet(
        self, user_id: str, spreadsheet_id: str, sheet_title: str
    ) -> dict[str, Any]:
        """
        Create a new sheet in a Google Sheets spreadsheet.

        Args:
            user_id: User identifier for credentials
            spreadsheet_id: The Google Sheets spreadsheet ID
            sheet_title: Title for the new sheet

        Returns:
            Dictionary containing created sheet data
        """
        logger.info(
            f"Creating sheet '{sheet_title}' in spreadsheet {spreadsheet_id} for user {user_id}"
        )

        if not await self.is_authenticated(user_id):
            return {
                "success": False,
                "error": (
                    f"User {user_id} is not authenticated with Google. Please authenticate first."
                ),
                "spreadsheet_id": spreadsheet_id,
                "sheet_title": sheet_title,
            }

        try:
            return await self.sheets_service.create_sheet(spreadsheet_id, sheet_title, user_id)
        except Exception as e:
            logger.error(
                f"Error creating sheet '{sheet_title}' in spreadsheet {spreadsheet_id}: {str(e)}"
            )
            return {
                "success": False,
                "error": str(e),
                "spreadsheet_id": spreadsheet_id,
                "sheet_title": sheet_title,
            }
