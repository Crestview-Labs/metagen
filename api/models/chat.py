"""Chat-related API models."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from agents.agent_manager import UIResponse


class ChatRequest(BaseModel):
    """Request to send a message to the agent."""

    message: str
    session_id: Optional[str] = None


class UIResponseModel(BaseModel):
    """Pydantic model for UIResponse."""

    type: str
    content: str
    agent_id: str
    metadata: Optional[dict[str, Any]] = None
    timestamp: datetime

    @classmethod
    def from_ui_response(cls, ui_response: UIResponse) -> "UIResponseModel":
        """Convert UIResponse to Pydantic model."""
        return cls(
            type=ui_response.type.value,
            content=ui_response.content,
            agent_id=ui_response.agent_id,
            metadata=ui_response.metadata,
            timestamp=ui_response.timestamp or datetime.now(),
        )


class ChatResponse(BaseModel):
    """Response from agent chat."""

    responses: list[UIResponseModel]
    session_id: Optional[str] = None
    success: bool = True
