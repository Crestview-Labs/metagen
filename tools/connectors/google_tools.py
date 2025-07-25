"""MCP tool wrappers for Google service connectors."""

import logging
from typing import Any, Optional

from connectors.google.auth import AsyncGoogleOAuthHandler
from connectors.google.drive_connector.drive_tool import DriveConnectorTool
from connectors.google.gcal_connector.gcal_tool import GCalConnectorTool
from connectors.google.gmail_connector.gmail_tool import GmailConnectorTool

logger = logging.getLogger(__name__)


class GoogleToolsWrapper:
    """Wrapper to expose Google connectors as MCP tools."""

    def __init__(self, oauth_handler: Optional[AsyncGoogleOAuthHandler] = None):
        """Initialize with OAuth handler (can be set later)."""
        self.oauth_handler = oauth_handler
        self._gmail_tool: Optional[GmailConnectorTool] = None
        self._drive_tool: Optional[DriveConnectorTool] = None
        self._gcal_tool: Optional[GCalConnectorTool] = None

    async def initialize(self, oauth_handler: Optional[AsyncGoogleOAuthHandler] = None) -> None:
        """Initialize the tools with OAuth handler."""
        if oauth_handler:
            self.oauth_handler = oauth_handler

        if not self.oauth_handler:
            raise ValueError("OAuth handler required for Google tools")

        # Initialize individual tools
        self._gmail_tool = GmailConnectorTool(self.oauth_handler)
        self._drive_tool = DriveConnectorTool(self.oauth_handler)
        self._gcal_tool = GCalConnectorTool(self.oauth_handler)

    # Gmail Tools
    async def gmail_search(
        self,
        query: str,
        max_results: int = 10,
        include_body: bool = False,
        page_token: Optional[str] = None,
    ) -> dict[str, Any]:
        """Search Gmail messages."""
        if not self._gmail_tool:
            raise RuntimeError("Gmail tool not initialized")

        return await self._gmail_tool.search_emails(
            user_id="default_user", query=query or "", max_results=max_results
        )

    async def gmail_get_message(self, message_id: str, format: str = "full") -> dict[str, Any]:
        """Get a specific Gmail message."""
        if not self._gmail_tool:
            raise RuntimeError("Gmail tool not initialized")

        return await self._gmail_tool.get_email(user_id="default_user", message_id=message_id)

    async def gmail_list_labels(self) -> dict[str, Any]:
        """List Gmail labels."""
        if not self._gmail_tool:
            raise RuntimeError("Gmail tool not initialized")

        return await self._gmail_tool.get_labels(user_id="default_user")

    # Drive Tools
    async def drive_search_files(
        self,
        query: Optional[str] = None,
        max_results: int = 10,
        page_token: Optional[str] = None,
        order_by: Optional[str] = None,
        user_id: str = "default_user",
    ) -> dict[str, Any]:
        """Search Google Drive files."""
        if not self._drive_tool:
            raise RuntimeError("Drive tool not initialized")

        # DriveConnectorTool.search_files expects: user_id, query, max_results
        # It doesn't support page_token or order_by
        return await self._drive_tool.search_files(
            user_id=user_id,
            query=query or "",  # query is required, provide empty string if None
            max_results=max_results,
        )

    async def drive_get_file(self, file_id: str, fields: Optional[str] = None) -> dict[str, Any]:
        """Get Google Drive file metadata."""
        if not self._drive_tool:
            raise RuntimeError("Drive tool not initialized")

        return await self._drive_tool.get_file(user_id="default_user", file_id=file_id)

    async def drive_download_file(self, file_id: str, mime_type: Optional[str] = None) -> bytes:
        """Download a Google Drive file."""
        if not self._drive_tool:
            raise RuntimeError("Drive tool not initialized")

        # Note: download_file is not implemented in DriveConnectorTool
        raise NotImplementedError("File download not yet implemented in DriveConnectorTool")

    # Calendar Tools
    async def gcal_list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        max_results: int = 10,
        single_events: bool = True,
        order_by: str = "startTime",
        user_id: str = "default_user",
    ) -> dict[str, Any]:
        """List Google Calendar events."""
        if not self._gcal_tool:
            raise RuntimeError("Calendar tool not initialized")

        # GCalConnectorTool.list_events expects: user_id, max_results, time_min, time_max
        # It doesn't support calendar_id, single_events, or order_by
        return await self._gcal_tool.list_events(
            user_id=user_id, max_results=max_results, time_min=time_min, time_max=time_max
        )

    async def gcal_get_event(
        self, event_id: str, calendar_id: str = "primary", user_id: str = "default_user"
    ) -> dict[str, Any]:
        """Get a specific calendar event."""
        if not self._gcal_tool:
            raise RuntimeError("Calendar tool not initialized")

        # GCalConnectorTool.get_event expects: user_id, event_id
        # It doesn't support calendar_id
        return await self._gcal_tool.get_event(user_id=user_id, event_id=event_id)

    async def gcal_create_event(
        self,
        summary: str,
        start: dict[str, Any],
        end: dict[str, Any],
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[list[dict[str, str]]] = None,
        calendar_id: str = "primary",
    ) -> dict[str, Any]:
        """Create a calendar event."""
        if not self._gcal_tool:
            raise RuntimeError("Calendar tool not initialized")

        event: dict[str, Any] = {"summary": summary, "start": start, "end": end}

        if description:
            event["description"] = description
        if location:
            event["location"] = location
        if attendees:
            event["attendees"] = attendees

        # Note: create_event is not implemented in GCalConnectorTool
        raise NotImplementedError("Event creation not yet implemented in GCalConnectorTool")

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Get MCP tool definitions for all Google tools."""
        return [
            # Gmail tools
            {
                "name": "gmail_search",
                "description": "Search Gmail messages using Gmail query syntax",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Gmail search query (e.g., 'from:user@example.com', "
                                "'subject:meeting')"
                            ),
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 10)",
                        },
                        "include_body": {
                            "type": "boolean",
                            "description": "Whether to include message body (default: false)",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "gmail_get_message",
                "description": "Get a specific Gmail message by ID",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "message_id": {"type": "string", "description": "Gmail message ID"}
                    },
                    "required": ["message_id"],
                },
            },
            # Drive tools
            {
                "name": "drive_search_files",
                "description": "Search Google Drive files",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Drive search query (e.g., 'name contains \"report\"')",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 10)",
                        },
                    },
                },
            },
            {
                "name": "drive_get_file",
                "description": "Get Google Drive file metadata",
                "input_schema": {
                    "type": "object",
                    "properties": {"file_id": {"type": "string", "description": "Drive file ID"}},
                    "required": ["file_id"],
                },
            },
            # Calendar tools
            {
                "name": "gcal_list_events",
                "description": "List Google Calendar events",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "time_min": {
                            "type": "string",
                            "description": "Start time in RFC3339 format",
                        },
                        "time_max": {"type": "string", "description": "End time in RFC3339 format"},
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of events (default: 10)",
                        },
                    },
                },
            },
            {
                "name": "gcal_create_event",
                "description": "Create a calendar event",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string", "description": "Event title"},
                        "start": {
                            "type": "object",
                            "description": "Start time (with 'dateTime' or 'date' field)",
                        },
                        "end": {
                            "type": "object",
                            "description": "End time (with 'dateTime' or 'date' field)",
                        },
                        "description": {"type": "string", "description": "Event description"},
                        "location": {"type": "string", "description": "Event location"},
                    },
                    "required": ["summary", "start", "end"],
                },
            },
        ]
