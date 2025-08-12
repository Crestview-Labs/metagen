#!/usr/bin/env python3
"""Main entry point for metagen FastAPI backend server."""

import argparse
import logging
import os
import signal
import sys
from pathlib import Path
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
    logger.info("\nShutdown signal received. Cleaning up...")
    sys.exit(0)


def main() -> None:
    """Run the FastAPI server."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Metagen Backend Server")
    parser.add_argument(
        "--db-path",
        type=str,
        default="./db/metagen.db",
        help="Path to the SQLite database file (default: ./db/metagen.db)",
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port to run the server on (default: 8080)"
    )
    args = parser.parse_args()

    # Set the database path in environment variable for the app to use
    db_path = Path(args.db_path)
    os.environ["METAGEN_DB_PATH"] = str(db_path)

    # Ensure the directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Starting Metagen Backend Server...")
    logger.info(f"Database path: {db_path}")
    logger.info(f"Port: {args.port}")

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=args.port,
        reload=False,  # Disable auto-reload for better signal handling
        log_level="debug",
    )


if __name__ == "__main__":
    main()
