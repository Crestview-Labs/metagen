"""Project configuration and paths."""

import os
from pathlib import Path
from typing import Any

# Project root is where this config.py file is located
PROJECT_ROOT = Path(__file__).parent

# Database configuration
# Allow overriding via environment variable
if "METAGEN_DB_PATH" in os.environ:
    DB_PATH = Path(os.environ["METAGEN_DB_PATH"])
    DB_DIR = DB_PATH.parent
else:
    DB_DIR = PROJECT_ROOT / "db"
    DB_PATH = DB_DIR / "metagen.db"

# Ensure db directory exists
DB_DIR.mkdir(parents=True, exist_ok=True)

# Database URL for SQLAlchemy/Alembic
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Memory configuration defaults (can be overridden by environment)
MEMORY_CONFIG = {
    "compaction_token_threshold": int(os.getenv("MEMORY_COMPACTION_TOKEN_THRESHOLD", "10000")),
    "compaction_min_turns": int(os.getenv("MEMORY_COMPACTION_MIN_TURNS", "5")),
    "scheduler_check_interval": int(os.getenv("MEMORY_SCHEDULER_CHECK_INTERVAL", "300")),
}

# Tool approval configuration
TOOL_APPROVAL_CONFIG: dict[str, Any] = {
    # Global switch for tool approval
    "require_approval": os.getenv("REQUIRE_TOOL_APPROVAL", "true").lower() == "true",
    # Tools that don't need approval (safe read operations)
    "auto_approve_tools": os.getenv(
        "AUTO_APPROVE_TOOLS", "read_file,list_files,search_files,grep,get_current_time"
    ).split(",")
    if os.getenv("AUTO_APPROVE_TOOLS")
    else [
        # File system read operations
        "read_file",
        "list_files",
        "search_files",
        "grep",
        # Time/info operations
        "get_current_time",
        # Memory operations
        "memory_search",
        "get_recent_conversations",
        # Task management read operations
        "list_tasks",
        # Gmail read operations
        "gmail_search",
        "gmail_get_email",
        "gmail_get_labels",
        # Google Drive read operations
        "drive_search_files",
        "drive_get_file",
        # Calendar read operations
        "calendar_list_events",
        # Google auth status
        "google_auth_status",
        # Google Docs read operations
        "docs_get_document",
        "docs_get_content",
        # Google Sheets read operations
        "sheets_get_spreadsheet",
        "sheets_get_values",
        # Google Slides read operations
        "slides_get_presentation",
    ],
    # Whether to remember user preferences for future sessions
    "remember_preferences": os.getenv("REMEMBER_TOOL_PREFERENCES", "true").lower() == "true",
    # Tools with side effects that should always require explicit approval
    "tools_with_side_effects": os.getenv(
        "TOOLS_WITH_SIDE_EFFECTS", "write_file,delete_file,execute_command,send_email"
    ).split(",")
    if os.getenv("TOOLS_WITH_SIDE_EFFECTS")
    else [
        # File system write operations
        "write_file",
        "delete_file",
        # Command execution
        "execute_command",
        # Email operations
        "send_email",
        # Task management write operations
        "execute_task",
        "create_task",
        "update_task",
        # External API calls
        "api_request",
        # Google Docs write operations
        "docs_create_document",
        "docs_insert_text",
        "docs_replace_text",
        # Google Sheets write operations
        "sheets_create_spreadsheet",
        "sheets_update_values",
        "sheets_append_values",
        "sheets_create_sheet",
        # Google Slides write operations
        "slides_create_presentation",
        "slides_create_slide",
        "slides_add_text",
        "slides_replace_text",
        "slides_duplicate_slide",
        "slides_delete_slide",
    ],
}
