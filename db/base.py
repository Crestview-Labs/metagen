"""SQLAlchemy declarative base for all database models."""

from typing import Any

from sqlalchemy.orm import declarative_base

# Single declarative base for all models in the application
Base: Any = declarative_base()

# This can be imported by:
# - db/manager.py for schema creation
# - memory/storage/database.py for model definitions
# - Any other modules that need to define SQLAlchemy models
