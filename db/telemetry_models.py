"""SQLAlchemy database models for telemetry data."""

from sqlalchemy import Column, DateTime, Float, Index, String, Text, func

from .base import Base


class TelemetrySpanModel(Base):
    """SQLAlchemy model for OpenTelemetry spans."""

    __tablename__ = "telemetry_spans"

    # Primary identification
    span_id = Column(String, primary_key=True)
    trace_id = Column(String, nullable=False)
    parent_span_id = Column(String, nullable=True)

    # Span details
    name = Column(String, nullable=False)
    service_name = Column(String, nullable=True)

    # Timing
    start_time = Column(Float, nullable=False)  # Unix timestamp
    end_time = Column(Float, nullable=True)
    duration_ms = Column(Float, nullable=True)

    # Span data (stored as JSON strings)
    attributes = Column(Text, nullable=True)  # JSON
    events = Column(Text, nullable=True)  # JSON
    status = Column(String, nullable=True)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=func.now())

    # Indexes for efficient queries
    __table_args__ = (
        Index("idx_telemetry_trace_id", "trace_id"),
        Index("idx_telemetry_start_time", "start_time"),
        Index("idx_telemetry_name", "name"),
    )
