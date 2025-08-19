"""Chat-related API models."""

import uuid
from typing import Optional, Union

from pydantic import BaseModel, Field

from common.messages import ApprovalDecision, ApprovalResponseMessage, Message, UserMessage


class ChatRequest(BaseModel):
    """Request to send a message to the agent."""

    # TODO: Remove ApprovalResponseMessage from the Union type.
    # ApprovalResponseMessage should ONLY go through /api/chat/approval-response endpoint.
    # When sent through /chat/stream, it doesn't work correctly (gets routed as regular message).
    # Keeping for backward compatibility but should be removed in next major version.
    message: Union[str, UserMessage, ApprovalResponseMessage] = Field(
        description="Message to send to the agent - can be a string or a Message object"
    )
    session_id: str = Field(description="Session identifier for request routing")

    def to_message(self) -> Message:
        """Convert to appropriate Message type."""
        if isinstance(self.message, str):
            # Use session_id from request if provided, otherwise generate a new one
            session_id = self.session_id or str(uuid.uuid4())
            return UserMessage(agent_id="METAGEN", session_id=session_id, content=self.message)
        else:
            # Ensure message objects also have a session_id
            if not self.message.session_id:
                self.message.session_id = self.session_id or str(uuid.uuid4())
            return self.message


class ApprovalResponse(BaseModel):
    """Response from the approval endpoint."""

    tool_id: str = Field(description="ID of the tool that was approved/rejected")
    decision: ApprovalDecision = Field(description="The approval decision that was processed")
    message: Optional[str] = Field(
        default="Approval processed successfully", description="Optional status message"
    )
