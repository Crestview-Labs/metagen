import logging
from typing import Any, Optional

from connectors.google.auth import AsyncGoogleOAuthHandler

from .gcal_service_async import AsyncGCalService

logger = logging.getLogger(__name__)


class GCalConnectorTool:
    """MCP-compatible Google Calendar connector tool"""

    def __init__(self, oauth_handler: AsyncGoogleOAuthHandler):
        logger.debug("Initializing GCalConnectorTool")
        self.oauth_handler = oauth_handler
        self.gcal_service = AsyncGCalService(oauth_handler)
        logger.debug("GCalConnectorTool initialized")

    async def execute(self, method: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a Calendar operation"""
        logger.debug(f"Executing Calendar method: {method} with args: {kwargs}")

        if method == "list_events":
            return await self.list_events(**kwargs)
        elif method == "search_events":
            return await self.search_events(**kwargs)
        elif method == "get_event":
            return await self.get_event(**kwargs)
        else:
            logger.error(f"Unknown method: {method}")
            raise ValueError(f"Unknown method: {method}")

    async def list_events(
        self,
        user_id: str,
        max_results: int = 10,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
    ) -> dict[str, Any]:
        """List calendar events"""
        logger.debug(f"Listing events - user: {user_id}, max_results: {max_results}")

        try:
            result = await self.gcal_service.list_events(user_id, max_results, time_min, time_max)
            logger.debug(f"List completed - found {result['count']} events")
            return result
        except Exception as e:
            logger.error(f"Error listing events: {str(e)}", exc_info=True)
            raise Exception(f"Failed to list events: {str(e)}")

    async def search_events(
        self, user_id: str, query: str, max_results: int = 10
    ) -> dict[str, Any]:
        """Search calendar events by text"""
        logger.debug(
            f"Searching events - user: {user_id}, query: '{query}', max_results: {max_results}"
        )

        try:
            result = await self.gcal_service.search_events(user_id, query, max_results)
            logger.debug(f"Search completed - found {result['count']} events")
            return result
        except Exception as e:
            logger.error(f"Error searching events: {str(e)}", exc_info=True)
            raise Exception(f"Failed to search events: {str(e)}")

    async def get_event(self, user_id: str, event_id: str) -> dict[str, Any]:
        """Get detailed information about a specific event"""
        logger.debug(f"Getting event - user: {user_id}, event_id: {event_id}")

        try:
            result = await self.gcal_service.get_event(user_id, event_id)
            logger.debug(f"Event retrieved - summary: {result['summary']}")
            return result
        except Exception as e:
            logger.error(f"Error getting event: {str(e)}", exc_info=True)
            raise Exception(f"Failed to get event: {str(e)}")
