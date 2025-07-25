"""MCP Server management - spawns and manages MCP server subprocesses."""

import asyncio
import logging
import os
import time
from contextlib import AsyncExitStack
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class MCPServer:
    """
    Manages MCP server subprocess lifecycle.

    Responsibilities:
    - Spawn and manage MCP server subprocess
    - Handle server initialization and cleanup
    - Provide connection interface for MCPClient
    - Manage environment variables and configuration
    """

    def __init__(
        self,
        server_path: str,
        db_path: Optional[str] = None,
        env_vars: Optional[dict[str, str]] = None,
    ):
        """
        Initialize MCP server manager.

        Args:
            server_path: Path to MCP server script (e.g., "tools/mcp_server.py")
            db_path: Database path to pass to server via METAGEN_DB_PATH
            env_vars: Additional environment variables to pass to server
        """
        self.server_path = server_path
        self.db_path = db_path
        self.env_vars = env_vars or {}

        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self._initialized = False
        self._tools_cache: list[dict[str, Any]] = []
        self._last_health_check: float = 0
        self._health_check_interval: float = 30.0  # Check every 30 seconds
        self._restart_count: int = 0
        self._max_restarts: int = 5
        self._health_check_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the MCP server subprocess and establish connection."""
        if self._initialized:
            return

        logger.info(f"🔍 DEBUG: Starting MCP server: {self.server_path}")

        # Determine command based on file extension
        is_python = self.server_path.endswith(".py")
        is_js = self.server_path.endswith(".js")

        if not (is_python or is_js):
            raise ValueError(f"Unsupported server type: {self.server_path}")

        # Build command and environment
        if is_python:
            command = "uv"
            # Run as module to fix import paths
            if self.server_path == "tools/mcp_server.py":
                args = ["run", "python", "-m", "tools.mcp_server"]
            else:
                args = ["run", "python", self.server_path]
            env = self._build_python_env()
            logger.info(f"🔍 DEBUG: Python command: {command} {' '.join(args)}")
        else:
            command = "node"
            args = [self.server_path]
            env = None
            logger.info(f"🔍 DEBUG: Node command: {command} {' '.join(args)}")

        server_params = StdioServerParameters(command=command, args=args, env=env)

        try:
            # Connect to MCP server
            logger.info("🔍 DEBUG: Connecting to MCP server with params:")
            logger.info(f"🔍 DEBUG: Command: {command}")
            logger.info(f"🔍 DEBUG: Args: {args}")
            logger.info(f"🔍 DEBUG: Working directory: {os.getcwd()}")
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            logger.info("🔍 DEBUG: Got stdio transport")
            stdio, write = stdio_transport
            session = await self.exit_stack.enter_async_context(ClientSession(stdio, write))
            logger.info("🔍 DEBUG: Created client session")

            await session.initialize()
            logger.info("🔍 DEBUG: Session initialized")
            self.session = session

            # Cache available tools
            logger.info("🔍 DEBUG: Listing tools...")
            response = await session.list_tools()
            logger.info(f"🔍 DEBUG: Got {len(response.tools)} tools")
            self._tools_cache = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                for tool in response.tools
            ]

            self._initialized = True
            self._last_health_check = time.time()
            logger.info(f"MCP server started with {len(self._tools_cache)} tools")

            # Start health monitoring task
            self._health_check_task = asyncio.create_task(self._health_monitor())
            logger.info(f"Started health monitoring for {self.server_path}")

        except Exception as e:
            logger.error(f"Failed to start MCP server {self.server_path}: {e}")
            await self.stop()
            raise

    def _build_python_env(self) -> dict[str, str]:
        """Build environment variables for Python MCP server."""
        env = os.environ.copy()

        # Add current directory to PYTHONPATH for module imports
        current_dir = os.getcwd()
        pythonpath = env.get("PYTHONPATH", "")
        if pythonpath:
            env["PYTHONPATH"] = f"{current_dir}:{pythonpath}"
        else:
            env["PYTHONPATH"] = current_dir

        # Add database path if provided
        if self.db_path:
            env["METAGEN_DB_PATH"] = self.db_path
            logger.info(f"Setting METAGEN_DB_PATH={self.db_path} for MCP server")

        # Add any additional environment variables
        env.update(self.env_vars)

        return env

    async def _health_monitor(self) -> None:
        """Monitor MCP server health and restart if needed."""
        while self._initialized:
            try:
                await asyncio.sleep(self._health_check_interval)

                # Perform health check
                if not await self._check_health():
                    logger.warning(f"MCP server {self.server_path} health check failed")
                    await self._restart()
                else:
                    self._last_health_check = time.time()

            except asyncio.CancelledError:
                logger.info(f"Health monitor cancelled for {self.server_path}")
                break
            except Exception as e:
                logger.error(f"Error in health monitor for {self.server_path}: {e}")
                await asyncio.sleep(5)  # Short delay before retrying

    async def _check_health(self) -> bool:
        """Check if MCP server is healthy."""
        if not self._initialized or not self.session:
            return False

        try:
            # Try to list tools as a health check
            response = await asyncio.wait_for(self.session.list_tools(), timeout=5.0)
            return len(response.tools) > 0
        except Exception as e:
            logger.error(f"Health check failed for {self.server_path}: {e}")
            return False

    async def _restart(self) -> None:
        """Restart the MCP server."""
        if self._restart_count >= self._max_restarts:
            logger.error(
                f"MCP server {self.server_path} exceeded max restarts ({self._max_restarts})"
            )
            return

        self._restart_count += 1
        logger.info(
            f"Restarting MCP server {self.server_path} "
            f"(attempt {self._restart_count}/{self._max_restarts})"
        )

        # Stop the server
        await self._stop_internal()

        # Wait before restarting
        wait_time = min(30, 2**self._restart_count)
        logger.info(f"Waiting {wait_time} seconds before restart...")
        await asyncio.sleep(wait_time)

        try:
            # Start the server again
            await self.start()
            logger.info(f"Successfully restarted MCP server {self.server_path}")
            # Reset restart count on successful restart
            self._restart_count = 0
        except Exception as e:
            logger.error(f"Failed to restart MCP server {self.server_path}: {e}")

    async def _stop_internal(self) -> None:
        """Internal stop method that doesn't cancel health monitor."""
        logger.info(f"Stopping MCP server: {self.server_path}")

        try:
            await self.exit_stack.aclose()
        except (RuntimeError, Exception) as e:
            # Async context issues - let resources clean up naturally
            logger.warning(f"MCP server cleanup issue (non-critical): {e}")

        self.session = None
        self._initialized = False
        self._tools_cache = []

    async def stop(self) -> None:
        """Stop the MCP server and clean up resources."""
        if not self._initialized:
            return

        # Cancel health monitor task
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        await self._stop_internal()

    async def call_tool(self, tool_name: str, parameters: dict[str, Any]) -> Any:
        """Call a tool on this MCP server."""
        if not self._initialized or not self.session:
            raise RuntimeError("MCP server not started")

        logger.debug(f"Calling tool {tool_name} on server {self.server_path}")
        result = await self.session.call_tool(tool_name, parameters)
        return result

    def get_tools(self) -> list[dict[str, Any]]:
        """Get list of tools available on this server."""
        return self._tools_cache.copy()

    def has_tool(self, tool_name: str) -> bool:
        """Check if this server provides a specific tool."""
        return any(tool["name"] == tool_name for tool in self._tools_cache)

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._initialized and self.session is not None

    def get_health_status(self) -> dict[str, Any]:
        """Get detailed health status of the MCP server."""
        return {
            "server_path": self.server_path,
            "is_running": self.is_running,
            "tool_count": len(self._tools_cache),
            "restart_count": self._restart_count,
            "last_health_check": self._last_health_check,
            "seconds_since_health_check": time.time() - self._last_health_check
            if self._last_health_check > 0
            else None,
            "health_check_interval": self._health_check_interval,
            "max_restarts": self._max_restarts,
        }

    def __repr__(self) -> str:
        status = "running" if self.is_running else "stopped"
        tool_count = len(self._tools_cache)
        return (
            f"MCPServer({self.server_path}, {status}, "
            f"{tool_count} tools, restarts={self._restart_count})"
        )
