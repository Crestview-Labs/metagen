"""Tool approval tracking structures for internal agent use."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ToolPendingApproval:
    """Track pending tool approval state."""

    tool_id: str  # Unique ID for this tool call
    tool_name: str  # Name of the tool
    tool_args: dict[str, Any]  # Arguments for the tool
    turn_id: Optional[str]  # Conversation turn ID
    tool_usage_id: Optional[str]  # Database ID for tool usage record
    created_at: datetime = field(default_factory=datetime.utcnow)
