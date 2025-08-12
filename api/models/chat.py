"""Chat-related API models."""

from typing import Optional, Union

from pydantic import BaseModel, Field

from common.messages import ApprovalDecision, ApprovalResponseMessage, Message, UserMessage


class ChatRequest(BaseModel):
    """Request to send a message to the agent."""

    message: Union[str, UserMessage, ApprovalResponseMessage] = Field(
        description="Message to send to the agent - can be a string or a Message object"
    )
    session_id: Optional[str] = None

    def to_message(self) -> Message:
        """Convert to appropriate Message type."""
        if isinstance(self.message, str):
            return UserMessage(content=self.message)
        else:
            return self.message


class ApprovalResponse(BaseModel):
    """Response from the approval endpoint."""

    tool_id: str = Field(description="ID of the tool that was approved/rejected")
    decision: ApprovalDecision = Field(description="The approval decision that was processed")
    message: Optional[str] = Field(
        default="Approval processed successfully", description="Optional status message"
    )
