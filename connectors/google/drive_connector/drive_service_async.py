import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from googleapiclient.discovery import build

from connectors.google.auth import AsyncGoogleOAuthHandler

logger = logging.getLogger(__name__)


class AsyncDriveService:
    """Async service for interacting with Google Drive API"""

    def __init__(self, oauth_handler: AsyncGoogleOAuthHandler):
        logger.debug("Initializing AsyncDriveService")
        self.oauth_handler = oauth_handler
        self.executor = ThreadPoolExecutor(max_workers=4)
        logger.debug("Drive service initialized")

    async def _get_service(self, user_id: str) -> Any:
        """Get authenticated Drive service instance"""
        logger.debug(f"Getting Drive service for user: {user_id}")

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
                logger.debug("Building Drive API service")
                service = build("drive", "v3", credentials=credentials)
                logger.debug("Drive API service built successfully")
                return service
            except Exception as e:
                logger.error(f"Error building Drive service: {str(e)}", exc_info=True)
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _build_service)

    async def search_files(self, user_id: str, query: str, max_results: int = 10) -> dict[str, Any]:
        """Search Google Drive files"""
        logger.debug(
            f"Searching files for user: {user_id}, query: '{query}', max_results: {max_results}"
        )

        service = await self._get_service(user_id)

        def _search() -> dict[str, Any]:
            try:
                logger.debug(f"Executing Drive search with query: '{query}'")

                # Build Drive API query
                # If query already contains Drive API syntax (like mimeType, name contains,
                # etc.), use it directly
                # Otherwise, wrap it as a name search
                if any(
                    keyword in query.lower()
                    for keyword in [
                        "mimetype=",
                        "name contains",
                        "name =",
                        "parents in",
                        "owners in",
                    ]
                ):
                    # Query already contains Drive API syntax, use it directly
                    drive_query = f"{query} and trashed=false"
                else:
                    # Simple text search, wrap in name contains
                    drive_query = f"name contains '{query}' and trashed=false"

                results = (
                    service.files()
                    .list(
                        q=drive_query,
                        pageSize=max_results,
                        fields="files(id,name,mimeType,modifiedTime,size,webViewLink,owners)",
                    )
                    .execute()
                )

                files = results.get("files", [])
                logger.debug(f"Search returned {len(files)} files")

                formatted_files = []
                for file in files:
                    formatted_files.append(
                        {
                            "id": file["id"],
                            "name": file["name"],
                            "type": file.get("mimeType", ""),
                            "modified": file.get("modifiedTime", ""),
                            "size": file.get("size", "0"),
                            "link": file.get("webViewLink", ""),
                            "owner": file.get("owners", [{}])[0].get("displayName", "")
                            if file.get("owners")
                            else "",
                        }
                    )

                result = {"count": len(formatted_files), "files": formatted_files}

                logger.debug(f"Search completed successfully, returning {result['count']} files")
                return result

            except Exception as e:
                logger.error(f"Error during file search: {str(e)}", exc_info=True)
                raise

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(self.executor, _search)
        except Exception as e:
            logger.error(f"Failed to search files: {str(e)}")
            raise Exception(f"Failed to search files: {str(e)}")

    async def get_file(self, user_id: str, file_id: str) -> dict[str, Any]:
        """Get detailed information about a specific file"""
        logger.debug(f"Getting file for user: {user_id}, file_id: {file_id}")

        service = await self._get_service(user_id)

        def _get_file() -> dict[str, Any]:
            try:
                logger.debug(f"Fetching file details for ID: {file_id}")
                file = (
                    service.files()
                    .get(
                        fileId=file_id,
                        fields="id,name,mimeType,modifiedTime,createdTime,size,webViewLink,owners,description",
                    )
                    .execute()
                )

                result = {
                    "id": file["id"],
                    "name": file["name"],
                    "type": file.get("mimeType", ""),
                    "modified": file.get("modifiedTime", ""),
                    "created": file.get("createdTime", ""),
                    "size": file.get("size", "0"),
                    "link": file.get("webViewLink", ""),
                    "owner": file.get("owners", [{}])[0].get("displayName", "")
                    if file.get("owners")
                    else "",
                    "description": file.get("description", ""),
                }

                logger.debug(f"File retrieved successfully: {result['name']}")
                return result

            except Exception as e:
                logger.error(f"Error getting file {file_id}: {str(e)}", exc_info=True)
                raise

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(self.executor, _get_file)
        except Exception as e:
            logger.error(f"Failed to get file: {str(e)}")
            raise Exception(f"Failed to get file: {str(e)}")

    def __del__(self) -> None:
        """Cleanup executor on deletion"""
        if hasattr(self, "executor"):
            self.executor.shutdown(wait=False)
