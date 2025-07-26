"""Chat API routes."""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agents.agent_manager import AgentManager, UIResponse
from agents.tool_approval import ToolApprovalDecision, ToolApprovalResponse

from ..models.chat import ChatRequest, ChatResponse, UIResponseModel

logger = logging.getLogger(__name__)

chat_router = APIRouter()


def get_manager(request: Request) -> AgentManager:
    """Get AgentManager from app state."""
    if not hasattr(request.app.state, "manager"):
        raise HTTPException(status_code=503, detail="AgentManager not initialized")

    manager = request.app.state.manager
    if not manager._initialized:
        raise HTTPException(status_code=503, detail="AgentManager not ready")

    return manager  # type: ignore[no-any-return]


@chat_router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, chat_request: ChatRequest) -> ChatResponse:
    """Send a message to the agent and get response."""
    try:
        logger.info(f"💬 Chat request: {chat_request.message[:100]}...")

        _ = get_manager(request)  # TODO: Use manager when chat method is implemented

        # Send message to agent
        # TODO: Fix AgentManager.chat method - it doesn't exist
        ui_responses: list[UIResponse] = []

        # Convert UIResponse objects to Pydantic models
        response_models = [UIResponseModel.from_ui_response(response) for response in ui_responses]

        logger.info(f"✅ Chat completed with {len(response_models)} responses")

        return ChatResponse(
            responses=response_models, session_id=chat_request.session_id, success=True
        )

    except Exception as e:
        logger.error(f"❌ Chat error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat processing failed: {str(e)}")


@chat_router.post("/chat/stream")
async def chat_stream(request: Request, chat_request: ChatRequest) -> StreamingResponse:
    """Stream chat responses as they are generated."""

    async def generate_stream() -> AsyncGenerator[str, None]:
        try:
            logger.info(f"🌊 Stream chat request: {chat_request.message[:100]}...")
            logger.debug(f"🔍 Full chat request: {chat_request}")

            manager = get_manager(request)

            # Stream responses from agent
            async for response in manager.chat_stream(chat_request.message):
                # Convert UIResponse to JSON and yield
                response_data = {
                    "type": response.type.value,
                    "content": response.content,
                    "metadata": response.metadata or {},
                    "timestamp": response.timestamp.isoformat() if response.timestamp else None,
                }

                yield f"data: {json.dumps(response_data)}\n\n"

            # Send completion signal
            completion_data = {"type": "complete", "session_id": chat_request.session_id}
            yield f"data: {json.dumps(completion_data)}\n\n"

        except asyncio.CancelledError:
            # Client disconnected - this is normal behavior
            logger.info("🔌 Client disconnected from stream")
            raise  # Re-raise to properly clean up the connection
        except Exception as e:
            logger.error(f"❌ Stream chat error: {str(e)}", exc_info=True)
            error_response: dict[str, Any] = {
                "type": "error",
                "content": f"Stream error: {str(e)}",
                "metadata": {},
                "timestamp": None,
            }
            yield f"data: {json.dumps(error_response)}\n\n"
        finally:
            logger.info(f"🏁 Stream completed for session: {chat_request.session_id}")

    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        },
    )


@chat_router.post("/tool-decision")
async def tool_decision(request: Request, decision_data: dict[str, Any]) -> dict[str, Any]:
    """Handle tool approval/rejection decision from UI/CLI.

    Expected payload:
    {
        "tool_id": "uuid",
        "decision": "approved" | "rejected",
        "feedback": "optional feedback if rejected",
        "approved_by": "user_id or 'user'"
    }
    """
    try:
        logger.info(f"🔨 Tool decision received: {decision_data}")

        # Validate required fields
        if "tool_id" not in decision_data or "decision" not in decision_data:
            raise HTTPException(
                status_code=400, detail="Missing required fields: tool_id and decision"
            )

        # Create ToolApprovalResponse
        try:
            approval_response = ToolApprovalResponse(
                tool_id=decision_data["tool_id"],
                decision=ToolApprovalDecision(decision_data["decision"]),
                feedback=decision_data.get("feedback"),
                approved_by=decision_data.get("approved_by", "user"),
            )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid decision value: {decision_data['decision']}. "
                    "Must be 'approved' or 'rejected'"
                ),
            )

        # Get manager and send approval response
        manager = get_manager(request)
        await manager.handle_tool_approval_response(approval_response)

        logger.info(f"✅ Tool decision processed for {approval_response.tool_id}")

        return {
            "success": True,
            "tool_id": approval_response.tool_id,
            "decision": approval_response.decision.value,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Tool decision error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Tool decision processing failed: {str(e)}")


@chat_router.get("/pending-tools")
async def get_pending_tools(request: Request) -> dict[str, Any]:
    """Get list of tools pending approval."""
    try:
        manager = get_manager(request)

        # Get pending approvals from memory manager
        if not hasattr(manager, "memory_manager") or not manager.memory_manager:
            return {"success": True, "pending_tools": []}

        pending = await manager.memory_manager.get_pending_approvals()

        # Convert to API response format
        pending_list = [
            {
                "tool_id": tool.id,
                "tool_name": tool.tool_name,
                "tool_args": tool.tool_args,
                "entity_id": tool.entity_id,
                "created_at": tool.created_at.isoformat() if tool.created_at else None,
                "requires_approval": tool.requires_approval,
            }
            for tool in pending
        ]

        logger.info(f"📋 Found {len(pending_list)} pending tools")

        return {"success": True, "pending_tools": pending_list, "count": len(pending_list)}

    except Exception as e:
        logger.error(f"❌ Get pending tools error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get pending tools: {str(e)}")
