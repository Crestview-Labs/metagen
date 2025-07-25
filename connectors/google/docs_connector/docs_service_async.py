"""Async Google Docs service implementation."""

import logging
from typing import Any

from connectors.google.base_service import BaseGoogleService

logger = logging.getLogger(__name__)


class DocsServiceAsync(BaseGoogleService):
    """Async Google Docs service implementation."""

    @property
    def service_name(self) -> str:
        return "docs"

    @property
    def service_version(self) -> str:
        return "v1"

    async def get_document(self, document_id: str, user_id: str = "default_user") -> dict[str, Any]:
        """
        Get a Google Docs document by ID.

        Args:
            document_id: The Google Docs document ID
            user_id: User identifier for credentials

        Returns:
            Dictionary containing document data
        """
        logger.info(f"Getting document {document_id} for user {user_id}")

        try:

            def _get_document(service: Any) -> Any:
                return service.documents().get(documentId=document_id)

            result = await self._execute_request(_get_document, user_id)

            return {
                "success": True,
                "document": result,
                "document_id": document_id,
                "title": result.get("title", ""),
                "revision_id": result.get("revisionId", ""),
                "document_style": result.get("documentStyle", {}),
                "body": result.get("body", {}),
            }

        except Exception as e:
            logger.error(f"Error getting document {document_id}: {str(e)}")
            return self._format_error_response(
                e, {"success": False, "document_id": document_id, "document": None}
            )

    async def create_document(self, title: str, user_id: str = "default_user") -> dict[str, Any]:
        """
        Create a new Google Docs document.

        Args:
            title: Title for the new document
            user_id: User identifier for credentials

        Returns:
            Dictionary containing created document data
        """
        logger.info(f"Creating document '{title}' for user {user_id}")

        try:

            def _create_document(service: Any) -> Any:
                return service.documents().create(body={"title": title})

            result = await self._execute_request(_create_document, user_id)

            return {
                "success": True,
                "document": result,
                "document_id": result.get("documentId", ""),
                "title": result.get("title", ""),
                "revision_id": result.get("revisionId", ""),
                "document_url": (
                    f"https://docs.google.com/document/d/{result.get('documentId', '')}"
                ),
            }

        except Exception as e:
            logger.error(f"Error creating document '{title}': {str(e)}")
            return self._format_error_response(
                e, {"success": False, "title": title, "document": None}
            )

    async def batch_update_document(
        self, document_id: str, requests: list[dict[str, Any]], user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Apply batch updates to a Google Docs document.

        Args:
            document_id: The Google Docs document ID
            requests: List of update requests
            user_id: User identifier for credentials

        Returns:
            Dictionary containing update results
        """
        logger.info(
            f"Batch updating document {document_id} with {len(requests)} requests "
            f"for user {user_id}"
        )

        try:

            def _batch_update(service: Any) -> Any:
                return service.documents().batchUpdate(
                    documentId=document_id, body={"requests": requests}
                )

            result = await self._execute_request(_batch_update, user_id)

            return {
                "success": True,
                "document_id": document_id,
                "revision_id": result.get("documentRevisionId", ""),
                "replies": result.get("replies", []),
                "write_control": result.get("writeControl", {}),
            }

        except Exception as e:
            logger.error(f"Error batch updating document {document_id}: {str(e)}")
            return self._format_error_response(
                e, {"success": False, "document_id": document_id, "requests": requests}
            )

    async def insert_text(
        self, document_id: str, text: str, index: int = 1, user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Insert text into a Google Docs document.

        Args:
            document_id: The Google Docs document ID
            text: Text to insert
            index: Location to insert text (default: 1, beginning of document)
            user_id: User identifier for credentials

        Returns:
            Dictionary containing insert results
        """
        logger.info(
            f"Inserting text into document {document_id} at index {index} for user {user_id}"
        )

        requests = [{"insertText": {"location": {"index": index}, "text": text}}]

        return await self.batch_update_document(document_id, requests, user_id)

    async def replace_text(
        self, document_id: str, find_text: str, replace_text: str, user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Replace all occurrences of text in a Google Docs document.

        Args:
            document_id: The Google Docs document ID
            find_text: Text to find and replace
            replace_text: Text to replace with
            user_id: User identifier for credentials

        Returns:
            Dictionary containing replace results
        """
        logger.info(
            f"Replacing text in document {document_id}: '{find_text}' -> "
            f"'{replace_text}' for user {user_id}"
        )

        requests = [
            {
                "replaceAllText": {
                    "containsText": {"text": find_text, "matchCase": False},
                    "replaceText": replace_text,
                }
            }
        ]

        return await self.batch_update_document(document_id, requests, user_id)

    async def get_document_content(
        self, document_id: str, user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Get the text content of a Google Docs document.

        Args:
            document_id: The Google Docs document ID
            user_id: User identifier for credentials

        Returns:
            Dictionary containing document text content
        """
        logger.info(f"Getting content from document {document_id} for user {user_id}")

        try:
            doc_result = await self.get_document(document_id, user_id)

            if not doc_result.get("success", False):
                return doc_result

            document = doc_result.get("document", {})
            body = document.get("body", {})
            content = body.get("content", [])

            # Extract text from document structure
            text_content = []

            def extract_text_from_element(element: dict[str, Any]) -> None:
                if "paragraph" in element:
                    paragraph = element["paragraph"]
                    paragraph_text = ""
                    for text_element in paragraph.get("elements", []):
                        if "textRun" in text_element:
                            paragraph_text += text_element["textRun"].get("content", "")
                    text_content.append(paragraph_text)
                elif "table" in element:
                    # Handle table content
                    table = element["table"]
                    for row in table.get("tableRows", []):
                        for cell in row.get("tableCells", []):
                            for cell_element in cell.get("content", []):
                                extract_text_from_element(cell_element)

            for element in content:
                extract_text_from_element(element)

            full_text = "".join(text_content)

            return {
                "success": True,
                "document_id": document_id,
                "title": document.get("title", ""),
                "text_content": full_text,
                "paragraph_count": len(text_content),
                "character_count": len(full_text),
            }

        except Exception as e:
            logger.error(f"Error getting content from document {document_id}: {str(e)}")
            return self._format_error_response(
                e, {"success": False, "document_id": document_id, "text_content": ""}
            )
