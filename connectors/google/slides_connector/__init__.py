"""Google Slides connector module for Google Slides API integration."""

from .slides_service_async import SlidesServiceAsync
from .slides_tool import SlidesConnectorTool

__all__ = ["SlidesServiceAsync", "SlidesConnectorTool"]
