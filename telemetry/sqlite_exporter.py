"""SQLite span exporter for storing telemetry data in the same database as conversations."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SQLiteSpanExporter(SpanExporter):
    """Store spans in SQLite database alongside conversation data."""

    def __init__(self, db_manager: Any) -> None:
        """Initialize with database manager."""
        self.db_manager = db_manager
        logger.debug(f"🔍 SQLiteSpanExporter.__init__() called with db_manager: {db_manager}")
        # No initialization - DB manager handles it

    def export(self, spans: Any) -> SpanExportResult:
        """Export spans to SQLite database."""
        # Bridge sync to async
        return asyncio.run(self._export_async(spans))

    async def _export_async(self, spans: Any) -> SpanExportResult:
        """Export spans to SQLite database asynchronously."""
        try:
            engine = await self.db_manager.get_async_engine()
            async with AsyncSession(engine) as session:
                for span in spans:
                    # Extract span data
                    span_data = {
                        "span_id": format(span.context.span_id, "016x"),
                        "trace_id": format(span.context.trace_id, "032x"),
                        "parent_span_id": format(span.parent.span_id, "016x")
                        if span.parent
                        else None,
                        "name": span.name,
                        "service_name": span.resource.attributes.get("service.name", "unknown"),
                        "start_time": span.start_time / 1e9,  # Convert to seconds
                        "end_time": span.end_time / 1e9 if span.end_time else None,
                        "duration_ms": (span.end_time - span.start_time) / 1e6
                        if span.end_time
                        else None,
                        "attributes": json.dumps({k: str(v) for k, v in span.attributes.items()}),
                        "events": json.dumps(
                            [
                                {
                                    "name": event.name,
                                    "timestamp": event.timestamp / 1e9,
                                    "attributes": dict(event.attributes)
                                    if event.attributes
                                    else {},
                                }
                                for event in span.events
                            ]
                        ),
                        "status": span.status.status_code.name,
                    }

                    # Add created_at timestamp
                    span_data["created_at"] = datetime.utcnow()

                    # Insert or replace span using SQLAlchemy
                    await session.execute(
                        text("""
                        INSERT OR REPLACE INTO telemetry_spans (
                            span_id, trace_id, parent_span_id, name, service_name,
                            start_time, end_time, duration_ms, attributes, events, 
                            status, created_at
                        ) VALUES (
                            :span_id, :trace_id, :parent_span_id, :name, :service_name,
                            :start_time, :end_time, :duration_ms, :attributes, :events, 
                            :status, :created_at
                        )
                        """),
                        span_data,
                    )

                await session.commit()

            return SpanExportResult.SUCCESS

        except Exception as e:
            logger.error(f"❌ Failed to export spans to SQLite: {e}")
            return SpanExportResult.FAILURE

    async def get_trace_async(self, trace_id: str) -> list[dict[str, Any]]:
        """Get all spans for a trace asynchronously."""
        engine = await self.db_manager.get_async_engine()
        async with AsyncSession(engine) as session:
            result = await session.execute(
                text(
                    "SELECT * FROM telemetry_spans WHERE trace_id = :trace_id ORDER BY start_time"
                ),
                {"trace_id": trace_id},
            )
            rows = result.fetchall()

            # Get column names
            columns = result.keys()

            # Convert to dictionaries
            spans = []
            for row in rows:
                span = dict(zip(columns, row))
                # Parse JSON fields
                span["attributes"] = json.loads(span["attributes"]) if span["attributes"] else {}
                span["events"] = json.loads(span["events"]) if span["events"] else []
                spans.append(span)

            return spans

    async def get_recent_traces_async(self, limit: int = 20) -> list[str]:
        """Get recent unique trace IDs asynchronously."""
        engine = await self.db_manager.get_async_engine()
        async with AsyncSession(engine) as session:
            result = await session.execute(
                text("""
                SELECT DISTINCT trace_id 
                FROM telemetry_spans 
                ORDER BY created_at DESC 
                LIMIT :limit
                """),
                {"limit": limit},
            )
            rows = result.fetchall()
            return [row[0] for row in rows]

    async def analyze_trace_async(self, trace_id: str) -> dict[str, Any]:
        """Analyze a trace for performance issues asynchronously."""
        spans = await self.get_trace_async(trace_id)
        if not spans:
            return {"error": "Trace not found"}

        # Calculate total duration
        start_times = [s["start_time"] for s in spans if s["start_time"]]
        end_times = [s["end_time"] for s in spans if s["end_time"]]

        if start_times and end_times:
            total_duration_ms = (max(end_times) - min(start_times)) * 1000
        else:
            total_duration_ms = 0

        # Find slow operations (>1 second)
        slow_spans = sorted(
            [s for s in spans if s["duration_ms"] and s["duration_ms"] > 1000],
            key=lambda s: s["duration_ms"],
            reverse=True,
        )[:5]

        # Tool usage analysis
        tool_spans = [s for s in spans if s["name"].startswith("tool.")]

        return {
            "trace_id": trace_id,
            "total_duration_ms": total_duration_ms,
            "span_count": len(spans),
            "root_span": next((s["name"] for s in spans if not s["parent_span_id"]), "unknown"),
            "services_involved": list(set(s["service_name"] for s in spans)),
            "slow_operations": [
                {"name": s["name"], "duration_ms": s["duration_ms"], "attributes": s["attributes"]}
                for s in slow_spans
            ],
            "tool_calls": [
                {"name": s["name"], "duration_ms": s["duration_ms"], "status": s["status"]}
                for s in tool_spans
            ],
            "has_errors": any(s["status"] != "OK" for s in spans),
        }

    async def clear_all_spans(self) -> int:
        """Clear all telemetry spans from the database.

        Returns:
            Number of spans deleted
        """
        engine = await self.db_manager.get_async_engine()
        async with AsyncSession(engine) as session:
            # Get count before deletion
            result = await session.execute(text("SELECT COUNT(*) FROM telemetry_spans"))
            count = result.scalar() or 0

            # Delete all spans
            await session.execute(text("DELETE FROM telemetry_spans"))
            await session.commit()

            logger.info(f"🗑️ Cleared {count} telemetry spans from database")
            return count
