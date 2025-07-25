import logging
from typing import Any

from connectors.google.auth import AsyncGoogleOAuthHandler

from .drive_service_async import AsyncDriveService

logger = logging.getLogger(__name__)


class DriveConnectorTool:
    """MCP-compatible Drive connector tool"""

    def __init__(self, oauth_handler: AsyncGoogleOAuthHandler):
        logger.debug("Initializing DriveConnectorTool")
        self.oauth_handler = oauth_handler
        self.drive_service = AsyncDriveService(oauth_handler)
        logger.debug("DriveConnectorTool initialized")

    async def execute(self, method: str, **kwargs: Any) -> dict[str, Any]:
        """Execute a Drive operation"""
        logger.debug(f"Executing Drive method: {method} with args: {kwargs}")

        if method == "search_files":
            return await self.search_files(**kwargs)
        elif method == "get_file":
            return await self.get_file(**kwargs)
        else:
            logger.error(f"Unknown method: {method}")
            raise ValueError(f"Unknown method: {method}")

    async def search_files(self, user_id: str, query: str, max_results: int = 10) -> dict[str, Any]:
        """Search Google Drive files"""
        logger.debug(
            f"Searching files - user: {user_id}, query: '{query}', max_results: {max_results}"
        )

        try:
            result = await self.drive_service.search_files(user_id, query, max_results)
            logger.debug(f"Search completed - found {result['count']} files")
            return result
        except Exception as e:
            logger.error(f"Error searching files: {str(e)}", exc_info=True)
            raise Exception(f"Failed to search files: {str(e)}")

    async def get_file(self, user_id: str, file_id: str) -> dict[str, Any]:
        """Get detailed information about a specific file"""
        logger.debug(f"Getting file - user: {user_id}, file_id: {file_id}")

        try:
            result = await self.drive_service.get_file(user_id, file_id)
            logger.debug(f"File retrieved - name: {result['name']}")
            return result
        except Exception as e:
            logger.error(f"Error getting file: {str(e)}", exc_info=True)
            raise Exception(f"Failed to get file: {str(e)}")
