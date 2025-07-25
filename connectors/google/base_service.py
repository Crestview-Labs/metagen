import asyncio
import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from googleapiclient.discovery import build

from connectors.google.auth import AsyncGoogleOAuthHandler

logger = logging.getLogger(__name__)


class BaseGoogleService(ABC):
    """Base class for Google API services with common OAuth and service patterns"""

    def __init__(self, oauth_handler: Optional[AsyncGoogleOAuthHandler] = None):
        self.oauth_handler = oauth_handler or AsyncGoogleOAuthHandler()
        self.executor = ThreadPoolExecutor(max_workers=4)
        logger.debug(f"Initialized {self.__class__.__name__}")

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Google API service name (e.g., 'gmail', 'drive', 'calendar')"""
        pass

    @property
    @abstractmethod
    def service_version(self) -> str:
        """Google API service version (e.g., 'v1', 'v3')"""
        pass

    async def _get_service(self, user_id: str = "default_user") -> Any:
        """Get authenticated Google API service instance"""
        logger.debug(f"Getting {self.service_name} service for user: {user_id}")

        # Load credentials
        credentials = await self.oauth_handler.load_credentials(user_id)
        if not credentials:
            raise ValueError(
                f"No authentication found for user {user_id}. "
                "Please authenticate with Google first."
            )

        # Refresh credentials if needed
        try:
            credentials = await self.oauth_handler.refresh_token(credentials)
            await self.oauth_handler.store_credentials(user_id, credentials)
        except ValueError as e:
            # Token expired/revoked - re-raise with helpful message
            logger.warning(f"Token expired/revoked for user {user_id}: {str(e)}")
            raise ValueError(
                f"Authentication expired for user {user_id}. Please re-authenticate with Google."
            )
        except Exception as e:
            # Check for Google-specific auth errors
            error_str = str(e).lower()
            if "invalid_grant" in error_str or "token has been expired or revoked" in error_str:
                logger.warning(f"Invalid grant error for user {user_id}: {str(e)}")
                raise ValueError(
                    f"Authentication expired for user {user_id}. "
                    "Please re-authenticate with Google."
                )
            logger.error(f"Unexpected error refreshing credentials: {str(e)}", exc_info=True)
            raise

        # Build service using ThreadPoolExecutor
        def _build_service() -> Any:
            return build(self.service_name, self.service_version, credentials=credentials)

        loop = asyncio.get_event_loop()
        service = await loop.run_in_executor(self.executor, _build_service)
        logger.debug(f"Successfully built {self.service_name} service")
        return service

    async def _execute_request(self, request_func: Any, user_id: str = "default_user") -> Any:
        """
        Execute a Google API request with proper error handling

        Args:
            request_func: Function that takes a service and returns a request
            user_id: User identifier for credentials
        """
        try:
            service = await self._get_service(user_id)

            def _execute() -> Any:
                request = request_func(service)
                return request.execute()

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(self.executor, _execute)
            logger.debug(f"Successfully executed {self.service_name} request")
            return result

        except ValueError as e:
            # Re-authentication needed
            logger.warning(f"Authentication error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error executing {self.service_name} request: {str(e)}", exc_info=True)
            raise

    def _format_error_response(
        self, error: Exception, default_structure: Optional[dict[Any, Any]] = None
    ) -> dict:
        """Format error response in consistent structure"""
        error_response = default_structure or {"error": str(error), "success": False}
        error_response["error"] = str(error)
        error_response["success"] = False
        return error_response

    def __del__(self) -> None:
        """Cleanup executor on deletion"""
        if hasattr(self, "executor"):
            self.executor.shutdown(wait=False)
