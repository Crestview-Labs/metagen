import base64
import logging
from email.mime.text import MIMEText
from typing import Any, Optional

from connectors.google.base_service import BaseGoogleService

logger = logging.getLogger(__name__)


class GmailService(BaseGoogleService):
    """Gmail API service for metagen"""

    @property
    def service_name(self) -> str:
        return "gmail"

    @property
    def service_version(self) -> str:
        return "v1"

    async def search_messages(
        self, user_id: str, query: str, max_results: int = 10
    ) -> dict[str, Any]:
        """
        Search Gmail messages using Gmail search syntax

        Args:
            user_id: User identifier for credentials
            query: Gmail search query (e.g., "from:john@example.com", "subject:invoice")
            max_results: Maximum number of results to return

        Returns:
            Dict with count, messages array, and optional nextPageToken
        """
        try:
            logger.debug(
                f"Searching Gmail messages for user {user_id}: "
                f"query='{query}', max_results={max_results}"
            )

            def _search_request(service: Any) -> Any:
                return service.users().messages().list(userId="me", q=query, maxResults=max_results)

            result = await self._execute_request(_search_request, user_id)
            messages = result.get("messages", [])

            # Get metadata for each message
            formatted_messages = []
            for message in messages:
                try:

                    def _get_metadata(service: Any) -> Any:
                        return (
                            service.users()
                            .messages()
                            .get(
                                userId="me",
                                id=message["id"],
                                format="metadata",
                                metadataHeaders=["From", "To", "Subject", "Date"],
                            )
                        )

                    msg_data = await self._execute_request(_get_metadata, user_id)

                    # Extract headers
                    headers = {
                        header["name"]: header["value"]
                        for header in msg_data.get("payload", {}).get("headers", [])
                    }

                    formatted_messages.append(
                        {
                            "id": msg_data["id"],
                            "threadId": msg_data["threadId"],
                            "snippet": msg_data.get("snippet", ""),
                            "from": headers.get("From", ""),
                            "to": headers.get("To", ""),
                            "subject": headers.get("Subject", ""),
                            "date": headers.get("Date", ""),
                        }
                    )

                except Exception as e:
                    logger.warning(f"Error getting metadata for message {message['id']}: {str(e)}")
                    continue

            return {
                "count": len(formatted_messages),
                "messages": formatted_messages,
                "nextPageToken": result.get("nextPageToken"),
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error searching Gmail messages: {str(e)}", exc_info=True)
            return self._format_error_response(
                e, {"count": 0, "messages": [], "nextPageToken": None, "success": False}
            )

    async def get_message(self, user_id: str, message_id: str) -> dict[str, Any]:
        """
        Get full Gmail message details

        Args:
            user_id: User identifier for credentials
            message_id: Gmail message ID

        Returns:
            Dict with full message details including body
        """
        try:
            logger.debug(f"Getting Gmail message {message_id} for user {user_id}")

            def _get_message_request(service: Any) -> Any:
                return service.users().messages().get(userId="me", id=message_id, format="full")

            msg_data = await self._execute_request(_get_message_request, user_id)

            # Extract headers
            headers = {
                header["name"]: header["value"]
                for header in msg_data.get("payload", {}).get("headers", [])
            }

            # Extract body
            body = self._extract_body(msg_data.get("payload", {}))

            return {
                "id": msg_data["id"],
                "threadId": msg_data["threadId"],
                "from": headers.get("From", ""),
                "to": headers.get("To", ""),
                "subject": headers.get("Subject", ""),
                "date": headers.get("Date", ""),
                "body": body,
                "snippet": msg_data.get("snippet", ""),
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error getting Gmail message {message_id}: {str(e)}", exc_info=True)
            return self._format_error_response(e, {"id": message_id, "body": "", "success": False})

    async def send_message(
        self,
        user_id: str,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send an email message

        Args:
            user_id: User identifier for credentials
            to: Recipient email address
            subject: Email subject
            body: Email body (text)
            cc: Optional CC recipients
            bcc: Optional BCC recipients

        Returns:
            Dict with sent message details
        """
        try:
            logger.debug(
                f"Sending Gmail message for user {user_id}: to='{to}', subject='{subject}'"
            )

            # Create message
            message = MIMEText(body)
            message["to"] = to
            message["subject"] = subject

            if cc:
                message["cc"] = cc
            if bcc:
                message["bcc"] = bcc

            # Encode message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            def _send_request(service: Any) -> Any:
                return service.users().messages().send(userId="me", body={"raw": raw_message})

            result = await self._execute_request(_send_request, user_id)

            return {
                "id": result["id"],
                "threadId": result["threadId"],
                "to": to,
                "subject": subject,
                "success": True,
                "message": f"Email sent successfully to {to}",
            }

        except Exception as e:
            logger.error(f"Error sending Gmail message: {str(e)}", exc_info=True)
            return self._format_error_response(
                e, {"id": None, "to": to, "subject": subject, "success": False}
            )

    async def get_labels(self, user_id: str) -> dict[str, Any]:
        """Get Gmail labels"""
        try:
            logger.debug(f"Getting Gmail labels for user {user_id}")

            def _get_labels_request(service: Any) -> Any:
                return service.users().labels().list(userId="me")

            result = await self._execute_request(_get_labels_request, user_id)

            labels = [
                {"id": label["id"], "name": label["name"], "type": label["type"]}
                for label in result.get("labels", [])
            ]

            return {"labels": labels, "count": len(labels), "success": True}

        except Exception as e:
            logger.error(f"Error getting Gmail labels: {str(e)}", exc_info=True)
            return self._format_error_response(e, {"labels": [], "count": 0, "success": False})

    async def get_profile(self, user_id: str) -> dict[str, Any]:
        """Get Gmail profile information"""
        try:
            logger.debug(f"Getting Gmail profile for user {user_id}")

            def _get_profile_request(service: Any) -> Any:
                return service.users().getProfile(userId="me")

            result = await self._execute_request(_get_profile_request, user_id)

            return {
                "emailAddress": result.get("emailAddress", ""),
                "messagesTotal": result.get("messagesTotal", 0),
                "threadsTotal": result.get("threadsTotal", 0),
                "historyId": result.get("historyId", ""),
                "success": True,
            }

        except Exception as e:
            logger.error(f"Error getting Gmail profile: {str(e)}", exc_info=True)
            return self._format_error_response(
                e,
                {
                    "emailAddress": "",
                    "messagesTotal": 0,
                    "threadsTotal": 0,
                    "historyId": "",
                    "success": False,
                },
            )

    def _extract_body(self, payload: dict[str, Any]) -> str:
        """Extract message body from Gmail payload"""
        try:
            # Check if message has parts (multipart)
            if "parts" in payload:
                for part in payload["parts"]:
                    if part.get("mimeType") == "text/plain":
                        body_data = part.get("body", {}).get("data", "")
                        if body_data:
                            return base64.urlsafe_b64decode(body_data).decode("utf-8")
                # If no text/plain part found, try first part
                if payload["parts"]:
                    body_data = payload["parts"][0].get("body", {}).get("data", "")
                    if body_data:
                        return base64.urlsafe_b64decode(body_data).decode("utf-8")
            else:
                # Single part message
                body_data = payload.get("body", {}).get("data", "")
                if body_data:
                    return base64.urlsafe_b64decode(body_data).decode("utf-8")

            return "Unable to extract message body"

        except Exception as e:
            logger.warning(f"Error extracting message body: {str(e)}")
            return f"Error extracting message body: {str(e)}"
