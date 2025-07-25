"""Trace analyzer for automatic performance insights and debugging."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SpanInsight:
    """Individual span analysis."""

    name: str
    duration_ms: float
    category: str  # 'http', 'agent', 'llm', 'tool', 'coordination'
    description: str
    performance_rating: str  # 'fast', 'normal', 'slow', 'very_slow'
    issues: list[str] = field(default_factory=list)


@dataclass
class TraceInsights:
    """Complete trace analysis with automated insights."""

    trace_id: str
    total_duration_ms: float
    request_flow: list[SpanInsight]
    key_insights: list[str]
    performance_issues: list[str]
    recommendations: list[str]
    bottlenecks: list[dict[str, Any]]
    tool_analysis: Optional[dict[str, Any]] = None


class TraceAnalyzer:
    """Analyzes traces and generates human-readable insights automatically."""

    # Performance thresholds (in milliseconds)
    THRESHOLDS = {
        "http_request": {"fast": 100, "normal": 1000, "slow": 5000},
        "llm_call": {"fast": 1000, "normal": 3000, "slow": 8000},
        "tool_execution": {"fast": 500, "normal": 2000, "slow": 5000},
        "agent_processing": {"fast": 500, "normal": 2000, "slow": 10000},
        "coordination": {"fast": 50, "normal": 200, "slow": 1000},
    }

    def analyze_trace(self, spans: list[dict[str, Any]]) -> TraceInsights:
        """Analyze a complete trace and generate insights."""
        if not spans:
            return TraceInsights(
                trace_id="unknown",
                total_duration_ms=0,
                request_flow=[],
                key_insights=["No spans found in trace"],
                performance_issues=["Empty trace"],
                recommendations=["Check if tracing is properly enabled"],
                bottlenecks=[],
            )

        trace_id = spans[0].get("trace_id", "unknown")

        # Categorize and analyze spans
        categorized_spans = self._categorize_spans(spans)
        span_insights = self._analyze_spans(categorized_spans)

        # Calculate total duration
        total_duration = self._calculate_total_duration(spans)

        # Generate insights
        key_insights = self._generate_key_insights(span_insights, total_duration)
        performance_issues = self._identify_performance_issues(span_insights)
        recommendations = self._generate_recommendations(span_insights, performance_issues)
        bottlenecks = self._identify_bottlenecks(span_insights)
        tool_analysis = self._analyze_tools(span_insights)

        return TraceInsights(
            trace_id=trace_id,
            total_duration_ms=total_duration,
            request_flow=span_insights,
            key_insights=key_insights,
            performance_issues=performance_issues,
            recommendations=recommendations,
            bottlenecks=bottlenecks,
            tool_analysis=tool_analysis,
        )

    def _categorize_spans(self, spans: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Categorize spans by their function."""
        categories: dict[str, list[dict[str, Any]]] = {
            "http": [],
            "agent": [],
            "llm": [],
            "tool": [],
            "coordination": [],
        }

        for span in spans:
            name = span.get("name", "").lower()

            if any(x in name for x in ["http", "post", "get", "api"]):
                categories["http"].append(span)
            elif "metaagent" in name or "agent" in name:
                categories["agent"].append(span)
            elif "llm" in name or "anthropic" in name or "openai" in name:
                categories["llm"].append(span)
            elif "tool" in name or "gmail" in name or "drive" in name or "calendar" in name:
                categories["tool"].append(span)
            else:
                categories["coordination"].append(span)

        return categories

    def _analyze_spans(
        self, categorized_spans: dict[str, list[dict[str, Any]]]
    ) -> list[SpanInsight]:
        """Analyze each span and generate insights."""
        insights = []

        for category, spans in categorized_spans.items():
            for span in spans:
                insight = self._analyze_single_span(span, category)
                insights.append(insight)

        # Sort by duration (longest first)
        insights.sort(key=lambda x: x.duration_ms, reverse=True)
        return insights

    def _analyze_single_span(self, span: dict[str, Any], category: str) -> SpanInsight:
        """Analyze a single span."""
        name = span.get("name", "unknown")
        duration = span.get("duration_ms", 0)

        # Determine performance rating
        thresholds = self.THRESHOLDS.get(category, self.THRESHOLDS["coordination"])
        if duration < thresholds["fast"]:
            rating = "fast"
        elif duration < thresholds["normal"]:
            rating = "normal"
        elif duration < thresholds["slow"]:
            rating = "slow"
        else:
            rating = "very_slow"

        # Generate description
        description = self._generate_span_description(span, category, duration)

        # Identify issues
        issues = self._identify_span_issues(span, category, rating)

        return SpanInsight(
            name=name,
            duration_ms=duration,
            category=category,
            description=description,
            performance_rating=rating,
            issues=issues,
        )

    def _generate_span_description(
        self, span: dict[str, Any], category: str, duration: float
    ) -> str:
        """Generate human-readable description for a span."""
        name = span.get("name", "unknown")

        if category == "http":
            if "POST" in name and "chat" in name:
                return f"HTTP chat request processing ({duration:.1f}s total)"
            return f"HTTP request handling ({duration:.1f}s)"

        elif category == "agent":
            if "stream_chat" in name:
                return f"Agent chat coordination and response streaming ({duration:.1f}s)"
            return f"Agent processing ({duration:.1f}s)"

        elif category == "llm":
            if "initial_call" in name:
                return f"LLM analyzing request and deciding on tool usage ({duration:.1f}s)"
            return f"LLM processing ({duration:.1f}s)"

        elif category == "tool":
            if "gmail" in name.lower():
                return f"Gmail API call ({duration:.1f}s)"
            elif "drive" in name.lower():
                return f"Google Drive API call ({duration:.1f}s)"
            elif "calendar" in name.lower():
                return f"Google Calendar API call ({duration:.1f}s)"
            elif "tool_execution_phase" in name:
                return f"Tool execution coordination ({duration:.1f}s)"
            return f"Tool execution ({duration:.1f}s)"

        else:
            return f"System coordination ({duration:.1f}s)"

    def _identify_span_issues(self, span: dict[str, Any], category: str, rating: str) -> list[str]:
        """Identify potential issues with a span."""
        issues = []
        _ = span.get("name", "")  # TODO: Use name when analyzing span names
        duration = span.get("duration_ms", 0)

        if rating == "very_slow":
            issues.append(f"Very slow performance ({duration:.1f}s)")

        # Check for specific issues
        if category == "llm" and duration > 5000:
            issues.append(
                "LLM call taking longer than expected - check token count or model performance"
            )

        if category == "tool" and duration > 3000:
            issues.append("Tool execution slow - check API connectivity or payload size")

        if "error" in span.get("attributes", {}):
            issues.append("Span contains errors")

        return issues

    def _calculate_total_duration(self, spans: list[dict[str, Any]]) -> float:
        """Calculate total trace duration."""
        if not spans:
            return 0

        # Use the maximum duration from all spans as approximation
        return float(max(s.get("duration_ms", 0) for s in spans))

    def _generate_key_insights(
        self, span_insights: list[SpanInsight], total_duration: float
    ) -> list[str]:
        """Generate key insights about the trace."""
        insights = []

        # Find the longest operations
        top_spans = sorted(span_insights, key=lambda x: x.duration_ms, reverse=True)[:5]

        insights.append(f"Total request completed in {total_duration:.1f}s")

        if top_spans:
            insights.append(f"Longest operation: {top_spans[0].description}")

        # LLM analysis
        llm_spans = [s for s in span_insights if s.category == "llm"]
        if llm_spans:
            total_llm_time = sum(s.duration_ms for s in llm_spans)
            insights.append(
                f"LLM processing took {total_llm_time:.1f}s "
                f"({(total_llm_time / total_duration) * 100:.1f}% of total)"
            )

        # Tool analysis
        tool_spans = [s for s in span_insights if s.category == "tool" and "mcp_server" in s.name]
        if tool_spans:
            total_tool_time = sum(s.duration_ms for s in tool_spans)
            insights.append(
                f"Tool execution took {total_tool_time:.1f}s "
                f"({(total_tool_time / total_duration) * 100:.1f}% of total)"
            )
            insights.append(
                f"Used {len(tool_spans)} tool(s): "
                f"{', '.join(set(s.name.split('.')[-1] for s in tool_spans))}"
            )

        return insights

    def _identify_performance_issues(self, span_insights: list[SpanInsight]) -> list[str]:
        """Identify performance issues."""
        issues = []

        # Collect all issues from spans
        for span in span_insights:
            issues.extend(span.issues)

        # Check for coordination overhead
        coordination_spans = [s for s in span_insights if s.category == "coordination"]
        if coordination_spans:
            total_coord_time = sum(s.duration_ms for s in coordination_spans)
            if total_coord_time > 1000:
                issues.append(f"High coordination overhead ({total_coord_time:.1f}s)")

        return list(set(issues))  # Remove duplicates

    def _generate_recommendations(
        self, span_insights: list[SpanInsight], issues: list[str]
    ) -> list[str]:
        """Generate actionable recommendations."""
        recommendations = []

        # Performance recommendations
        slow_llm = [
            s
            for s in span_insights
            if s.category == "llm" and s.performance_rating in ["slow", "very_slow"]
        ]
        if slow_llm:
            recommendations.append(
                "Consider reducing message history or using a faster model "
                "for initial tool decisions"
            )

        slow_tools = [
            s
            for s in span_insights
            if s.category == "tool" and s.performance_rating in ["slow", "very_slow"]
        ]
        if slow_tools:
            recommendations.append(
                "Optimize tool execution: check API response times and payload sizes"
            )

        if not recommendations:
            recommendations.append("Performance looks good! No major optimizations needed.")

        return recommendations

    def _identify_bottlenecks(self, span_insights: list[SpanInsight]) -> list[dict[str, Any]]:
        """Identify performance bottlenecks."""
        bottlenecks = []

        # Sort by duration and identify top bottlenecks
        sorted_spans = sorted(span_insights, key=lambda x: x.duration_ms, reverse=True)

        for span in sorted_spans[:3]:  # Top 3 bottlenecks
            if span.duration_ms > 1000:  # Only significant delays
                bottlenecks.append(
                    {
                        "operation": span.name,
                        "duration_ms": span.duration_ms,
                        "category": span.category,
                        "description": span.description,
                        "severity": span.performance_rating,
                    }
                )

        return bottlenecks

    def _analyze_tools(self, span_insights: list[SpanInsight]) -> Optional[dict[str, Any]]:
        """Analyze tool usage patterns."""
        tool_spans = [s for s in span_insights if s.category == "tool" and "mcp_server" in s.name]

        if not tool_spans:
            return None

        tools_used = []
        total_tool_time = 0

        for span in tool_spans:
            tool_name = span.name.split(".")[-1] if "." in span.name else span.name
            tools_used.append(
                {
                    "name": tool_name,
                    "duration_ms": span.duration_ms,
                    "performance": span.performance_rating,
                }
            )
            total_tool_time += span.duration_ms  # type: ignore

        avg_tool_time = float(total_tool_time / len(tools_used)) if tools_used else 0.0

        return {
            "tools_used": tools_used,
            "total_tool_time_ms": total_tool_time,
            "average_tool_time_ms": avg_tool_time,
            "tool_count": len(tools_used),
            "fastest_tool": (
                min(tools_used, key=lambda x: float(str(x["duration_ms"]))) if tools_used else None
            ),
            "slowest_tool": (
                max(tools_used, key=lambda x: float(str(x["duration_ms"]))) if tools_used else None
            ),
        }


def format_insights_for_display(insights: TraceInsights) -> str:
    """Format insights for human-readable display."""
    output = []

    output.append(f"# 📊 Trace Analysis: {insights.trace_id}")
    output.append(f"**Total Duration:** {insights.total_duration_ms:.1f}s")
    output.append("")

    # Request Flow
    output.append("## 🔄 Complete Request Flow:")
    for i, span in enumerate(insights.request_flow[:5], 1):  # Top 5 operations
        output.append(f"{i}. **{span.description}** ({span.performance_rating})")
    output.append("")

    # Key Insights
    output.append("## 💡 Key Insights:")
    for insight in insights.key_insights:
        output.append(f"- {insight}")
    output.append("")

    # Performance Issues
    if insights.performance_issues:
        output.append("## ⚠️ Performance Issues:")
        for issue in insights.performance_issues:
            output.append(f"- {issue}")
        output.append("")

    # Recommendations
    output.append("## 🚀 Recommendations:")
    for rec in insights.recommendations:
        output.append(f"- {rec}")
    output.append("")

    # Tool Analysis
    if insights.tool_analysis:
        output.append("## 🔧 Tool Analysis:")
        ta = insights.tool_analysis
        output.append(f"- **Tools Used:** {ta['tool_count']}")
        output.append(f"- **Total Tool Time:** {ta['total_tool_time_ms']:.1f}s")
        if ta["fastest_tool"]:
            output.append(
                f"- **Fastest Tool:** {ta['fastest_tool']['name']} "
                f"({ta['fastest_tool']['duration_ms']:.1f}s)"
            )
        if ta["slowest_tool"]:
            output.append(
                f"- **Slowest Tool:** {ta['slowest_tool']['name']} "
                f"({ta['slowest_tool']['duration_ms']:.1f}s)"
            )

    return "\n".join(output)
