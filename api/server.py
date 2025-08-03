"""Main FastAPI server for metagen backend."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Optional

# Logging is configured in main.py
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agents.agent_manager import AgentManager
from config import TOOL_APPROVAL_CONFIG
from db import get_db_engine
from telemetry import init_telemetry

from .routes.auth import auth_router
from .routes.chat import chat_router
from .routes.memory import router as memory_router
from .routes.system import system_router
from .routes.telemetry import router as telemetry_router
from .routes.tools import tools_router

logger = logging.getLogger(__name__)

# Global manager instance
manager: Optional[AgentManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan context manager."""
    global manager

    logger.info("🚀 Starting metagen backend server...")

    # Initialize DatabaseEngine first
    db_engine = get_db_engine()
    await db_engine.initialize()
    logger.info("✅ Database initialized")

    # Initialize OpenTelemetry with db_engine
    try:
        init_telemetry(service_name="metagen-api", enable_console=False, db_engine=db_engine)
        logger.info("✅ OpenTelemetry initialized")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize telemetry: {e}")

    # Initialize AgentManager with db_engine
    try:
        manager = AgentManager(
            agent_name="MetaAgent", db_engine=db_engine, mcp_servers=["tools/mcp_server.py"]
        )

        response = await manager.initialize()
        if response.type.value == "error":
            logger.error(f"Failed to initialize AgentManager: {response.content}")
            raise Exception(f"Manager initialization failed: {response.content}")

        logger.info("✅ AgentManager initialized successfully")

        # Configure tool approval from centralized config
        if TOOL_APPROVAL_CONFIG["require_approval"]:
            manager.configure_tool_approval(
                require_approval=True, auto_approve_tools=TOOL_APPROVAL_CONFIG["auto_approve_tools"]
            )
            logger.info(
                f"🔐 Tool approval configured: "
                f"auto_approve={TOOL_APPROVAL_CONFIG['auto_approve_tools'][:3]}..."
            )

        # Store manager reference for routes
        app.state.manager = manager

        yield

    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise
    finally:
        # Cleanup
        if manager:
            logger.info("🧹 Cleaning up AgentManager...")
            await manager.cleanup()
            logger.info("✅ AgentManager cleanup complete")

        # Close database connections
        await db_engine.close()
        logger.info("✅ Database connections closed")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

    app = FastAPI(
        title="Metagen Backend API",
        description="HTTP API for Metagen superintelligent personal agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add CORS middleware for TypeScript CLI communication
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # In production, restrict this
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Add OpenTelemetry FastAPI instrumentation
    # Note: This must be done AFTER all routes are added
    # FastAPIInstrumentor.instrument_app(app)

    # Add global exception handlers
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle all unhandled exceptions."""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An internal error occurred. Please try again later.",
                "error_type": type(exc).__name__,
                "path": str(request.url.path),
            },
        )

    # Include routers
    app.include_router(chat_router, prefix="/api", tags=["chat"])
    app.include_router(auth_router, prefix="/api", tags=["authentication"])
    app.include_router(tools_router, prefix="/api", tags=["tools"])
    app.include_router(system_router, prefix="/api", tags=["system"])
    app.include_router(memory_router, tags=["memory"])
    app.include_router(telemetry_router, tags=["telemetry"])

    @app.get("/")
    async def root() -> dict[str, str]:
        """Root endpoint."""
        return {"message": "Metagen Backend API", "version": "0.1.0", "status": "running"}

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Health check endpoint with detailed status."""
        health_status: dict[str, Any] = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {},
        }

        # Check AgentManager
        if hasattr(app.state, "manager") and app.state.manager._initialized:
            manager = app.state.manager

            # Get MCP server health
            mcp_servers_health = []
            for server in manager.mcp_servers_instances:
                mcp_servers_health.append(server.get_health_status())

            health_status["components"]["agent_manager"] = {  # type: ignore[index]
                "status": "healthy",
                "agents": {
                    "meta_agent": "running" if manager.meta_agent else "not_initialized",
                    "task_agent": "running" if manager.task_agent else "not_initialized",
                },
                "mcp_servers": {
                    "count": len(manager.mcp_servers_instances),
                    "servers": mcp_servers_health,
                },
            }
        else:
            health_status["components"]["agent_manager"] = {"status": "not_initialized"}

        # Check database
        try:
            db_engine = get_db_engine()
            db_health = await db_engine.check_health()

            health_status["components"]["database"] = {
                "status": "healthy" if db_health["healthy"] else "unhealthy",
                "path": db_health["database_path"],
                "size_mb": db_health["database_size_mb"],
                "table_count": db_health.get("table_count", 0),
                "last_check": db_health["last_check"],
                "errors": db_health["errors"],
            }
        except Exception as e:
            health_status["components"]["database"] = {"status": "error", "error": str(e)}

        # Overall status
        if any(comp.get("status") != "healthy" for comp in health_status["components"].values()):
            health_status["status"] = "degraded"

        return health_status

    return app


# Create the application instance
app = create_app()
