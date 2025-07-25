#!/usr/bin/env python3
"""Main entry point for metagen FastAPI backend server."""

import logging
import signal
import sys
from typing import Any

import uvicorn

from api.server import app  # noqa: F401 - Used by uvicorn

# TODO: Fix subprocess signal handling for proper Ctrl-C behavior
# The MCP SDK's stdio_client doesn't properly propagate signals to subprocesses.
# This is a known limitation. Need to implement proper process group management
# or use a process supervisor that kills the entire process tree.

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Set aiosqlite to INFO level to reduce noise
logging.getLogger("aiosqlite").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


def signal_handler(sig: Any, frame: Any) -> None:
    """Handle shutdown signals gracefully."""
    logger.info("\n🛑 Shutdown signal received. Cleaning up...")
    sys.exit(0)


def main() -> None:
    """Run the FastAPI server."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("🚀 Starting Metagen Backend Server...")

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8080,
        reload=False,  # Disable auto-reload for better signal handling
        log_level="debug",
    )


if __name__ == "__main__":
    main()
