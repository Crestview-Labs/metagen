"""Custom SQLAlchemy types for Pydantic model serialization."""

from typing import Any

from pydantic import BaseModel
from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator


class PydanticJSON(TypeDecorator):
    """Custom SQLAlchemy type for storing Pydantic models as JSON.

    This type automatically handles serialization of Pydantic models to JSON
    when storing in the database, and deserialization back to Pydantic models
    when loading from the database.
    """

    impl = JSON
    cache_ok = True

    def __init__(self, pydantic_type: type[BaseModel]):
        """Initialize with the Pydantic model type.

        Args:
            pydantic_type: The Pydantic model class to use for serialization
        """
        super().__init__()
        self._pydantic_type = pydantic_type

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        """Process value before binding to SQL parameter.

        Converts Pydantic models to JSON-serializable dicts.

        Args:
            value: The value to process (Pydantic model or dict)
            dialect: The SQL dialect being used

        Returns:
            JSON-serializable dict or None
        """
        if value is not None:
            if isinstance(value, BaseModel):
                # Use mode='json' to ensure all fields are JSON serializable
                return value.model_dump(mode="json")
            elif isinstance(value, dict):
                # Already a dict, return as-is
                return value
            else:
                raise ValueError(
                    f"Expected {self._pydantic_type.__name__} or dict, got {type(value).__name__}"
                )
        return value

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        """Process value after loading from database.

        Converts JSON dicts back to Pydantic models.

        Args:
            value: The value from the database (dict or None)
            dialect: The SQL dialect being used

        Returns:
            Pydantic model instance or None
        """
        if value is not None:
            if isinstance(value, dict):
                return self._pydantic_type(**value)
            elif isinstance(value, self._pydantic_type):
                # Already the right type (shouldn't happen but handle gracefully)
                return value
            else:
                raise ValueError(f"Expected dict from database, got {type(value).__name__}")
        return value

    def process_literal_param(self, value: Any, dialect: Any) -> str:
        """Process literals for SQL compilation.

        Args:
            value: The literal value
            dialect: The SQL dialect being used

        Returns:
            String representation of the value
        """
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="json")
        return super().process_literal_param(value, dialect)

    @property
    def python_type(self) -> type[BaseModel]:
        """Return the Python type for this column."""
        return self._pydantic_type
