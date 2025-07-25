"""Telemetry API routes for trace analysis and debugging."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from telemetry import get_memory_exporter, get_sqlite_exporter
from telemetry.trace_analyzer import TraceAnalyzer, format_insights_for_display

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

# Initialize trace analyzer
_trace_analyzer = TraceAnalyzer()


@router.get("/traces")
async def get_recent_traces(limit: int = 20) -> list[str]:
    """Get recent trace IDs."""
    try:
        sqlite_exporter = get_sqlite_exporter()
        if not sqlite_exporter:
            raise HTTPException(status_code=503, detail="SQLite telemetry not initialized")
        return await sqlite_exporter.get_recent_traces_async(limit)
    except Exception as e:
        logger.error(f"Failed to get recent traces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str) -> dict[str, Any]:
    """Get all spans for a trace."""
    try:
        sqlite_exporter = get_sqlite_exporter()
        if not sqlite_exporter:
            raise HTTPException(status_code=503, detail="SQLite telemetry not initialized")
        spans = await sqlite_exporter.get_trace_async(trace_id)
        if not spans:
            raise HTTPException(status_code=404, detail="Trace not found")

        return {"trace_id": trace_id, "spans": spans}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get trace {trace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traces/{trace_id}/analysis")
async def analyze_trace(trace_id: str) -> dict[str, Any]:
    """Analyze a trace for performance issues."""
    try:
        sqlite_exporter = get_sqlite_exporter()
        if not sqlite_exporter:
            raise HTTPException(status_code=503, detail="SQLite telemetry not initialized")
        return await sqlite_exporter.analyze_trace_async(trace_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to analyze trace {trace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/current")
async def get_current_trace() -> dict[str, Any]:
    """Get the current active trace (useful for debugging stuck requests)."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if not span or not span.is_recording():
            return {"status": "No active span"}

        ctx = span.get_span_context()
        return {
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
            "is_recording": span.is_recording(),
            "span_name": getattr(span, "name", "unknown"),
        }
    except Exception as e:
        logger.error(f"Failed to get current trace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/memory/traces")
async def get_memory_traces(limit: int = 10) -> list[str]:
    """Get recent traces from in-memory storage."""
    exporter = get_memory_exporter()
    if not exporter:
        raise HTTPException(status_code=503, detail="Memory telemetry not initialized")

    traces = exporter.get_recent_traces(limit)
    return list(traces)


@router.get("/memory/traces/{trace_id}")
async def get_memory_trace(trace_id: str) -> dict[str, Any]:
    """Get trace from in-memory storage."""
    exporter = get_memory_exporter()
    if not exporter:
        raise HTTPException(status_code=503, detail="Memory telemetry not initialized")

    spans = exporter.get_trace(trace_id)
    if not spans:
        raise HTTPException(status_code=404, detail="Trace not found in memory")

    return {"trace_id": trace_id, "spans": [span.__dict__ for span in spans]}


@router.get("/traces/{trace_id}/insights")
async def get_trace_insights(trace_id: str) -> dict[str, Any]:
    """Get intelligent analysis and insights for a trace."""
    try:
        sqlite_exporter = get_sqlite_exporter()
        if not sqlite_exporter:
            raise HTTPException(status_code=503, detail="SQLite telemetry not initialized")
        spans = await sqlite_exporter.get_trace_async(trace_id)
        if not spans:
            raise HTTPException(status_code=404, detail="Trace not found")

        insights = _trace_analyzer.analyze_trace(spans)
        return {"trace_id": trace_id, "insights": insights.__dict__}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to analyze trace {trace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traces/{trace_id}/report")
async def get_trace_report(trace_id: str) -> dict[str, str]:
    """Get a formatted markdown report for a trace."""
    try:
        sqlite_exporter = get_sqlite_exporter()
        if not sqlite_exporter:
            raise HTTPException(status_code=503, detail="SQLite telemetry not initialized")
        spans = await sqlite_exporter.get_trace_async(trace_id)
        if not spans:
            raise HTTPException(status_code=404, detail="Trace not found")

        insights = _trace_analyzer.analyze_trace(spans)
        report = format_insights_for_display(insights)

        return {"trace_id": trace_id, "report": report}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate report for trace {trace_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest/insights")
async def get_latest_trace_insights() -> dict[str, Any]:
    """Get insights for the most recent trace."""
    try:
        sqlite_exporter = get_sqlite_exporter()
        if not sqlite_exporter:
            raise HTTPException(status_code=503, detail="SQLite telemetry not initialized")
        traces = await sqlite_exporter.get_recent_traces_async(1)
        if not traces:
            raise HTTPException(status_code=404, detail="No traces found")

        latest_trace_id = traces[0]
        spans = await sqlite_exporter.get_trace_async(latest_trace_id)
        insights = _trace_analyzer.analyze_trace(spans)

        return {"trace_id": latest_trace_id, "insights": insights.__dict__}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to analyze latest trace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest/report")
async def get_latest_trace_report() -> dict[str, str]:
    """Get a formatted report for the most recent trace."""
    try:
        sqlite_exporter = get_sqlite_exporter()
        if not sqlite_exporter:
            raise HTTPException(status_code=503, detail="SQLite telemetry not initialized")
        traces = await sqlite_exporter.get_recent_traces_async(1)
        if not traces:
            raise HTTPException(status_code=404, detail="No traces found")

        latest_trace_id = traces[0]
        spans = await sqlite_exporter.get_trace_async(latest_trace_id)
        insights = _trace_analyzer.analyze_trace(spans)
        report = format_insights_for_display(insights)

        return {"trace_id": latest_trace_id, "report": report}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate latest trace report: {e}")
        raise HTTPException(status_code=500, detail=str(e))
