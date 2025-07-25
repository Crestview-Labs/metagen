"""System API routes."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from agents.agent_manager import AgentManager

from ..models.system import SystemInfo, ToolInfo

logger = logging.getLogger(__name__)

system_router = APIRouter()


def get_manager(request: Request) -> AgentManager:
    """Get AgentManager from app state."""
    if not hasattr(request.app.state, "manager"):
        raise HTTPException(status_code=503, detail="AgentManager not initialized")

    manager = request.app.state.manager
    if not manager._initialized:
        raise HTTPException(status_code=503, detail="AgentManager not ready")

    return manager  # type: ignore[no-any-return]


@system_router.get("/system/info", response_model=SystemInfo)
async def get_system_info(request: Request) -> SystemInfo:
    """Get system information."""
    try:
        logger.info("📊 Getting system information...")

        manager = get_manager(request)

        # Get system info from AgentManager
        response = await manager.get_system_info()

        if response.type.value == "error":
            raise HTTPException(status_code=500, detail=response.content)

        # Extract information
        agent_info = response.metadata.get("agent_info", {}) if response.metadata else {}
        model = response.metadata.get("model", "unknown") if response.metadata else "unknown"
        tools_data = response.metadata.get("tools", []) if response.metadata else []

        # Convert tools to ToolInfo models
        tools = []
        if tools_data:
            # Get full tool info from current agent
            current_agent = manager._get_current_agent()
            full_tools = await current_agent.get_available_tools()
            tools = [
                ToolInfo(
                    name=tool["name"],
                    description=tool["description"],
                    input_schema=tool["input_schema"],
                )
                for tool in full_tools
            ]

        assert manager.memory_manager is not None, "Memory manager must be initialized"
        memory_path = str(manager.memory_manager.storage.db_path)  # type: ignore[attr-defined]
        assert memory_path is not None, "Memory path must not be None"

        system_info = SystemInfo(
            agent_name=agent_info.get("name", manager.agent_name),
            model=model,
            tools=tools,
            tool_count=len(tools),
            memory_path=memory_path,
            initialized=manager._initialized,
        )

        logger.info(f"📊 System info: {system_info.agent_name}, {system_info.tool_count} tools")
        return system_info

    except Exception as e:
        logger.error(f"❌ System info error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get system info: {str(e)}")


@system_router.get("/system/health")
async def health_check(request: Request) -> dict[str, Any]:
    """Detailed health check."""
    try:
        manager_available = hasattr(request.app.state, "manager")
        manager_initialized = False
        tools_count = 0

        if manager_available:
            manager = request.app.state.manager
            manager_initialized = manager._initialized

            if manager_initialized:
                try:
                    current_agent = manager._get_current_agent()
                    tools = await current_agent.get_available_tools()
                    tools_count = len(tools)
                except Exception:
                    pass

        return {
            "status": "healthy" if manager_initialized else "degraded",
            "components": {
                "manager": "available" if manager_available else "missing",
                "agent": "initialized" if manager_initialized else "not_ready",
                "tools": f"{tools_count} available" if tools_count > 0 else "not_available",
            },
            "timestamp": "2025-06-28",
        }

    except Exception as e:
        logger.error(f"❌ Health check error: {str(e)}")
        return {"status": "unhealthy", "error": str(e), "timestamp": "2025-06-28"}
