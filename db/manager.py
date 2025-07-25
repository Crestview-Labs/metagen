"""Centralized database initialization and management."""

import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from config import DB_PATH

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database initialization and provides handles to different components."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize with database path."""
        self.db_path = db_path or DB_PATH
        self._async_engine: Optional[AsyncEngine] = None
        self._initialized = False
        self._last_health_check: float = 0
        self._health_check_interval: float = 60.0  # Check every minute
        logger.debug(f"🔍 DatabaseManager initialized with path: {self.db_path}")

    def ensure_db_exists(self) -> None:
        """Ensure database file and directory exist."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.db_path.exists():
            logger.info(f"📁 Creating new database at: {self.db_path}")
            # Touch the file to create it
            self.db_path.touch()
        else:
            logger.info(f"📁 Using existing database at: {self.db_path}")

    def get_sync_connection(self) -> sqlite3.Connection:
        """Get a synchronous SQLite connection (for telemetry)."""
        logger.debug(f"🔍 Creating sync connection to: {self.db_path}")
        return sqlite3.connect(str(self.db_path))

    async def get_async_engine(self) -> AsyncEngine:
        """Get async SQLAlchemy engine (for storage backend)."""
        if not self._async_engine:
            logger.debug(f"🔍 Creating async engine for: {self.db_path}")

            database_url = f"sqlite+aiosqlite:///{self.db_path}"

            self._async_engine = create_async_engine(
                database_url,
                echo=False,
                poolclass=NullPool,  # No connection pooling for SQLite
                connect_args={"check_same_thread": False, "timeout": 30.0},
            )

            # Register SQLite pragmas
            @event.listens_for(self._async_engine.sync_engine, "connect")
            def set_sqlite_pragma(dbapi_conn: Any, connection_record: Any) -> None:
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA synchronous = NORMAL")
                cursor.execute("PRAGMA busy_timeout = 30000")
                cursor.close()

        return self._async_engine

    async def initialize(self) -> None:
        """Initialize the database with all required schemas."""
        if self._initialized:
            logger.debug("🔍 Database already initialized")
            return

        logger.info("🚀 Initializing database...")

        # Ensure database exists
        self.ensure_db_exists()

        # Initialize telemetry schema first (synchronous)
        self._init_telemetry_schema()

        # Initialize main schema (async)
        await self._init_main_schema()

        self._initialized = True
        logger.info("✅ Database initialization complete")

    def _init_telemetry_schema(self) -> None:
        """Initialize telemetry schema using sync connection."""
        logger.debug("🔍 Initializing telemetry schema...")

        # Now handled by SQLAlchemy models in _init_main_schema
        logger.debug("✅ Telemetry schema will be created with main schema")

    async def _init_main_schema(self) -> None:
        """Initialize main application schema using async engine."""
        logger.debug("🔍 Initializing main schema...")

        engine = await self.get_async_engine()

        # Import models to ensure they're registered
        from sqlalchemy import text

        # Import all model files to ensure they're registered with Base
        import db.memory_models  # noqa: F401
        import db.telemetry_models  # noqa: F401
        from db.base import Base

        # Create all tables and set additional pragmas
        async with engine.begin() as conn:
            # Create tables
            await conn.run_sync(Base.metadata.create_all)

            # Set additional pragmas for optimal performance
            await conn.execute(
                text("PRAGMA wal_autocheckpoint = 1000")
            )  # Checkpoint every 1000 pages
            await conn.execute(text("PRAGMA cache_size = -64000"))  # 64MB cache

            # Run integrity check
            result = await conn.execute(text("PRAGMA integrity_check"))
            integrity = result.scalar()
            if integrity != "ok":
                raise RuntimeError(f"Database integrity check failed: {integrity}")

        logger.debug("✅ Main schema initialized")

    async def check_health(self) -> dict[str, Any]:
        """Check database health and return status."""
        health_status: dict[str, Any] = {
            "healthy": True,
            "last_check": self._last_health_check,
            "seconds_since_check": time.time() - self._last_health_check
            if self._last_health_check > 0
            else None,
            "database_path": str(self.db_path),
            "database_exists": self.db_path.exists(),
            "database_size_mb": 0,
            "errors": [],
        }

        try:
            # Check file exists and size
            if self.db_path.exists():
                health_status["database_size_mb"] = round(
                    self.db_path.stat().st_size / 1024 / 1024, 2
                )
            else:
                health_status["healthy"] = False
                health_status["errors"].append("Database file does not exist")  # type: ignore[union-attr]
                return health_status

            # Test async connection
            if self._async_engine:
                async with AsyncSession(self._async_engine) as session:
                    # Quick query to test connection
                    result = await session.execute(text("SELECT 1"))
                    if result.scalar() != 1:
                        health_status["healthy"] = False
                        health_status["errors"].append("Database query test failed")  # type: ignore[union-attr]

                    # Check table count
                    result = await session.execute(
                        text("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                    )
                    table_count = result.scalar()
                    health_status["table_count"] = table_count

                    # Run quick integrity check
                    result = await session.execute(text("PRAGMA quick_check"))
                    integrity = result.scalar()
                    if integrity != "ok":
                        health_status["healthy"] = False
                        health_status["errors"].append(f"Integrity check failed: {integrity}")  # type: ignore[union-attr]

            self._last_health_check = time.time()

        except Exception as e:
            health_status["healthy"] = False
            health_status["errors"].append(f"Health check error: {str(e)}")  # type: ignore[union-attr]
            logger.error(f"Database health check failed: {e}", exc_info=True)

        return health_status

    async def close(self) -> None:
        """Close database connections."""
        if self._async_engine:
            await self._async_engine.dispose()
            self._async_engine = None
        self._initialized = False


# Global instance
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get or create the global database manager."""
    global _db_manager
    if not _db_manager:
        _db_manager = DatabaseManager()
    return _db_manager
