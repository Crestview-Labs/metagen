"""Async Google Slides service implementation."""

import logging
from typing import Any, Optional

from connectors.google.base_service import BaseGoogleService

logger = logging.getLogger(__name__)


class SlidesServiceAsync(BaseGoogleService):
    """Async Google Slides service implementation."""

    @property
    def service_name(self) -> str:
        return "slides"

    @property
    def service_version(self) -> str:
        return "v1"

    async def get_presentation(
        self, presentation_id: str, user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Get a Google Slides presentation by ID.

        Args:
            presentation_id: The Google Slides presentation ID
            user_id: User identifier for credentials

        Returns:
            Dictionary containing presentation data
        """
        logger.info(f"Getting presentation {presentation_id} for user {user_id}")

        try:

            def _get_presentation(service: Any) -> Any:
                return service.presentations().get(presentationId=presentation_id)

            result = await self._execute_request(_get_presentation, user_id)

            return {
                "success": True,
                "presentation": result,
                "presentation_id": presentation_id,
                "title": result.get("title", ""),
                "revision_id": result.get("revisionId", ""),
                "page_size": result.get("pageSize", {}),
                "slides": result.get("slides", []),
                "slide_count": len(result.get("slides", [])),
            }

        except Exception as e:
            logger.error(f"Error getting presentation {presentation_id}: {str(e)}")
            return self._format_error_response(
                e, {"success": False, "presentation_id": presentation_id, "presentation": None}
            )

    async def create_presentation(
        self, title: str, user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Create a new Google Slides presentation.

        Args:
            title: Title for the new presentation
            user_id: User identifier for credentials

        Returns:
            Dictionary containing created presentation data
        """
        logger.info(f"Creating presentation '{title}' for user {user_id}")

        try:

            def _create_presentation(service: Any) -> Any:
                return service.presentations().create(body={"title": title})

            result = await self._execute_request(_create_presentation, user_id)

            return {
                "success": True,
                "presentation": result,
                "presentation_id": result.get("presentationId", ""),
                "title": result.get("title", ""),
                "revision_id": result.get("revisionId", ""),
                "slides": result.get("slides", []),
                "slide_count": len(result.get("slides", [])),
                "presentation_url": (
                    f"https://docs.google.com/presentation/d/{result.get('presentationId', '')}"
                ),
            }

        except Exception as e:
            logger.error(f"Error creating presentation '{title}': {str(e)}")
            return self._format_error_response(
                e, {"success": False, "title": title, "presentation": None}
            )

    async def batch_update_presentation(
        self, presentation_id: str, requests: list[dict[str, Any]], user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Apply batch updates to a Google Slides presentation.

        Args:
            presentation_id: The Google Slides presentation ID
            requests: List of update requests
            user_id: User identifier for credentials

        Returns:
            Dictionary containing update results
        """
        logger.info(
            f"Batch updating presentation {presentation_id} with {len(requests)} "
            f"requests for user {user_id}"
        )

        try:

            def _batch_update(service: Any) -> Any:
                return service.presentations().batchUpdate(
                    presentationId=presentation_id, body={"requests": requests}
                )

            result = await self._execute_request(_batch_update, user_id)

            return {
                "success": True,
                "presentation_id": presentation_id,
                "presentation_id_result": result.get("presentationId", ""),
                "replies": result.get("replies", []),
                "write_control": result.get("writeControl", {}),
            }

        except Exception as e:
            logger.error(f"Error batch updating presentation {presentation_id}: {str(e)}")
            return self._format_error_response(
                e, {"success": False, "presentation_id": presentation_id, "requests": requests}
            )

    async def create_slide(
        self,
        presentation_id: str,
        slide_layout_reference: Optional[str] = None,
        user_id: str = "default_user",
    ) -> dict[str, Any]:
        """
        Create a new slide in a Google Slides presentation.

        Args:
            presentation_id: The Google Slides presentation ID
            slide_layout_reference: Layout reference for the slide (optional)
            user_id: User identifier for credentials

        Returns:
            Dictionary containing created slide data
        """
        logger.info(f"Creating slide in presentation {presentation_id} for user {user_id}")

        request: dict[str, Any] = {"createSlide": {"insertionIndex": 1}}

        if slide_layout_reference:
            request["createSlide"]["slideLayoutReference"] = {"layoutId": slide_layout_reference}

        result = await self.batch_update_presentation(presentation_id, [request], user_id)

        if result.get("success", False):
            # Extract slide info from reply
            replies = result.get("replies", [])
            if replies and "createSlide" in replies[0]:
                slide_info = replies[0]["createSlide"]
                result["slide_id"] = slide_info.get("objectId", "")

        return result

    async def add_text_to_slide(
        self, presentation_id: str, slide_id: str, text: str, user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Add text to a slide in a Google Slides presentation.

        Args:
            presentation_id: The Google Slides presentation ID
            slide_id: The slide ID to add text to
            text: Text to add
            user_id: User identifier for credentials

        Returns:
            Dictionary containing text addition results
        """
        logger.info(
            f"Adding text to slide {slide_id} in presentation {presentation_id} for user {user_id}"
        )

        # First, create a text box
        text_box_id = f"textbox_{slide_id}_{len(text)}"

        requests: list[dict[str, Any]] = [
            {
                "createShape": {
                    "objectId": text_box_id,
                    "shapeType": "TEXT_BOX",
                    "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {
                            "height": {"magnitude": 200, "unit": "PT"},
                            "width": {"magnitude": 400, "unit": "PT"},
                        },
                        "transform": {
                            "scaleX": 1,
                            "scaleY": 1,
                            "translateX": 100,
                            "translateY": 100,
                            "unit": "PT",
                        },
                    },
                }
            },
            {"insertText": {"objectId": text_box_id, "insertionIndex": 0, "text": text}},
        ]

        result = await self.batch_update_presentation(presentation_id, requests, user_id)

        if result.get("success", False):
            result["text_box_id"] = text_box_id
            result["text"] = text

        return result

    async def replace_text_in_presentation(
        self, presentation_id: str, find_text: str, replace_text: str, user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Replace all occurrences of text in a Google Slides presentation.

        Args:
            presentation_id: The Google Slides presentation ID
            find_text: Text to find and replace
            replace_text: Text to replace with
            user_id: User identifier for credentials

        Returns:
            Dictionary containing replace results
        """
        logger.info(
            f"Replacing text in presentation {presentation_id}: '{find_text}' -> "
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

        return await self.batch_update_presentation(presentation_id, requests, user_id)

    async def duplicate_slide(
        self, presentation_id: str, slide_id: str, user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Duplicate a slide in a Google Slides presentation.

        Args:
            presentation_id: The Google Slides presentation ID
            slide_id: The slide ID to duplicate
            user_id: User identifier for credentials

        Returns:
            Dictionary containing duplication results
        """
        logger.info(
            f"Duplicating slide {slide_id} in presentation {presentation_id} for user {user_id}"
        )

        requests = [{"duplicateObject": {"objectId": slide_id}}]

        result = await self.batch_update_presentation(presentation_id, requests, user_id)

        if result.get("success", False):
            # Extract duplicated slide info from reply
            replies = result.get("replies", [])
            if replies and "duplicateObject" in replies[0]:
                duplicate_info = replies[0]["duplicateObject"]
                result["duplicated_slide_id"] = duplicate_info.get("objectId", "")

        return result

    async def delete_slide(
        self, presentation_id: str, slide_id: str, user_id: str = "default_user"
    ) -> dict[str, Any]:
        """
        Delete a slide from a Google Slides presentation.

        Args:
            presentation_id: The Google Slides presentation ID
            slide_id: The slide ID to delete
            user_id: User identifier for credentials

        Returns:
            Dictionary containing deletion results
        """
        logger.info(
            f"Deleting slide {slide_id} from presentation {presentation_id} for user {user_id}"
        )

        requests = [{"deleteObject": {"objectId": slide_id}}]

        return await self.batch_update_presentation(presentation_id, requests, user_id)
