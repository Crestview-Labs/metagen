"""Tools API routes."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from agents.agent_manager import AgentManager

from ..models.system import ToolInfo, ToolsResponse

logger = logging.getLogger(__name__)

tools_router = APIRouter()


def get_manager(request: Request) -> AgentManager:
    """Get AgentManager from app state."""
    if not hasattr(request.app.state, "manager"):
        raise HTTPException(status_code=503, detail="AgentManager not initialized")

    manager = request.app.state.manager
    if not manager._initialized:
        raise HTTPException(status_code=503, detail="AgentManager not ready")

    return manager  # type: ignore[no-any-return]


@tools_router.get("/tools", response_model=ToolsResponse)
async def get_tools(request: Request) -> ToolsResponse:
    """Get list of available tools."""
    try:
        logger.info("🔧 Getting available tools...")

        manager = get_manager(request)

        # Get tools from MetaAgent
        if manager.meta_agent is None:
            raise HTTPException(status_code=503, detail="MetaAgent not initialized")

        tools_data = await manager.meta_agent.get_available_tools()

        # Convert to ToolInfo models
        tools = [
            ToolInfo(
                name=tool["name"],
                description=tool["description"],
                input_schema=tool["input_schema"],
            )
            for tool in tools_data
        ]

        result = ToolsResponse(tools=tools, count=len(tools))

        logger.info(f"🔧 Returning {len(tools)} tools")
        return result

    except Exception as e:
        logger.error(f"❌ Tools error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get tools: {str(e)}")


@tools_router.get("/tools/google")
async def get_google_tools(request: Request) -> dict[str, Any]:
    """Get list of Google-specific tools."""
    try:
        logger.info("🔧 Getting Google tools...")

        manager = get_manager(request)

        # Get all tools and filter for Google ones
        if manager.meta_agent is None:
            raise HTTPException(status_code=503, detail="MetaAgent not initialized")

        tools_data = await manager.meta_agent.get_available_tools()
        google_tools = [
            tool
            for tool in tools_data
            if any(service in tool["name"] for service in ["gmail", "drive", "calendar"])
        ]

        result = {
            "count": len(google_tools),
            "tools": google_tools,
            "services": {
                "gmail": [t for t in google_tools if "gmail" in t["name"]],
                "drive": [t for t in google_tools if "drive" in t["name"]],
                "calendar": [t for t in google_tools if "calendar" in t["name"]],
            },
        }

        logger.info(f"🔧 Returning {len(google_tools)} Google tools")
        return result

    except Exception as e:
        logger.error(f"❌ Google tools error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get Google tools: {str(e)}")
