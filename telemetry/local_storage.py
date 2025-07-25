"""Local telemetry storage for in-memory span analysis without external dependencies."""

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult


@dataclass
class StoredSpan:
    """Simplified span storage for local analysis."""

    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    name: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_ms: float = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    status: str = "OK"
    service_name: str = ""


class InMemorySpanExporter(SpanExporter):
    """Store spans in memory for local analysis without external dependencies."""

    def __init__(self, max_spans: int = 10000):
        self.spans: deque[StoredSpan] = deque(maxlen=max_spans)
        self._lock = threading.Lock()

    def export(self, spans: Any) -> SpanExportResult:
        """Store spans in memory."""
        with self._lock:
            for span in spans:
                stored_span = StoredSpan(
                    trace_id=format(span.context.trace_id, "032x"),
                    span_id=format(span.context.span_id, "016x"),
                    parent_span_id=format(span.parent.span_id, "016x") if span.parent else None,
                    name=span.name,
                    start_time=datetime.fromtimestamp(span.start_time / 1e9),
                    end_time=datetime.fromtimestamp(span.end_time / 1e9) if span.end_time else None,
                    duration_ms=(span.end_time - span.start_time) / 1e6 if span.end_time else 0,
                    attributes={k: str(v) for k, v in span.attributes.items()},
                    events=[
                        {
                            "name": event.name,
                            "timestamp": datetime.fromtimestamp(event.timestamp / 1e9).isoformat(),
                            "attributes": dict(event.attributes) if event.attributes else {},
                        }
                        for event in span.events
                    ],
                    status=span.status.status_code.name,
                    service_name=span.resource.attributes.get("service.name", "unknown"),
                )
                self.spans.append(stored_span)
        return SpanExportResult.SUCCESS

    def get_trace(self, trace_id: str) -> list[StoredSpan]:
        """Get all spans for a trace."""
        with self._lock:
            return [s for s in self.spans if s.trace_id == trace_id]

    def get_recent_traces(self, limit: int = 10) -> list[str]:
        """Get recent unique trace IDs."""
        with self._lock:
            trace_ids = []
            seen = set()
            for span in reversed(self.spans):
                if span.trace_id not in seen:
                    seen.add(span.trace_id)
                    trace_ids.append(span.trace_id)
                if len(trace_ids) >= limit:
                    break
            return trace_ids

    def analyze_trace(self, trace_id: str) -> dict[str, Any]:
        """Analyze a trace for debugging."""
        spans = self.get_trace(trace_id)
        if not spans:
            return {"error": "Trace not found"}

        # Build trace tree
        root_spans = [s for s in spans if s.parent_span_id is None]

        # Calculate stats
        end_times = [s.end_time for s in spans if s.end_time is not None]
        start_times = [s.start_time for s in spans if s.start_time is not None]

        if end_times and start_times:
            total_duration = max(end_times) - min(start_times)
        else:
            total_duration = timedelta(0)

        # Find slow operations
        slow_spans = sorted(
            [s for s in spans if s.duration_ms > 1000], key=lambda s: s.duration_ms, reverse=True
        )[:5]

        # Tool usage
        tool_spans = [s for s in spans if s.name.startswith("tool.")]

        return {
            "trace_id": trace_id,
            "total_duration_ms": total_duration.total_seconds() * 1000,
            "span_count": len(spans),
            "root_span": root_spans[0].name if root_spans else "unknown",
            "services_involved": list(set(s.service_name for s in spans)),
            "slow_operations": [
                {"name": s.name, "duration_ms": s.duration_ms, "attributes": s.attributes}
                for s in slow_spans
            ],
            "tool_calls": [
                {"name": s.name, "duration_ms": s.duration_ms, "status": s.status}
                for s in tool_spans
            ],
            "has_errors": any(s.status != "OK" for s in spans),
        }
