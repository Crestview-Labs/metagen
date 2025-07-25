"""Tool result formatting utilities for better UI display."""

import json
from typing import Any


class ToolResultFormatter:
    """Formats tool results for improved readability in the UI."""

    def format_tool_result(self, result_content: str) -> str:
        """Format tool result content for better display."""
        try:
            # Try to parse as JSON and format nicely
            result_data = json.loads(result_content.strip())

            # Handle different tool result types
            if isinstance(result_data, dict):
                # Check for common patterns and format accordingly
                if "success" in result_data and "messages" in result_data:
                    # Gmail search result
                    return self._format_gmail_search_result(result_data)
                elif "success" in result_data and "body" in result_data:
                    # Gmail message result
                    return self._format_gmail_message_result(result_data)
                elif "success" in result_data and "files" in result_data:
                    # Drive search result
                    return self._format_drive_search_result(result_data)
                elif "success" in result_data and "events" in result_data:
                    # Calendar result
                    return self._format_calendar_result(result_data)
                else:
                    # Generic success/error result
                    if result_data.get("success"):
                        return "✅ Operation successful"
                    else:
                        error = result_data.get("error", "Unknown error")
                        return f"❌ Operation failed: {error}"

            # Fallback to pretty JSON
            return f"📊 Result:\n```json\n{json.dumps(result_data, indent=2)}\n```"

        except json.JSONDecodeError:
            # Not JSON, return as-is with formatting
            return f"📋 Result: {result_content.strip()}"

    def _format_gmail_search_result(self, data: dict[str, Any]) -> str:
        """Format Gmail search results."""
        if not data.get("success"):
            return f"❌ Gmail search failed: {data.get('error', 'Unknown error')}"

        messages = data.get("messages", [])
        count = data.get("count", len(messages))

        if count == 0:
            return "📭 No emails found"

        result = f"📧 Found {count} email(s):\n"
        for i, msg in enumerate(messages[:3], 1):  # Show max 3
            from_addr = msg.get("from", "Unknown")
            subject = msg.get("subject", "No subject")
            date = msg.get("date", "No date")
            result += f"  {i}. From: {from_addr}\n     Subject: {subject}\n     Date: {date}\n"

        if len(messages) > 3:
            result += f"  ... and {len(messages) - 3} more"

        return result

    def _format_gmail_message_result(self, data: dict[str, Any]) -> str:
        """Format Gmail message details."""
        if not data.get("success"):
            return f"❌ Failed to get email: {data.get('error', 'Unknown error')}"

        from_addr = data.get("from", "Unknown")
        subject = data.get("subject", "No subject")
        date = data.get("date", "No date")
        body = data.get("body", "No content")

        # Truncate long bodies
        if len(body) > 300:
            body = body[:300] + "..."

        return (
            f"📨 Email Details:\n  From: {from_addr}\n  Subject: {subject}\n"
            f"  Date: {date}\n  Content: {body}"
        )

    def _format_drive_search_result(self, data: dict[str, Any]) -> str:
        """Format Drive search results."""
        if not data.get("success"):
            return f"❌ Drive search failed: {data.get('error', 'Unknown error')}"

        files = data.get("files", [])
        count = data.get("count", len(files))

        if count == 0:
            return "📁 No files found"

        result = f"📁 Found {count} file(s):\n"
        for i, file in enumerate(files[:3], 1):  # Show max 3
            name = file.get("name", "Unknown")
            type_info = file.get("mimeType", "Unknown type")
            result += f"  {i}. {name} ({type_info})\n"

        if len(files) > 3:
            result += f"  ... and {len(files) - 3} more"

        return result

    def _format_calendar_result(self, data: dict[str, Any]) -> str:
        """Format Calendar results."""
        if not data.get("success"):
            return f"❌ Calendar request failed: {data.get('error', 'Unknown error')}"

        events = data.get("events", [])
        count = data.get("count", len(events))

        if count == 0:
            return "📅 No events found"

        result = f"📅 Found {count} event(s):\n"
        for i, event in enumerate(events[:3], 1):  # Show max 3
            summary = event.get("summary", "No title")
            start = event.get("start", "No start time")
            result += f"  {i}. {summary} - {start}\n"

        if len(events) > 3:
            result += f"  ... and {len(events) - 3} more"

        return result


# Global formatter instance
tool_result_formatter = ToolResultFormatter()
