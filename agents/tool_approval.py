"""Tool approval communication structures for UI/CLI interaction."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ToolApprovalDecision(str, Enum):
    """Tool approval decisions."""

    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"


@dataclass
class ToolApprovalRequest:
    """Request for tool approval sent to UI/CLI."""

    tool_id: str  # Unique ID for this tool call
    tool_name: str  # Name of the tool
    tool_args: dict[str, Any]  # Arguments for the tool
    agent_id: str  # Which agent is requesting
    description: Optional[str] = None  # Human-readable description of what tool will do
    risk_level: Optional[str] = None  # "low", "medium", "high"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "agent_id": self.agent_id,
            "description": self.description,
            "risk_level": self.risk_level,
        }


@dataclass
class ToolApprovalResponse:
    """Response from UI/CLI for tool approval."""

    tool_id: str  # Must match the request tool_id
    decision: ToolApprovalDecision  # approved/rejected/timeout
    feedback: Optional[str] = None  # User feedback if rejected
    approved_by: Optional[str] = None  # User ID or "system" for auto-approvals

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolApprovalResponse":
        """Create from dictionary."""
        return cls(
            tool_id=data["tool_id"],
            decision=ToolApprovalDecision(data["decision"]),
            feedback=data.get("feedback"),
            approved_by=data.get("approved_by"),
        )

    @classmethod
    def approve(cls, tool_id: str, approved_by: str = "user") -> "ToolApprovalResponse":
        """Create an approval response."""
        return cls(tool_id=tool_id, decision=ToolApprovalDecision.APPROVED, approved_by=approved_by)

    @classmethod
    def reject(
        cls, tool_id: str, feedback: str, approved_by: str = "user"
    ) -> "ToolApprovalResponse":
        """Create a rejection response."""
        return cls(
            tool_id=tool_id,
            decision=ToolApprovalDecision.REJECTED,
            feedback=feedback,
            approved_by=approved_by,
        )

    @classmethod
    def timeout(cls, tool_id: str) -> "ToolApprovalResponse":
        """Create a timeout response."""
        return cls(
            tool_id=tool_id,
            decision=ToolApprovalDecision.TIMEOUT,
            feedback="Approval request timed out",
            approved_by="system",
        )


@dataclass
class ToolPendingApproval:
    """Track pending tool approval state."""

    tool_id: str  # Unique ID for this tool call
    tool_name: str  # Name of the tool
    tool_args: dict[str, Any]  # Arguments for the tool
    turn_id: Optional[str]  # Conversation turn ID
    trace_id: Optional[str]  # Tracing ID
    tool_usage_id: Optional[str]  # Database ID for tool usage record
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Original event data for re-execution
    original_event: Any = None  # The original tool call event

    def is_expired(self, timeout_seconds: float = 30.0) -> bool:
        """Check if this approval request has expired."""
        elapsed = (datetime.utcnow() - self.created_at).total_seconds()
        return elapsed > timeout_seconds
