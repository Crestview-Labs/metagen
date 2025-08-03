"""Telemetry-related SQLModel models.

These models serve as both SQLAlchemy ORM models and Pydantic validation models.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Column, Index
from sqlmodel import Field, SQLModel


class TelemetrySpan(SQLModel, table=True):
    """Model for OpenTelemetry spans.

    Stores distributed tracing data for observability.
    """

    __tablename__ = "telemetry_spans"

    # Primary identification
    span_id: str = Field(primary_key=True, description="Unique span identifier")
    trace_id: str = Field(index=True, description="Trace this span belongs to")
    parent_span_id: Optional[str] = Field(default=None, description="Parent span ID if nested")

    # Span details
    name: str = Field(index=True, description="Operation name")
    service_name: Optional[str] = Field(default=None, description="Service that created this span")

    # Timing
    start_time: float = Field(index=True, description="Start time as Unix timestamp")
    end_time: Optional[float] = Field(default=None, description="End time as Unix timestamp")
    duration_ms: Optional[float] = Field(default=None, description="Duration in milliseconds")

    # Span data
    attributes: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON), description="Span attributes as key-value pairs"
    )
    events: Optional[list[dict[str, Any]]] = Field(
        default=None, sa_column=Column(JSON), description="Events that occurred during the span"
    )
    status: Optional[str] = Field(default=None, description="Span status (OK, ERROR, etc)")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

    # Table configuration
    __table_args__ = (
        Index("idx_telemetry_trace_id", "trace_id"),
        Index("idx_telemetry_start_time", "start_time"),
        Index("idx_telemetry_name", "name"),
    )
