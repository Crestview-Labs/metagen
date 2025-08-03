"""Base models and mixins for SQLModel."""

from datetime import datetime

from sqlmodel import Field, SQLModel


class TimestampedModel(SQLModel):
    """Base model with created_at and updated_at timestamps.

    This is a mixin that can be inherited by other models to automatically
    include timestamp fields.
    """

    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        sa_column_kwargs={"onupdate": datetime.utcnow},
    )
