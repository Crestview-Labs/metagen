"""Memory management API routes."""

import logging

from fastapi import APIRouter, HTTPException, Request

from agents.agent_manager import AgentManager
from telemetry import get_memory_exporter, get_sqlite_exporter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"])


def get_manager(request: Request) -> AgentManager:
    """Get AgentManager from app state."""
    if not hasattr(request.app.state, "manager"):
        raise HTTPException(status_code=503, detail="AgentManager not initialized")
    return request.app.state.manager  # type: ignore[no-any-return]


@router.post("/clear")
async def clear_history(request: Request) -> dict[str, str]:
    """Clear all conversation history and telemetry data from the database."""
    try:
        logger.info("🗄️ Clearing all database tables...")

        # Get the AgentManager to access memory manager
        agent_manager = get_manager(request)

        # Clear conversation history through the memory manager
        if agent_manager.memory_manager:
            conversation_count = await agent_manager.memory_manager.clear_all_conversations()
            logger.info(f"✅ Cleared {conversation_count} conversation turns")
        else:
            logger.warning("⚠️ Memory manager not initialized")
            conversation_count = 0

        # Clear telemetry data through the telemetry module
        sqlite_exporter = get_sqlite_exporter()
        if sqlite_exporter:
            telemetry_count = await sqlite_exporter.clear_all_spans()
            logger.info(f"✅ Cleared {telemetry_count} telemetry spans")
        else:
            logger.warning("⚠️ SQLite telemetry not initialized")
            telemetry_count = 0

        # Clear in-memory telemetry
        try:
            memory_exporter = get_memory_exporter()
            if memory_exporter:
                memory_exporter.spans.clear()
                logger.info("✅ Cleared in-memory telemetry spans")
        except Exception as e:
            logger.warning(f"⚠️ Failed to clear in-memory telemetry: {e}")

        return {
            "message": "Database cleared successfully",
            "conversation_turns_deleted": str(conversation_count),
            "telemetry_spans_deleted": str(telemetry_count),
        }

    except Exception as e:
        logger.error(f"❌ Failed to clear database: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear database: {str(e)}")
