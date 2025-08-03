"""OpenTelemetry telemetry module for Metagen observability."""

import logging
import os
from typing import Any, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.semconv.resource import ResourceAttributes

from telemetry.sqlite_exporter import SQLiteSpanExporter

logger = logging.getLogger(__name__)


def init_telemetry(
    service_name: str = "metagen", enable_console: bool = False, db_engine: Any = None
) -> None:
    """Initialize OpenTelemetry with flexible export options.

    Args:
        service_name: Name of the service for tracing
        enable_console: Whether to enable console output
        db_engine: DatabaseEngine instance for SQLite storage
    """

    # Create resource
    resource = Resource.create(
        {ResourceAttributes.SERVICE_NAME: service_name, ResourceAttributes.SERVICE_VERSION: "0.1.0"}
    )

    # Set up tracing
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    # Check if we should enable external telemetry
    if os.getenv("OTEL_ENABLED", "false").lower() == "true":
        # Add OTLP exporter if endpoint is available
        endpoint = os.getenv("OTEL_ENDPOINT", "http://localhost:4317")
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(f"✅ OTLP telemetry enabled: {endpoint}")
        except Exception as e:
            logger.warning(f"⚠️ OTLP export not available: {e}")

    # Console output for debugging (lightweight alternative)
    if enable_console or os.getenv("OTEL_CONSOLE", "false").lower() == "true":
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("📊 Console telemetry enabled")

    # Always enable in-memory span storage for local analysis
    from telemetry.local_storage import InMemorySpanExporter

    memory_exporter = InMemorySpanExporter()
    tracer_provider.add_span_processor(BatchSpanProcessor(memory_exporter))

    # Enable SQLite span storage for persistence
    if db_engine:
        try:
            sqlite_exporter = SQLiteSpanExporter(db_engine)
            tracer_provider.add_span_processor(BatchSpanProcessor(sqlite_exporter))

            # Store global reference for API access
            global _sqlite_exporter
            _sqlite_exporter = sqlite_exporter

            logger.info("✅ SQLite telemetry storage enabled")
        except Exception as e:
            logger.warning(f"⚠️ SQLite telemetry storage failed: {e}")

    # Store global reference for API access
    global _memory_exporter
    _memory_exporter = memory_exporter

    logger.info(f"✅ Telemetry initialized for service: {service_name}")


def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer for a component."""
    return trace.get_tracer(name)


def get_memory_exporter() -> Any:
    """Get the global memory exporter instance."""
    global _memory_exporter
    return _memory_exporter


def get_sqlite_exporter() -> Optional[SQLiteSpanExporter]:
    """Get the global SQLite exporter instance."""
    global _sqlite_exporter
    return _sqlite_exporter


# Global instance storage
_memory_exporter = None
_sqlite_exporter: Optional[SQLiteSpanExporter] = None
