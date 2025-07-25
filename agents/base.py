"""Base Agent - Abstract base class for all agents with context-aware memory."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from opentelemetry import trace

from memory.storage.models import TurnStatus

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """Represents a message in agent conversation."""

    role: str  # "user", "assistant", "system"
    content: str
    timestamp: Optional[datetime] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class AgentResponse:
    """Response from an agent."""

    content: str
    tool_calls: Optional[list[dict[str, Any]]] = None
    usage: Optional[dict[str, Any]] = None
    model: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


@dataclass
class ContextSummary:
    """Represents a compacted conversation with context-ID."""

    context_id: str
    summary: str
    key_points: list[str]
    topics: list[str]
    timestamp: datetime
    message_count: int
    relevance_score: Optional[float] = None


class BaseAgent(ABC):
    """
    Abstract base class for all agents with context-aware memory.

    Key principles:
    - Raw conversations flow continuously without session boundaries
    - Compacted conversations get context-IDs for topic-based retrieval
    - Agent automatically discovers relevant contexts for current conversation
    - Users can optionally specify context, but agent figures it out automatically
    """

    def __init__(
        self,
        agent_id: str,
        instructions: str,
        agentic_client: Any = None,
        memory_manager: Any = None,
    ) -> None:
        """
        Initialize base agent.

        Args:
            agent_id: Unique agent identifier (e.g., METAGEN, TASK_EXECUTION_123)
            instructions: System instructions/prompt for the agent
            agentic_client: Agentic client for LLM + tool calling
            memory_manager: Memory manager for conversation storage
        """
        self.agent_id = agent_id
        self.name = agent_id  # Backward compatibility
        self.instructions = instructions
        self.agentic_client = agentic_client
        self.memory_manager = memory_manager
        self._initialized = False

        # Initialize tracer for telemetry
        self.tracer = trace.get_tracer(__name__)

    @property
    def is_initialized(self) -> bool:
        """Check if agent is initialized."""
        return self._initialized

    def get_current_task_id(self) -> Optional[str]:
        """Get current task ID if agent is executing a task. Override in subclasses."""
        return None

    async def initialize(self) -> None:
        """Initialize the agent and all its components."""
        if self._initialized:
            return

        # Standard initialization - handles SQLite concurrency requirements
        if self.agentic_client:
            await self.agentic_client.initialize()
        if self.memory_manager:
            await self.memory_manager.initialize()

        self._initialized = True

    async def stream_chat(self, message: str, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        """
        Stream a chat response using generate_stream_with_tools.

        Args:
            message: User message
            **kwargs: Additional parameters

        Yields:
            Dict chunks with stage and content
        """
        # Build context for the message
        context = await self.build_context(message)

        # Add the current message
        messages = context + [{"role": "user", "content": message}]

        # Stream using the common functionality
        async for chunk in self.generate_stream_with_tools(messages, **kwargs):
            yield chunk

    @abstractmethod
    async def build_context(self, query: str) -> list[dict[str, Any]]:
        """
        Build relevant context for a query.

        This single method replaces all the overlapping context methods.
        It searches across conversations, compact memories, and semantic memories
        to build the most relevant context for the given query.

        Args:
            query: The query to build context for

        Returns:
            List of message dictionaries for LLM context
        """
        pass

    async def use_tool(self, tool_name: str, parameters: dict[str, Any]) -> Any:
        """
        Use a tool available to the agent.

        This is common functionality - all agents use tools the same way.

        Args:
            tool_name: Name of the tool to use
            parameters: Parameters for the tool

        Returns:
            Tool execution result
        """
        if not self.agentic_client:
            raise ValueError("No agentic client available for tool usage")

        return await self.agentic_client.call_tool(tool_name, parameters)

    async def get_available_tools(self) -> list[dict[str, Any]]:
        """
        Get list of tools available to this agent.

        Returns:
            List of tool definitions
        """
        if not self.agentic_client:
            return []

        tools = await self.agentic_client.get_available_tools()
        return tools  # type: ignore[no-any-return]

    async def switch_model(self, model: str) -> bool:
        """
        Switch to a different LLM model.

        Args:
            model: Model identifier

        Returns:
            True if successful
        """
        if not self.agentic_client:
            return False

        # This would need to be implemented in agentic client
        # For now, return False as not implemented
        return False

    async def get_current_model(self) -> str:
        """Get the currently active model."""
        if not self.agentic_client:
            return "unknown"

        # This would need to be implemented in agentic client
        # For now, return unknown
        return "unknown"

    async def cleanup(self) -> None:
        """Clean up agent resources."""
        # Default implementation - agents can override if needed
        pass

    def get_agent_info(self) -> dict[str, Any]:
        """
        Get basic information about the agent.

        Returns:
            Agent information
        """
        return {
            "name": self.name,
            "agent_id": self.agent_id,
            "instructions": self.instructions,
            "initialized": self._initialized,
        }

    async def generate_stream_with_tools(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Generate streaming response with tool calling support.

        This is the core streaming functionality that all agents can use.
        It handles LLM calls, tool execution, and result streaming.

        Args:
            messages: List of conversation messages
            **kwargs: Additional parameters for LLM

        Yields:
            Dict chunks with structure:
            - {"stage": "thinking", "content": "...", "metadata": {...}}
            - {"stage": "llm_call", "content": "...", "metadata": {...}}
            - {"stage": "tool_call", "content": "...", "metadata": {...}}
            - {"stage": "tool_result", "content": "...", "metadata": {...}}
            - {"stage": "response", "content": "...", "metadata": {"final": True}}
        """
        if not self.agentic_client:
            raise ValueError(f"Agent {self.agent_id} requires an agentic client to function.")

        # Create in-progress turn at the start
        turn_id = None
        user_message = None

        if self.memory_manager and len(messages) > 0:
            # Extract user message (last user message in conversation)
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                    break

            if user_message:
                # Create turn with IN_PROGRESS status
                turn_id = await self.memory_manager.create_in_progress_turn(
                    user_query=user_message,
                    agent_id=self.agent_id,
                    task_id=self.get_current_task_id(),
                    trace_id=format(trace.get_current_span().get_span_context().trace_id, "032x")
                    if trace.get_current_span()
                    else None,
                    user_metadata={"timestamp": datetime.now().isoformat()},
                )

        # Start telemetry span
        try:
            with self.tracer.start_as_current_span(
                f"{self.agent_id.lower()}.generate_stream_with_tools",
                attributes={
                    "agent.id": self.agent_id,
                    "agent.name": self.name,
                    "messages.count": len(messages),
                    "turn.id": turn_id or "none",
                },
            ) as span:
                # Emit thinking stage
                yield {
                    "stage": "thinking",
                    "content": "thinking: Processing your request...",
                    "metadata": {"agent": self.name},
                }

                # Track for telemetry
                turn_start_time = datetime.now()
                current_span = trace.get_current_span()
                trace_id = (
                    format(current_span.get_span_context().trace_id, "032x")
                    if current_span
                    else None
                )

                span.add_event("thinking_stage_emitted")

                # Emit LLM call stage
                yield {
                    "stage": "llm_call",
                    "content": "llm_call: Analyzing request and available tools...",
                    "metadata": {"messages": len(messages)},
                }

                span.add_event("llm_call_stage_emitted")

                # Remove any existing 'tools' from kwargs to avoid duplicate parameters
                kwargs.pop("tools", None)

                # Convert messages to MCP format
                from client import Message, Role

                mcp_messages = [
                    Message(role=Role(msg["role"]), content=msg["content"]) for msg in messages
                ]

                # Call LLM with streaming enabled
                with self.tracer.start_as_current_span("agentic_client.generate") as agentic_span:
                    agentic_span.set_attribute("llm.stream", True)
                    agentic_span.set_attribute("llm.messages", len(mcp_messages))

                    response_stream = await self.agentic_client.generate(
                        messages=mcp_messages, stream=True, **kwargs
                    )

                # Track tool usage
                tool_calls_used = []
                tool_results_data = []
                tool_usage_map = {}  # Map tool name to tool_usage_id for updating results
                response_content = ""
                event_count = 0

                # Get tool result display setting (default False for cleaner output)
                show_tool_results = getattr(self, "show_tool_results", False)

                # Process streaming events
                with self.tracer.start_as_current_span("process_streaming_events") as stream_span:
                    async for event in response_stream:
                        event_count += 1
                        stream_span.add_event(
                            f"received_event_{event.type}", {"event_number": event_count}
                        )

                        if event.is_tool_call():
                            # Track tool calls
                            tool_name = (
                                event.metadata.get("tool_name") if event.metadata else "unknown"
                            )
                            tool_args = (
                                event.metadata.get("tool_args", {}) if event.metadata else {}
                            )

                            tool_calls_used.append({"name": tool_name, "args": tool_args})

                            # Record tool usage in real-time if we have a turn
                            tool_usage_id = None
                            if self.memory_manager and turn_id:
                                tool_usage_id = await self.memory_manager.record_tool_usage(
                                    turn_id=turn_id,
                                    entity_id=self.agent_id,
                                    tool_name=tool_name,
                                    tool_args=tool_args,
                                    requires_approval=False,  # TODO: Get from tool metadata
                                    trace_id=trace_id,
                                )

                                # Start execution immediately
                                if tool_usage_id:
                                    await self.memory_manager.start_tool_execution(tool_usage_id)
                                    # Map tool name to usage ID for result tracking
                                    tool_usage_map[tool_name] = tool_usage_id

                            # Emit tool call event with tool_usage_id
                            yield {
                                "stage": "tool_call",
                                "content": event.content or "",
                                "metadata": {
                                    **(event.metadata or {}),
                                    "tool_usage_id": tool_usage_id,
                                },
                            }
                        elif event.is_tool_result():
                            # Track tool results
                            tool_name = (
                                event.metadata.get("tool_name") if event.metadata else "unknown"
                            )
                            success = (
                                event.metadata.get("success", False) if event.metadata else False
                            )
                            result = event.metadata.get("result") if event.metadata else None
                            error = event.metadata.get("error") if event.metadata else None
                            duration_ms = (
                                event.metadata.get("duration_ms") if event.metadata else None
                            )

                            tool_results_data.append(
                                {
                                    "tool": tool_name,
                                    "success": success,
                                    "result": result,
                                    "error": error,
                                    "duration_ms": duration_ms,
                                }
                            )

                            # Update tool usage record with result
                            if self.memory_manager and tool_name in tool_usage_map:
                                tool_usage_id = tool_usage_map[tool_name]
                                await self.memory_manager.complete_tool_execution(
                                    tool_usage_id=tool_usage_id,
                                    success=success,
                                    result=result,
                                    error=error,
                                    duration_ms=duration_ms,
                                )

                            # Emit tool result event only if enabled
                            if show_tool_results:
                                yield {
                                    "stage": "tool_result",
                                    "content": event.content or "",
                                    "metadata": event.metadata,
                                }
                        elif event.is_content():
                            # This is the final response content
                            response_content = event.content or ""

                    stream_span.set_attribute("total_events", event_count)

                # Update conversation turn if we created one
                if self.memory_manager and turn_id:
                    turn_end_time = datetime.now()
                    total_duration_ms = (turn_end_time - turn_start_time).total_seconds() * 1000

                    await self.memory_manager.update_turn_completion(
                        turn_id=turn_id,
                        agent_response=response_content,
                        llm_context={
                            "messages": messages,
                            "model": kwargs.get("model", "unknown"),
                            "temperature": kwargs.get("temperature", 0.7),
                            "timestamp": turn_start_time.isoformat(),
                        },
                        tools_used=tool_calls_used,
                        tool_results=tool_results_data,
                        performance_metrics={
                            "total_duration_ms": total_duration_ms,
                            "llm_duration_ms": self.agentic_client.last_llm_duration_ms,
                            "tools_duration_ms": self.agentic_client.last_tools_duration_ms,
                        },
                        agent_metadata={
                            "agent_id": self.agent_id,
                            "timestamp": turn_end_time.isoformat(),
                            "model": kwargs.get("model", "unknown"),
                        },
                        status=TurnStatus.COMPLETED,
                    )

                span.add_event("response_stored")
                span.set_attribute("response.length", len(response_content))

                # Emit final response
                yield {
                    "stage": "response",
                    "content": response_content,
                    "metadata": {"final": True},
                }

        except Exception as e:
            # Handle errors by updating the turn status
            if self.memory_manager and turn_id:
                await self.memory_manager.update_turn_completion(
                    turn_id=turn_id,
                    agent_response="",
                    status=TurnStatus.ERROR,
                    error_details={
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "timestamp": datetime.now().isoformat(),
                    },
                )

            # Yield error stage instead of re-raising to allow graceful stream completion
            logger.error(f"Error in generate_stream_with_tools: {e}", exc_info=True)
            yield {
                "stage": "error",
                "content": f"An error occurred: {str(e)}",
                "metadata": {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "timestamp": datetime.now().isoformat(),
                },
            }
