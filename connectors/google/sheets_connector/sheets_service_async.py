"""Async Google Sheets service implementation."""

import logging
from typing import Any

from connectors.google.base_service import BaseGoogleService

logger = logging.getLogger(__name__)


class SheetsServiceAsync(BaseGoogleService):
    """Async Google Sheets service implementation."""

    @property
    def service_name(self) -> str:
        return "sheets"

    @property
    def service_version(self) -> str:
        return "v4"

    async def get_spreadsheet(
        self, spreadsheet_id: str, user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Get a Google Sheets spreadsheet by ID.

        Args:
            spreadsheet_id: The Google Sheets spreadsheet ID
            user_id: User identifier for credentials

        Returns:
            Dictionary containing spreadsheet data
        """
        logger.info(f"Getting spreadsheet {spreadsheet_id} for user {user_id}")

        try:

            def _get_spreadsheet(service: Any) -> Any:
                return service.spreadsheets().get(spreadsheetId=spreadsheet_id)

            result = await self._execute_request(_get_spreadsheet, user_id)

            return {
                "success": True,
                "spreadsheet": result,
                "spreadsheet_id": spreadsheet_id,
                "title": result.get("properties", {}).get("title", ""),
                "sheets": result.get("sheets", []),
                "spreadsheet_url": result.get("spreadsheetUrl", ""),
            }

        except Exception as e:
            logger.error(f"Error getting spreadsheet {spreadsheet_id}: {str(e)}")
            return self._format_error_response(
                e, {"success": False, "spreadsheet_id": spreadsheet_id, "spreadsheet": None}
            )

    async def create_spreadsheet(self, title: str, user_id: str = "default_user") -> dict[str, Any]:
        """
        Create a new Google Sheets spreadsheet.

        Args:
            title: Title for the new spreadsheet
            user_id: User identifier for credentials

        Returns:
            Dictionary containing created spreadsheet data
        """
        logger.info(f"Creating spreadsheet '{title}' for user {user_id}")

        try:

            def _create_spreadsheet(service: Any) -> Any:
                return service.spreadsheets().create(body={"properties": {"title": title}})

            result = await self._execute_request(_create_spreadsheet, user_id)

            return {
                "success": True,
                "spreadsheet": result,
                "spreadsheet_id": result.get("spreadsheetId", ""),
                "title": result.get("properties", {}).get("title", ""),
                "spreadsheet_url": result.get("spreadsheetUrl", ""),
            }

        except Exception as e:
            logger.error(f"Error creating spreadsheet '{title}': {str(e)}")
            return self._format_error_response(
                e, {"success": False, "title": title, "spreadsheet": None}
            )

    async def get_values(
        self, spreadsheet_id: str, range_name: str, user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Get values from a Google Sheets spreadsheet range.

        Args:
            spreadsheet_id: The Google Sheets spreadsheet ID
            range_name: The range to retrieve (e.g., "Sheet1!A1:D10")
            user_id: User identifier for credentials

        Returns:
            Dictionary containing range values
        """
        logger.info(
            f"Getting values from spreadsheet {spreadsheet_id} range {range_name} "
            f"for user {user_id}"
        )

        try:

            def _get_values(service: Any) -> Any:
                return (
                    service.spreadsheets()
                    .values()
                    .get(spreadsheetId=spreadsheet_id, range=range_name)
                )

            result = await self._execute_request(_get_values, user_id)

            return {
                "success": True,
                "spreadsheet_id": spreadsheet_id,
                "range": result.get("range", ""),
                "major_dimension": result.get("majorDimension", ""),
                "values": result.get("values", []),
                "row_count": len(result.get("values", [])),
                "column_count": len(result.get("values", [None])[0]) if result.get("values") else 0,
            }

        except Exception as e:
            logger.error(
                f"Error getting values from spreadsheet {spreadsheet_id} "
                f"range {range_name}: {str(e)}"
            )
            return self._format_error_response(
                e,
                {
                    "success": False,
                    "spreadsheet_id": spreadsheet_id,
                    "range": range_name,
                    "values": [],
                },
            )

    async def update_values(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: list[list[str]],
        user_id: str = "default_user",
    ) -> dict[str, Any]:
        """
        Update values in a Google Sheets spreadsheet range.

        Args:
            spreadsheet_id: The Google Sheets spreadsheet ID
            range_name: The range to update (e.g., "Sheet1!A1:D10")
            values: 2D array of values to update
            user_id: User identifier for credentials

        Returns:
            Dictionary containing update results
        """
        logger.info(
            f"Updating values in spreadsheet {spreadsheet_id} range {range_name} for user {user_id}"
        )

        try:

            def _update_values(service: Any) -> Any:
                return (
                    service.spreadsheets()
                    .values()
                    .update(
                        spreadsheetId=spreadsheet_id,
                        range=range_name,
                        valueInputOption="USER_ENTERED",
                        body={"values": values},
                    )
                )

            result = await self._execute_request(_update_values, user_id)

            return {
                "success": True,
                "spreadsheet_id": spreadsheet_id,
                "updated_range": result.get("updatedRange", ""),
                "updated_rows": result.get("updatedRows", 0),
                "updated_columns": result.get("updatedColumns", 0),
                "updated_cells": result.get("updatedCells", 0),
            }

        except Exception as e:
            logger.error(
                f"Error updating values in spreadsheet {spreadsheet_id} "
                f"range {range_name}: {str(e)}"
            )
            return self._format_error_response(
                e, {"success": False, "spreadsheet_id": spreadsheet_id, "range": range_name}
            )

    async def append_values(
        self,
        spreadsheet_id: str,
        range_name: str,
        values: list[list[str]],
        user_id: str = "default_user",
    ) -> dict[str, Any]:
        """
        Append values to a Google Sheets spreadsheet.

        Args:
            spreadsheet_id: The Google Sheets spreadsheet ID
            range_name: The range to append to (e.g., "Sheet1!A1:D1")
            values: 2D array of values to append
            user_id: User identifier for credentials

        Returns:
            Dictionary containing append results
        """
        logger.info(
            f"Appending values to spreadsheet {spreadsheet_id} range {range_name} "
            f"for user {user_id}"
        )

        try:

            def _append_values(service: Any) -> Any:
                return (
                    service.spreadsheets()
                    .values()
                    .append(
                        spreadsheetId=spreadsheet_id,
                        range=range_name,
                        valueInputOption="USER_ENTERED",
                        body={"values": values},
                    )
                )

            result = await self._execute_request(_append_values, user_id)

            return {
                "success": True,
                "spreadsheet_id": spreadsheet_id,
                "table_range": result.get("tableRange", ""),
                "updates": result.get("updates", {}),
                "updated_rows": result.get("updates", {}).get("updatedRows", 0),
                "updated_columns": result.get("updates", {}).get("updatedColumns", 0),
                "updated_cells": result.get("updates", {}).get("updatedCells", 0),
            }

        except Exception as e:
            logger.error(
                f"Error appending values to spreadsheet {spreadsheet_id} "
                f"range {range_name}: {str(e)}"
            )
            return self._format_error_response(
                e, {"success": False, "spreadsheet_id": spreadsheet_id, "range": range_name}
            )

    async def batch_update_spreadsheet(
        self, spreadsheet_id: str, requests: list[dict[str, Any]], user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Apply batch updates to a Google Sheets spreadsheet.

        Args:
            spreadsheet_id: The Google Sheets spreadsheet ID
            requests: List of update requests
            user_id: User identifier for credentials

        Returns:
            Dictionary containing batch update results
        """
        logger.info(
            f"Batch updating spreadsheet {spreadsheet_id} with {len(requests)} requests "
            f"for user {user_id}"
        )

        try:

            def _batch_update(service: Any) -> Any:
                return service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id, body={"requests": requests}
                )

            result = await self._execute_request(_batch_update, user_id)

            return {
                "success": True,
                "spreadsheet_id": spreadsheet_id,
                "spreadsheet_id_result": result.get("spreadsheetId", ""),
                "replies": result.get("replies", []),
                "updated_spreadsheet": result.get("updatedSpreadsheet", {}),
            }

        except Exception as e:
            logger.error(f"Error batch updating spreadsheet {spreadsheet_id}: {str(e)}")
            return self._format_error_response(
                e, {"success": False, "spreadsheet_id": spreadsheet_id, "requests": requests}
            )

    async def create_sheet(
        self, spreadsheet_id: str, sheet_title: str, user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Create a new sheet in a Google Sheets spreadsheet.

        Args:
            spreadsheet_id: The Google Sheets spreadsheet ID
            sheet_title: Title for the new sheet
            user_id: User identifier for credentials

        Returns:
            Dictionary containing created sheet data
        """
        logger.info(
            f"Creating sheet '{sheet_title}' in spreadsheet {spreadsheet_id} for user {user_id}"
        )

        requests = [{"addSheet": {"properties": {"title": sheet_title}}}]

        result = await self.batch_update_spreadsheet(spreadsheet_id, requests, user_id)

        if result.get("success", False):
            # Extract sheet info from reply
            replies = result.get("replies", [])
            if replies and "addSheet" in replies[0]:
                sheet_info = replies[0]["addSheet"]
                result["sheet_id"] = sheet_info.get("properties", {}).get("sheetId", "")
                result["sheet_title"] = sheet_info.get("properties", {}).get("title", "")

        return result
