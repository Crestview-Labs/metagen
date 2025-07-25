"""System-related API models."""

from typing import Any

from pydantic import BaseModel


class ToolInfo(BaseModel):
    """Information about an available tool."""

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolsResponse(BaseModel):
    """Tools listing response."""

    tools: list[ToolInfo]
    count: int


class SystemInfo(BaseModel):
    """System information response."""

    agent_name: str
    model: str
    tools: list[ToolInfo]
    tool_count: int
    memory_path: str
    initialized: bool
