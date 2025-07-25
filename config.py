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
