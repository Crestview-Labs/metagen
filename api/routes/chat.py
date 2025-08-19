"""Chat API routes."""

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agents.agent_manager import AgentManager
from common.messages import ApprovalResponseMessage, UserMessage

from ..models.chat import ApprovalResponse, ChatRequest

logger = logging.getLogger(__name__)

chat_router = APIRouter()


def get_manager(request: Request) -> AgentManager:
    """Get AgentManager from app state."""
    if not hasattr(request.app.state, "manager"):
        raise HTTPException(status_code=503, detail="AgentManager not initialized")

    manager = request.app.state.manager
    if manager is None:
        raise HTTPException(status_code=503, detail="AgentManager not initialized")

    if not manager._initialized:
        raise HTTPException(status_code=503, detail="AgentManager not ready")

    return manager  # type: ignore[no-any-return]


@chat_router.post("/chat/approval-response")
async def handle_approval_response(
    request: Request, approval: ApprovalResponseMessage
) -> ApprovalResponse:
    """Handle tool approval response."""
    logger.info(f"🔧 Received approval response for tool {approval.tool_id}: {approval.decision}")

    manager = get_manager(request)

    try:
        # Forward the approval to the manager
        await manager.handle_tool_approval_response(approval)

        return ApprovalResponse(
            tool_id=approval.tool_id,
            decision=approval.decision,
            message="Approval processed successfully",
        )
    except Exception as e:
        logger.error(f"❌ Error handling approval response: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process approval: {str(e)}")


@chat_router.post("/chat/stream")
async def chat_stream(request: Request, chat_request: ChatRequest) -> StreamingResponse:
    """Stream chat responses as they are generated."""
    logger.info(f"[API ENDPOINT] /chat/stream called with {chat_request}")

    async def generate_stream() -> AsyncGenerator[str, None]:
        try:
            # Convert to Message object
            message = chat_request.to_message()

            # Get message preview for logging
            if isinstance(message, UserMessage):
                msg_preview = message.content[:100]
            elif isinstance(message, ApprovalResponseMessage):
                # TODO: Remove this case - ApprovalResponseMessage should NEVER come through
                # /chat/stream. It doesn't work correctly (gets treated as regular message)
                # and we have a dedicated /api/chat/approval-response endpoint for this.
                # Keeping for now to avoid breaking changes, but should be removed.
                msg_preview = f"Approval: {message.decision} for {message.tool_id}"
            else:
                msg_preview = str(message)[:100]

            logger.info(f"Stream chat request: {msg_preview}...")

            manager = get_manager(request)

            # Stream responses from agent
            message_count = 0
            async for response in manager.chat_stream(message):
                message_count += 1
                # Convert Message to JSON and yield
                # Each message type has specific fields we need to serialize
                response_dict = response.to_dict()

                # Ensure metadata field exists
                if "metadata" not in response_dict:
                    response_dict["metadata"] = {}

                # Handle timestamp conversion - it might be a datetime or already a string
                if "timestamp" in response_dict and response_dict["timestamp"]:
                    timestamp = response_dict["timestamp"]
                    if hasattr(timestamp, "isoformat"):
                        response_dict["timestamp"] = timestamp.isoformat()
                    # If it's already a string, leave it as is

                yield f"data: {json.dumps(response_dict)}\n\n"

                # No need for separate completion signal - AgentMessage.final indicates completion

        except asyncio.CancelledError:
            # Client disconnected - this is normal behavior
            logger.info("🔌 Client disconnected from stream")
            raise  # Re-raise to properly clean up the connection
        except Exception as e:
            logger.error(f"❌ Stream chat error: {str(e)}", exc_info=True)
            # Use proper ErrorMessage
            from common.messages import ErrorMessage

            error_msg = ErrorMessage(
                agent_id="SYSTEM",
                session_id=chat_request.session_id or "",
                error=f"Stream error: {str(e)}",
            )
            yield f"data: {json.dumps(error_msg.to_dict())}\n\n"
        finally:
            logger.info(f"🏁 Stream completed for session: {chat_request.session_id}")
            # Don't unregister session here - the agent might still be processing
            # Session will be cleaned up when agent sends final message or after timeout

    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        },
    )
