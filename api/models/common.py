"""Common API models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    error_type: Optional[str] = None
    timestamp: datetime = datetime.now()


class SuccessResponse(BaseModel):
    """Standard success response."""

    message: str
    data: Optional[dict[str, Any]] = None
    timestamp: datetime = datetime.now()
