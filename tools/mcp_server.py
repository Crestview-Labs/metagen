"""Central MCP Server for metagen tools.

This MCP server exposes external service tools (Google services, etc.)
Core tools (file, memory, LLM analysis) are handled directly by Meta-agent.
"""

import logging
import signal
import sys
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from connectors.google.auth.oauth_handler import AsyncGoogleOAuthHandler
from connectors.google.docs_connector.docs_tool import DocsConnectorTool
from connectors.google.drive_connector.drive_tool import DriveConnectorTool
from connectors.google.gcal_connector.gcal_tool import GCalConnectorTool

# Google connector tools
from connectors.google.gmail_connector.gmail_tool import GmailConnectorTool
from connectors.google.sheets_connector.sheets_tool import SheetsConnectorTool
from connectors.google.slides_connector.slides_tool import SlidesConnectorTool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize telemetry
tracer = trace.get_tracer(__name__)
propagator = TraceContextTextMapPropagator()

# Initialize FastMCP server
mcp = FastMCP("metagen-server")

# Initialize OAuth handler (shared across Google services)
oauth_handler = AsyncGoogleOAuthHandler()

# Initialize Google service tools
gmail_tool = GmailConnectorTool(oauth_handler)
drive_tool = DriveConnectorTool(oauth_handler)
gcal_tool = GCalConnectorTool(oauth_handler)
docs_tool = DocsConnectorTool(oauth_handler)
sheets_tool = SheetsConnectorTool(oauth_handler)
slides_tool = SlidesConnectorTool(oauth_handler)


@mcp.tool()
async def gmail_search(
    query: str, user_id: str = "default_user", max_results: int = 10
) -> dict[str, Any]:
    """
    Search Gmail emails using Gmail query syntax.

    Args:
        query: Gmail search query (e.g., "from:john@example.com", "subject:invoice")
        user_id: User identifier (default: "default_user")
        max_results: Maximum number of emails to return (default: 10)

    Returns:
        Dictionary containing count and list of matching emails
    """
    return await gmail_tool.search_emails(user_id, query, max_results)


@mcp.tool()
async def gmail_get_email(message_id: str, user_id: str = "default_user") -> dict[str, Any]:
    """
    Get detailed information about a specific Gmail email.

    Args:
        message_id: Gmail message ID
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing email details including full body
    """
    return await gmail_tool.get_email(user_id, message_id)


@mcp.tool()
async def gmail_get_labels(user_id: str = "default_user") -> dict[str, Any]:
    """
    Get all Gmail labels for the user.

    Args:
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing list of labels
    """
    return await gmail_tool.get_labels(user_id)


@mcp.tool()
async def drive_search_files(
    query: str, user_id: str = "default_user", max_results: int = 10
) -> dict[str, Any]:
    """
    Search Google Drive files.

    Args:
        query: Drive search query
        user_id: User identifier (default: "default_user")
        max_results: Maximum number of files to return (default: 10)

    Returns:
        Dictionary containing count and list of matching files
    """
    return await drive_tool.search_files(user_id, query, max_results)


@mcp.tool()
async def drive_get_file(file_id: str, user_id: str = "default_user") -> dict[str, Any]:
    """
    Get detailed information about a specific Google Drive file.

    Args:
        file_id: Google Drive file ID
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing file details
    """
    return await drive_tool.get_file(user_id, file_id)


@mcp.tool()
async def calendar_list_events(
    user_id: str = "default_user",
    max_results: int = 10,
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
) -> dict[str, Any]:
    """
    List Google Calendar events.

    Args:
        user_id: User identifier (default: "default_user")
        max_results: Maximum number of events to return (default: 10)
        time_min: RFC3339 timestamp for earliest event (optional)
        time_max: RFC3339 timestamp for latest event (optional)

    Returns:
        Dictionary containing list of events
    """
    return await gcal_tool.list_events(user_id, max_results, time_min, time_max)


@mcp.tool()
async def google_auth_status(user_id: str = "default_user") -> dict[str, Any]:
    """
    Check Google authentication status for a user.

    Args:
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing authentication status for each service
    """
    gmail_auth = await gmail_tool.is_authenticated(user_id)

    return {
        "user_id": user_id,
        "gmail_authenticated": gmail_auth,
        "drive_authenticated": gmail_auth,  # Same OAuth scope
        "calendar_authenticated": gmail_auth,  # Same OAuth scope
        "docs_authenticated": gmail_auth,  # Same OAuth scope
        "sheets_authenticated": gmail_auth,  # Same OAuth scope
        "slides_authenticated": gmail_auth,  # Same OAuth scope
        "services_available": ["gmail", "drive", "calendar", "docs", "sheets", "slides"],
    }


# Google Docs Tools


@mcp.tool()
async def docs_get_document(document_id: str, user_id: str = "default_user") -> dict[str, Any]:
    """
    Get a Google Docs document by ID.

    Args:
        document_id: The Google Docs document ID
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing document data
    """
    return await docs_tool.get_document(user_id, document_id)


@mcp.tool()
async def docs_create_document(title: str, user_id: str = "default_user") -> dict[str, Any]:
    """
    Create a new Google Docs document.

    Args:
        title: Title for the new document
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing created document data
    """
    return await docs_tool.create_document(user_id, title)


@mcp.tool()
async def docs_get_content(document_id: str, user_id: str = "default_user") -> dict[str, Any]:
    """
    Get the text content of a Google Docs document.

    Args:
        document_id: The Google Docs document ID
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing document text content
    """
    return await docs_tool.get_document_content(user_id, document_id)


@mcp.tool()
async def docs_insert_text(
    document_id: str, text: str, index: int = 1, user_id: str = "default_user"
) -> dict[str, Any]:
    """
    Insert text into a Google Docs document.

    Args:
        document_id: The Google Docs document ID
        text: Text to insert
        index: Location to insert text (default: 1, beginning of document)
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing insert results
    """
    return await docs_tool.insert_text(user_id, document_id, text, index)


@mcp.tool()
async def docs_replace_text(
    document_id: str, find_text: str, replace_text: str, user_id: str = "default_user"
) -> dict[str, Any]:
    """
    Replace all occurrences of text in a Google Docs document.

    Args:
        document_id: The Google Docs document ID
        find_text: Text to find and replace
        replace_text: Text to replace with
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing replace results
    """
    return await docs_tool.replace_text(user_id, document_id, find_text, replace_text)


# Google Sheets Tools


@mcp.tool()
async def sheets_get_spreadsheet(
    spreadsheet_id: str, user_id: str = "default_user"
) -> dict[str, Any]:
    """
    Get a Google Sheets spreadsheet by ID.

    Args:
        spreadsheet_id: The Google Sheets spreadsheet ID
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing spreadsheet data
    """
    return await sheets_tool.get_spreadsheet(user_id, spreadsheet_id)


@mcp.tool()
async def sheets_create_spreadsheet(title: str, user_id: str = "default_user") -> dict[str, Any]:
    """
    Create a new Google Sheets spreadsheet.

    Args:
        title: Title for the new spreadsheet
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing created spreadsheet data
    """
    return await sheets_tool.create_spreadsheet(user_id, title)


@mcp.tool()
async def sheets_get_values(
    spreadsheet_id: str, range_name: str, user_id: str = "default_user"
) -> dict[str, Any]:
    """
    Get values from a Google Sheets spreadsheet range.

    Args:
        spreadsheet_id: The Google Sheets spreadsheet ID
        range_name: The range to retrieve (e.g., "Sheet1!A1:D10")
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing range values
    """
    return await sheets_tool.get_values(user_id, spreadsheet_id, range_name)


@mcp.tool()
async def sheets_update_values(
    spreadsheet_id: str, range_name: str, values: list[list[str]], user_id: str = "default_user"
) -> dict[str, Any]:
    """
    Update values in a Google Sheets spreadsheet range.

    Args:
        spreadsheet_id: The Google Sheets spreadsheet ID
        range_name: The range to update (e.g., "Sheet1!A1:D10")
        values: 2D array of values to update
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing update results
    """
    return await sheets_tool.update_values(user_id, spreadsheet_id, range_name, values)


@mcp.tool()
async def sheets_append_values(
    spreadsheet_id: str, range_name: str, values: list[list[str]], user_id: str = "default_user"
) -> dict[str, Any]:
    """
    Append values to a Google Sheets spreadsheet.

    Args:
        spreadsheet_id: The Google Sheets spreadsheet ID
        range_name: The range to append to (e.g., "Sheet1!A1:D1")
        values: 2D array of values to append
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing append results
    """
    return await sheets_tool.append_values(user_id, spreadsheet_id, range_name, values)


@mcp.tool()
async def sheets_create_sheet(
    spreadsheet_id: str, sheet_title: str, user_id: str = "default_user"
) -> dict[str, Any]:
    """
    Create a new sheet in a Google Sheets spreadsheet.

    Args:
        spreadsheet_id: The Google Sheets spreadsheet ID
        sheet_title: Title for the new sheet
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing created sheet data
    """
    return await sheets_tool.create_sheet(user_id, spreadsheet_id, sheet_title)


# Google Slides Tools


@mcp.tool()
async def slides_get_presentation(
    presentation_id: str, user_id: str = "default_user"
) -> dict[str, Any]:
    """
    Get a Google Slides presentation by ID.

    Args:
        presentation_id: The Google Slides presentation ID
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing presentation data
    """
    return await slides_tool.get_presentation(user_id, presentation_id)


@mcp.tool()
async def slides_create_presentation(title: str, user_id: str = "default_user") -> dict[str, Any]:
    """
    Create a new Google Slides presentation.

    Args:
        title: Title for the new presentation
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing created presentation data
    """
    return await slides_tool.create_presentation(user_id, title)


@mcp.tool()
async def slides_create_slide(
    presentation_id: str,
    slide_layout_reference: Optional[str] = None,
    user_id: str = "default_user",
) -> dict[str, Any]:
    """
    Create a new slide in a Google Slides presentation.

    Args:
        presentation_id: The Google Slides presentation ID
        slide_layout_reference: Layout reference for the slide (optional)
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing created slide data
    """
    return await slides_tool.create_slide(user_id, presentation_id, slide_layout_reference)


@mcp.tool()
async def slides_add_text(
    presentation_id: str, slide_id: str, text: str, user_id: str = "default_user"
) -> dict[str, Any]:
    """
    Add text to a slide in a Google Slides presentation.

    Args:
        presentation_id: The Google Slides presentation ID
        slide_id: The slide ID to add text to
        text: Text to add
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing text addition results
    """
    return await slides_tool.add_text_to_slide(user_id, presentation_id, slide_id, text)


@mcp.tool()
async def slides_replace_text(
    presentation_id: str, find_text: str, replace_text: str, user_id: str = "default_user"
) -> dict[str, Any]:
    """
    Replace all occurrences of text in a Google Slides presentation.

    Args:
        presentation_id: The Google Slides presentation ID
        find_text: Text to find and replace
        replace_text: Text to replace with
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing replace results
    """
    return await slides_tool.replace_text_in_presentation(
        user_id, presentation_id, find_text, replace_text
    )


@mcp.tool()
async def slides_duplicate_slide(
    presentation_id: str, slide_id: str, user_id: str = "default_user"
) -> dict[str, Any]:
    """
    Duplicate a slide in a Google Slides presentation.

    Args:
        presentation_id: The Google Slides presentation ID
        slide_id: The slide ID to duplicate
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing duplication results
    """
    return await slides_tool.duplicate_slide(user_id, presentation_id, slide_id)


@mcp.tool()
async def slides_delete_slide(
    presentation_id: str, slide_id: str, user_id: str = "default_user"
) -> dict[str, Any]:
    """
    Delete a slide from a Google Slides presentation.

    Args:
        presentation_id: The Google Slides presentation ID
        slide_id: The slide ID to delete
        user_id: User identifier (default: "default_user")

    Returns:
        Dictionary containing deletion results
    """
    return await slides_tool.delete_slide(user_id, presentation_id, slide_id)


if __name__ == "__main__":

    def signal_handler(sig: Any, frame: Any) -> None:
        logger.info("MCP server received shutdown signal")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("🚀 Starting metagen MCP server for external services...")
    mcp.run(transport="stdio")
