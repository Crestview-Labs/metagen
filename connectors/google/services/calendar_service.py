import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from connectors.google.base_service import BaseGoogleService

logger = logging.getLogger(__name__)


class CalendarService(BaseGoogleService):
    """Google Calendar API service for metagen"""

    @property
    def service_name(self) -> str:
        return "calendar"

    @property
    def service_version(self) -> str:
        return "v3"

    async def list_events(
        self,
        user_id: str,
        max_results: int = 10,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        List calendar events

        Args:
            user_id: User identifier for credentials
            max_results: Maximum number of events to return
            time_min: Start of time range (ISO format, optional)
            time_max: End of time range (ISO format, optional)

        Returns:
            Dict with count and events array
        """
        try:
            logger.debug(f"Listing calendar events for user {user_id}: max_results={max_results}")

            # Set default time range if not provided
            if not time_min:
                time_min = datetime.utcnow().isoformat() + "Z"
            if not time_max:
                # Default to 7 days from now
                end_time = datetime.utcnow() + timedelta(days=7)
                time_max = end_time.isoformat() + "Z"

            def _list_events_request(service: Any) -> Any:
                return service.events().list(
                    calendarId="primary",
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )

            result = await self._execute_request(_list_events_request, user_id)
            events = result.get("items", [])

            # Format events for response
            formatted_events = []
            for event in events:
                start = event.get("start", {})
                end = event.get("end", {})

                formatted_events.append(
                    {
                        "id": event.get("id", ""),
                        "summary": event.get("summary", "No title"),
                        "description": event.get("description", ""),
                        "location": event.get("location", ""),
                        "start": start.get("dateTime", start.get("date", "")),
                        "end": end.get("dateTime", end.get("date", "")),
                        "link": event.get("htmlLink", ""),
                        "attendees": [a.get("email", "") for a in event.get("attendees", [])],
                    }
                )

            return {"count": len(formatted_events), "events": formatted_events, "success": True}

        except Exception as e:
            logger.error(f"Error listing calendar events: {str(e)}", exc_info=True)
            return self._format_error_response(e, {"count": 0, "events": [], "success": False})

    async def search_events(
        self, user_id: str, query: str, max_results: int = 10
    ) -> dict[str, Any]:
        """
        Search calendar events

        Args:
            user_id: User identifier for credentials
            query: Search query text
            max_results: Maximum number of events to return

        Returns:
            Dict with count and events array
        """
        try:
            logger.debug(f"Searching calendar events for user {user_id}: query='{query}'")

            def _search_events_request(service: Any) -> Any:
                return service.events().list(
                    calendarId="primary",
                    q=query,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                )

            result = await self._execute_request(_search_events_request, user_id)
            events = result.get("items", [])

            # Format events for response
            formatted_events = []
            for event in events:
                start = event.get("start", {})
                end = event.get("end", {})

                formatted_events.append(
                    {
                        "id": event.get("id", ""),
                        "summary": event.get("summary", "No title"),
                        "description": event.get("description", ""),
                        "location": event.get("location", ""),
                        "start": start.get("dateTime", start.get("date", "")),
                        "end": end.get("dateTime", end.get("date", "")),
                        "link": event.get("htmlLink", ""),
                        "attendees": [a.get("email", "") for a in event.get("attendees", [])],
                    }
                )

            return {
                "count": len(formatted_events),
                "events": formatted_events,
                "query": query,
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error searching calendar events: {str(e)}", exc_info=True)
            return self._format_error_response(
                e, {"count": 0, "events": [], "query": query, "success": False}
            )
