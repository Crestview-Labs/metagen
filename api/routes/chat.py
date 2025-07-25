"""Chat API routes."""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agents.agent_manager import AgentManager, UIResponse

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
