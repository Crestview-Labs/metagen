import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Optional

from googleapiclient.discovery import build

from connectors.google.auth import AsyncGoogleOAuthHandler

logger = logging.getLogger(__name__)


class AsyncGCalService:
    """Async service for interacting with Google Calendar API"""

    def __init__(self, oauth_handler: AsyncGoogleOAuthHandler):
        logger.debug("Initializing AsyncGCalService")
        self.oauth_handler = oauth_handler
        self.executor = ThreadPoolExecutor(max_workers=4)
        logger.debug("Calendar service initialized")

    async def _get_service(self, user_id: str) -> Any:
        """Get authenticated Calendar service instance"""
        logger.debug(f"Getting Calendar service for user: {user_id}")

        credentials = await self.oauth_handler.load_credentials(user_id)

        if not credentials:
            logger.error(f"No credentials found for user: {user_id}")
            raise ValueError("No authentication found. Please authenticate first.")

        logger.debug("Refreshing credentials if needed")
        try:
            credentials = await self.oauth_handler.refresh_token(credentials)
            # Only store credentials if refresh was successful
            await self.oauth_handler.store_credentials(user_id, credentials)
        except ValueError as e:
            # This is our specific token expired error
            logger.warning(f"Token expired/revoked for user {user_id}: {str(e)}")
            raise
        except Exception as e:
            error_str = str(e).lower()
            if "invalid_grant" in error_str or "token has been expired or revoked" in error_str:
                logger.warning(f"Token expired/revoked for user {user_id}: {str(e)}")
                # Re-raise with a more specific error message
                raise ValueError("Token has been expired or revoked. Please re-authenticate.")
            else:
                logger.error(f"Error refreshing token for user {user_id}: {str(e)}")
                raise

        def _build_service() -> Any:
            try:
                logger.debug("Building Calendar API service")
                service = build("calendar", "v3", credentials=credentials)
                logger.debug("Calendar API service built successfully")
                return service
            except Exception as e:
                logger.error(f"Error building Calendar service: {str(e)}", exc_info=True)
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _build_service)

    async def list_events(
        self,
        user_id: str,
        max_results: int = 10,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
    ) -> dict[str, Any]:
        """List calendar events"""
        logger.debug(f"Listing events for user: {user_id}, max_results: {max_results}")

        service = await self._get_service(user_id)

        def _list_events() -> dict[str, Any]:
            try:
                # Default to next 7 days if no time range specified
                actual_time_min = time_min if time_min else datetime.utcnow().isoformat() + "Z"
                actual_time_max = (
                    time_max
                    if time_max
                    else (datetime.utcnow() + timedelta(days=7)).isoformat() + "Z"
                )

                logger.debug(f"Fetching events from {actual_time_min} to {actual_time_max}")

                events_result = (
                    service.events()
                    .list(
                        calendarId="primary",
                        timeMin=actual_time_min,
                        timeMax=actual_time_max,
                        maxResults=max_results,
                        singleEvents=True,
                        orderBy="startTime",
                    )
                    .execute()
                )

                events = events_result.get("items", [])
                logger.debug(f"Found {len(events)} events")

                formatted_events = []
                for event in events:
                    start = event["start"].get("dateTime", event["start"].get("date"))
                    end = event["end"].get("dateTime", event["end"].get("date"))

                    formatted_events.append(
                        {
                            "id": event["id"],
                            "summary": event.get("summary", "No title"),
                            "start": start,
                            "end": end,
                            "location": event.get("location", ""),
                            "description": event.get("description", ""),
                            "attendees": [
                                att.get("email", "") for att in event.get("attendees", [])
                            ],
                            "status": event.get("status", "confirmed"),
                            "link": event.get("htmlLink", ""),
                        }
                    )

                result = {"count": len(formatted_events), "events": formatted_events}

                logger.debug(f"Events list completed, returning {result['count']} events")
                return result

            except Exception as e:
                logger.error(f"Error listing events: {str(e)}", exc_info=True)
                raise

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(self.executor, _list_events)
        except Exception as e:
            logger.error(f"Failed to list events: {str(e)}")
            raise Exception(f"Failed to list events: {str(e)}")

    async def search_events(
        self, user_id: str, query: str, max_results: int = 10
    ) -> dict[str, Any]:
        """Search calendar events by text"""
        logger.debug(
            f"Searching events for user: {user_id}, query: '{query}', max_results: {max_results}"
        )

        service = await self._get_service(user_id)

        def _search() -> dict[str, Any]:
            try:
                logger.debug(f"Executing Calendar search with query: '{query}'")

                # Search in the next 365 days
                time_min = datetime.utcnow().isoformat() + "Z"
                time_max = (datetime.utcnow() + timedelta(days=365)).isoformat() + "Z"

                events_result = (
                    service.events()
                    .list(
                        calendarId="primary",
                        timeMin=time_min,
                        timeMax=time_max,
                        q=query,
                        maxResults=max_results,
                        singleEvents=True,
                        orderBy="startTime",
                    )
                    .execute()
                )

                events = events_result.get("items", [])
                logger.debug(f"Search returned {len(events)} events")

                formatted_events = []
                for event in events:
                    start = event["start"].get("dateTime", event["start"].get("date"))
                    end = event["end"].get("dateTime", event["end"].get("date"))

                    formatted_events.append(
                        {
                            "id": event["id"],
                            "summary": event.get("summary", "No title"),
                            "start": start,
                            "end": end,
                            "location": event.get("location", ""),
                            "description": event.get("description", ""),
                            "attendees": [
                                att.get("email", "") for att in event.get("attendees", [])
                            ],
                            "status": event.get("status", "confirmed"),
                            "link": event.get("htmlLink", ""),
                        }
                    )

                result = {"count": len(formatted_events), "events": formatted_events}

                logger.debug(f"Search completed successfully, returning {result['count']} events")
                return result

            except Exception as e:
                logger.error(f"Error during event search: {str(e)}", exc_info=True)
                raise

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(self.executor, _search)
        except Exception as e:
            logger.error(f"Failed to search events: {str(e)}")
            raise Exception(f"Failed to search events: {str(e)}")

    async def get_event(self, user_id: str, event_id: str) -> dict[str, Any]:
        """Get detailed information about a specific event"""
        logger.debug(f"Getting event for user: {user_id}, event_id: {event_id}")

        service = await self._get_service(user_id)

        def _get_event() -> dict[str, Any]:
            try:
                logger.debug(f"Fetching event details for ID: {event_id}")
                event = service.events().get(calendarId="primary", eventId=event_id).execute()

                start = event["start"].get("dateTime", event["start"].get("date"))
                end = event["end"].get("dateTime", event["end"].get("date"))

                result = {
                    "id": event["id"],
                    "summary": event.get("summary", "No title"),
                    "start": start,
                    "end": end,
                    "location": event.get("location", ""),
                    "description": event.get("description", ""),
                    "attendees": [
                        {
                            "email": att.get("email", ""),
                            "displayName": att.get("displayName", ""),
                            "responseStatus": att.get("responseStatus", "needsAction"),
                        }
                        for att in event.get("attendees", [])
                    ],
                    "organizer": event.get("organizer", {}).get("email", ""),
                    "status": event.get("status", "confirmed"),
                    "link": event.get("htmlLink", ""),
                    "created": event.get("created", ""),
                    "updated": event.get("updated", ""),
                    "recurringEventId": event.get("recurringEventId", ""),
                }

                logger.debug(f"Event retrieved successfully: {result['summary']}")
                return result

            except Exception as e:
                logger.error(f"Error getting event {event_id}: {str(e)}", exc_info=True)
                raise

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(self.executor, _get_event)
        except Exception as e:
            logger.error(f"Failed to get event: {str(e)}")
            raise Exception(f"Failed to get event: {str(e)}")

    def __del__(self) -> None:
        """Cleanup executor on deletion"""
        if hasattr(self, "executor"):
            self.executor.shutdown(wait=False)
