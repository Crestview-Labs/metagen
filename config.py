"""Project configuration and paths."""

import os
from pathlib import Path

# Project root is where this config.py file is located
PROJECT_ROOT = Path(__file__).parent

# Database configuration
DB_DIR = PROJECT_ROOT / "db"
DB_PATH = DB_DIR / "metagen_memory.db"

# Ensure db directory exists
DB_DIR.mkdir(exist_ok=True)

# Database URL for SQLAlchemy/Alembic
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Memory configuration defaults (can be overridden by environment)
MEMORY_CONFIG = {
    "compaction_token_threshold": int(os.getenv("MEMORY_COMPACTION_TOKEN_THRESHOLD", "10000")),
    "compaction_min_turns": int(os.getenv("MEMORY_COMPACTION_MIN_TURNS", "5")),
    "scheduler_check_interval": int(os.getenv("MEMORY_SCHEDULER_CHECK_INTERVAL", "300")),
}

# Tool approval configuration
TOOL_APPROVAL_CONFIG = {
    # Global switch for tool approval
    "require_approval": os.getenv("REQUIRE_TOOL_APPROVAL", "false").lower() == "true",
    # Tools that don't need approval (safe read operations)
    "auto_approve_tools": os.getenv(
        "AUTO_APPROVE_TOOLS", "read_file,list_files,search_files,grep,get_current_time"
    ).split(",")
    if os.getenv("AUTO_APPROVE_TOOLS")
    else [
        "read_file",
        "list_files",
        "search_files",
        "grep",
        "get_current_time",
        "memory_search",
        "get_recent_conversations",
    ],
    # Timeout for approval in seconds
    "approval_timeout_seconds": int(os.getenv("APPROVAL_TIMEOUT_SECONDS", "30")),
    # Whether to remember user preferences for future sessions
    "remember_preferences": os.getenv("REMEMBER_TOOL_PREFERENCES", "true").lower() == "true",
    # What to do on timeout: "approve", "reject", or "error"
    "timeout_action": os.getenv("APPROVAL_TIMEOUT_ACTION", "reject"),
    # Tools with side effects that should always require explicit approval
    "tools_with_side_effects": os.getenv(
        "TOOLS_WITH_SIDE_EFFECTS", "write_file,delete_file,execute_command,send_email"
    ).split(",")
    if os.getenv("TOOLS_WITH_SIDE_EFFECTS")
    else [
        "write_file",
        "delete_file",
        "execute_command",
        "send_email",
        "execute_task",
        "create_task",
        "update_task",
        "api_request",  # External API calls
    ],
}
