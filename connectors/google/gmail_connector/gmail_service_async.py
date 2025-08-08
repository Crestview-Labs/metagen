import asyncio
import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from googleapiclient.discovery import build

from connectors.google.auth import AsyncGoogleOAuthHandler

logger = logging.getLogger(__name__)


class AsyncGmailService:
    """Async service for interacting with Gmail API"""

    def __init__(self, oauth_handler: AsyncGoogleOAuthHandler):
        logger.debug("Initializing AsyncGmailService")
        self.oauth_handler = oauth_handler
        self.executor = ThreadPoolExecutor(max_workers=4)
        logger.debug("Gmail service initialized")

    async def _get_service(self, user_id: str) -> Any:
        """Get authenticated Gmail service instance"""
        logger.debug(f"Getting Gmail service for user: {user_id}")

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
                logger.debug("Building Gmail API service")
                service = build("gmail", "v1", credentials=credentials)
                logger.debug("Gmail API service built successfully")
                return service
            except Exception as e:
                logger.error(f"Error building Gmail service: {str(e)}", exc_info=True)
                raise

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _build_service)

    async def search_messages(
        self, user_id: str, query: str, max_results: int = 10
    ) -> dict[str, Any]:
        """Search Gmail messages with a query"""
        logger.debug(
            f"Searching messages for user: {user_id}, query: '{query}', max_results: {max_results}"
        )

        service = await self._get_service(user_id)

        def _search() -> dict[str, Any]:
            try:
                logger.debug(f"Executing Gmail search with query: '{query}'")
                # Note: When both gmail.readonly and gmail.metadata scopes are present,
                # the API sometimes enforces metadata-only restrictions
                results = (
                    service.users()
                    .messages()
                    .list(userId="me", q=query, maxResults=max_results)
                    .execute()
                )

                messages = results.get("messages", [])
                logger.debug(f"Search returned {len(messages)} messages")

                detailed_messages = []
                for idx, msg in enumerate(messages):
                    logger.debug(
                        f"Fetching details for message {idx + 1}/{len(messages)}, ID: {msg['id']}"
                    )
                    message_detail = (
                        service.users()
                        .messages()
                        .get(
                            userId="me",
                            id=msg["id"],
                            format="metadata",
                            metadataHeaders=["From", "To", "Subject", "Date"],
                        )
                        .execute()
                    )

                    headers = {
                        header["name"]: header["value"]
                        for header in message_detail["payload"].get("headers", [])
                    }

                    detailed_messages.append(
                        {
                            "id": msg["id"],
                            "threadId": message_detail["threadId"],
                            "snippet": message_detail["snippet"],
                            "from": headers.get("From", ""),
                            "to": headers.get("To", ""),
                            "subject": headers.get("Subject", ""),
                            "date": headers.get("Date", ""),
                        }
                    )

                result = {
                    "count": len(detailed_messages),
                    "messages": detailed_messages,
                    "nextPageToken": results.get("nextPageToken"),
                }

                logger.debug(f"Search completed successfully, returning {result['count']} messages")
                return result

            except Exception as e:
                logger.error(f"Error during message search: {str(e)}", exc_info=True)
                raise

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(self.executor, _search)
        except Exception as e:
            logger.error(f"Failed to search messages: {str(e)}")
            raise Exception(f"Failed to search messages: {str(e)}")

    async def get_message(self, user_id: str, message_id: str) -> dict[str, Any]:
        """Get a specific message by ID"""
        logger.debug(f"Getting message for user: {user_id}, message_id: {message_id}")

        service = await self._get_service(user_id)

        def _get_message() -> dict[str, Any]:
            try:
                logger.debug(f"Fetching full message details for ID: {message_id}")
                message = (
                    service.users()
                    .messages()
                    .get(userId="me", id=message_id, format="full")
                    .execute()
                )

                # Log the raw payload structure for debugging
                import json

                payload_json = json.dumps(message.get("payload", {}), indent=2)[:2000]
                logger.info(f"Raw Gmail message payload structure: {payload_json}")

                logger.debug("Extracting headers from message")
                headers = {
                    header["name"]: header["value"]
                    for header in message["payload"].get("headers", [])
                }

                logger.debug("Extracting body from message payload")
                body = self._extract_body(message["payload"])

                result = {
                    "id": message["id"],
                    "threadId": message["threadId"],
                    "from": headers.get("From", ""),
                    "to": headers.get("To", ""),
                    "subject": headers.get("Subject", ""),
                    "date": headers.get("Date", ""),
                    "body": body,
                    "snippet": message.get("snippet", ""),
                }

                logger.debug(
                    f"Message retrieved successfully, subject: {result['subject'][:50]}..."
                )
                return result

            except Exception as e:
                logger.error(f"Error getting message {message_id}: {str(e)}", exc_info=True)
                raise

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(self.executor, _get_message)
        except Exception as e:
            logger.error(f"Failed to get message: {str(e)}")
            raise Exception(f"Failed to get message: {str(e)}")

    def _extract_body(self, payload: dict[str, Any]) -> str:
        """Extract body from message payload"""
        logger.info("Extracting message body from payload")

        # Debug: Log the payload structure
        logger.info(f"Payload keys: {list(payload.keys())}")
        if "mimeType" in payload:
            logger.info(f"Payload mimeType: {payload['mimeType']}")
        if "parts" in payload:
            logger.info(f"Payload has {len(payload['parts'])} parts")
            for i, part in enumerate(payload["parts"]):
                has_data = bool(part.get("body", {}).get("data"))
                logger.info(
                    f"  Part {i}: mimeType={part.get('mimeType')}, "
                    f"has_body={bool(part.get('body'))}, has_data={has_data}"
                )
        if "body" in payload:
            logger.info(f"Payload has body: data_size={len(payload['body'].get('data', ''))}")

        body = ""

        try:
            # Recursively search for text content
            body = self._extract_body_recursive(payload)
            if not body:
                logger.debug("No body data found in message")
                body = "[No message body found]"
            else:
                logger.debug(f"Extracted body, length: {len(body)}")
        except Exception as e:
            logger.error(f"Error extracting body: {str(e)}", exc_info=True)
            body = "[Error extracting message body]"

        return body

    def _extract_body_recursive(self, payload: dict[str, Any]) -> str:
        """Recursively extract body from nested MIME parts"""
        body = ""

        # Check if this part has data directly
        if payload.get("body", {}).get("data"):
            try:
                # Important: Gmail may have padding issues, add padding if needed
                data = payload["body"]["data"]
                # Add padding if needed (base64 needs to be multiple of 4)
                missing_padding = len(data) % 4
                if missing_padding:
                    data += "=" * (4 - missing_padding)
                body = base64.urlsafe_b64decode(data).decode("utf-8")
                logger.info(f"Successfully decoded body data, length: {len(body)}")
                return body
            except Exception as e:
                logger.info(f"Failed to decode body data: {str(e)}")

        # Check for parts
        if "parts" in payload:
            # First, try to find text/plain
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    try:
                        # Add padding if needed (base64 needs to be multiple of 4)
                        data = part["body"]["data"]
                        logger.info(
                            f"Raw base64 data length: {len(data)}, first 100 chars: {data[:100]}"
                        )
                        missing_padding = len(data) % 4
                        if missing_padding:
                            data += "=" * (4 - missing_padding)
                        body = base64.urlsafe_b64decode(data).decode("utf-8")
                        content_preview = body[:200] if body else "[empty]"
                        logger.info(
                            f"Successfully decoded text/plain part, "
                            f"length: {len(body)}, content: {content_preview}"
                        )
                        if body and body.strip():  # Check if body has actual content
                            return body
                    except Exception as e:
                        logger.debug(f"Failed to decode text/plain part: {str(e)}")

            # If no text/plain with content, try text/html
            for part in payload["parts"]:
                if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
                    try:
                        # Add padding if needed (base64 needs to be multiple of 4)
                        data = part["body"]["data"]
                        missing_padding = len(data) % 4
                        if missing_padding:
                            data += "=" * (4 - missing_padding)
                        body = base64.urlsafe_b64decode(data).decode("utf-8")
                        if body and body.strip():  # Check for actual content
                            logger.info(f"Successfully decoded text/html part, length: {len(body)}")
                            return body
                    except Exception as e:
                        logger.debug(f"Failed to decode text/html part: {str(e)}")

            # Recursively check nested parts (for multipart/alternative, multipart/mixed, etc.)
            for part in payload["parts"]:
                if "multipart" in part.get("mimeType", "").lower():
                    nested_body = self._extract_body_recursive(part)
                    if nested_body:
                        return nested_body

        return body

    async def get_labels(self, user_id: str) -> list[dict[str, Any]]:
        """Get all labels in the user's account"""
        logger.debug(f"Getting labels for user: {user_id}")

        service = await self._get_service(user_id)

        def _get_labels() -> list[dict[str, Any]]:
            try:
                logger.debug("Fetching Gmail labels")
                results = service.users().labels().list(userId="me").execute()
                labels = results.get("labels", [])
                logger.debug(f"Found {len(labels)} labels")

                formatted_labels = [
                    {"id": label["id"], "name": label["name"], "type": label.get("type", "user")}
                    for label in labels
                ]

                logger.debug("Labels retrieved successfully")
                return formatted_labels

            except Exception as e:
                logger.error(f"Error getting labels: {str(e)}", exc_info=True)
                raise

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(self.executor, _get_labels)
        except Exception as e:
            logger.error(f"Failed to get labels: {str(e)}")
            raise Exception(f"Failed to get labels: {str(e)}")

    async def get_profile(self, user_id: str) -> dict[str, Any]:
        """Get user's Gmail profile"""
        logger.debug(f"Getting Gmail profile for user: {user_id}")

        try:
            service = await self._get_service(user_id)
        except ValueError as e:
            # This catches our specific token expired error from _get_service
            logger.warning(f"Authentication error in get_profile: {str(e)}")
            raise

        def _get_profile() -> dict[str, Any]:
            try:
                logger.debug("Fetching Gmail profile")
                profile = service.users().getProfile(userId="me").execute()

                result = {
                    "emailAddress": profile.get("emailAddress", ""),
                    "messagesTotal": profile.get("messagesTotal", 0),
                    "threadsTotal": profile.get("threadsTotal", 0),
                    "historyId": profile.get("historyId", ""),
                }

                logger.debug(
                    f"Profile retrieved: email={result['emailAddress']}, "
                    f"messages={result['messagesTotal']}, threads={result['threadsTotal']}"
                )
                return result

            except Exception as e:
                # Check if this is a token refresh error that happened during API call
                error_str = str(e)
                if (
                    "invalid_grant" in error_str.lower()
                    or "token has been expired or revoked" in error_str.lower()
                ):
                    logger.warning(f"Token expired during API call: {error_str}")
                    # Re-raise as ValueError to match our expected error type
                    raise ValueError("Token has been expired or revoked. Please re-authenticate.")
                else:
                    logger.error(f"Error getting profile: {error_str}")
                    raise

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(self.executor, _get_profile)
        except ValueError:
            # Re-raise ValueError as-is (token expired errors)
            raise
        except Exception as e:
            logger.error(f"Failed to get profile: {str(e)}")
            raise Exception(f"Failed to get profile: {str(e)}")

    def __del__(self) -> None:
        """Cleanup executor on deletion"""
        if hasattr(self, "executor"):
            self.executor.shutdown(wait=False)
