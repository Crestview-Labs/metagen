"""Base Agent - Abstract base class for all agents with context-aware memory."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from opentelemetry import trace

from agents.tool_approval import (
    ToolApprovalDecision,
    ToolApprovalRequest,
    ToolApprovalResponse,
    ToolPendingApproval,
)
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

        # Tool approval configuration
        self._require_tool_approval: bool = False
        self._auto_approve_tools: set[str] = set()
        self._approval_timeout: float = 30.0
        self._approval_response_queue: Optional[asyncio.Queue] = None
        self._pending_approvals: dict[str, ToolPendingApproval] = {}

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

    def configure_tool_approval(
        self,
        require_approval: bool = False,
        auto_approve_tools: Optional[set[str]] = None,
        approval_timeout: float = 30.0,
        approval_response_queue: Optional[asyncio.Queue] = None,
    ) -> None:
        """Configure tool approval settings for the agent.

        Args:
            require_approval: Whether to require approval for tool execution
            auto_approve_tools: Set of tool names that don't need approval
            approval_timeout: Timeout in seconds for approval (default 30s)
            approval_response_queue: Queue to receive approval responses
        """
        self._require_tool_approval = require_approval
        self._auto_approve_tools = auto_approve_tools or set()
        self._approval_timeout = approval_timeout
        self._approval_response_queue = approval_response_queue

        if require_approval and not approval_response_queue:
            raise ValueError(
                "approval_response_queue must be provided when require_approval is True"
            )

        logger.info(
            f"Tool approval configured for {self.agent_id}: "
            f"require={require_approval}, auto_approve={list(self._auto_approve_tools)}"
        )

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

    async def _handle_tool_call_event(
        self,
        event: Any,
        turn_id: Optional[str],
        trace_id: Optional[str],
        tool_usage_map: dict[str, str],
    ) -> AsyncIterator[dict[str, Any]]:
        """Handle tool call events including approval flow.

        Non-blocking implementation:
        - If approval needed: yields request and stores pending state
        - If approved/auto-approved: proceeds with execution

        Args:
            event: The tool call event from the stream
            turn_id: Current conversation turn ID
            trace_id: Tracing ID for observability
            tool_usage_map: Map of tool names to usage IDs

        Yields:
            Events for tool approval, tool call, etc.
        """
        # Extract tool information
        tool_name = event.metadata.get("tool_name", "unknown") if event.metadata else "unknown"
        tool_args = event.metadata.get("tool_args", {}) if event.metadata else {}

        # Check if tool requires approval
        # TODO: Move disabled_tools to Agent level and pass to AgenticClient
        needs_approval = self._require_tool_approval and tool_name not in self._auto_approve_tools

        # Record tool usage in database
        tool_usage_id = None
        if self.memory_manager and turn_id:
            try:
                tool_usage_id = await self.memory_manager.record_tool_usage(
                    turn_id=turn_id,
                    entity_id=self.agent_id,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    requires_approval=needs_approval,
                    trace_id=trace_id,
                )
            except Exception as e:
                logger.error(f"Failed to record tool usage: {e}")

        # Handle approval if needed
        if needs_approval:
            # Create approval request
            approval_request = ToolApprovalRequest(
                tool_id=tool_usage_id or "unknown",
                tool_name=tool_name,
                tool_args=tool_args,
                agent_id=self.agent_id,
                description=f"Execute {tool_name} with provided arguments",
                risk_level="medium",  # TODO: Determine from tool metadata
            )

            # Create and store pending approval
            pending = ToolPendingApproval(
                tool_id=tool_usage_id or "unknown",
                tool_name=tool_name,
                tool_args=tool_args,
                turn_id=turn_id,
                trace_id=trace_id,
                tool_usage_id=tool_usage_id,
                original_event=event,
            )
            self._pending_approvals[pending.tool_id] = pending

            # Yield approval request event (non-blocking!)
            yield {
                "stage": "tool_approval_request",
                "content": f"{tool_name}({', '.join(f'{k}={v}' for k, v in tool_args.items())})",
                "metadata": {
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_id": tool_usage_id,
                    "approval_request": approval_request.to_dict(),
                },
            }

            logger.info(
                f"Tool {tool_name} requires approval - request sent (tool_id: {tool_usage_id})"
            )
            # Don't execute - wait for approval response
            return

        # Auto-approved or no approval required - proceed with execution
        if self.memory_manager and tool_usage_id:
            try:
                await self.memory_manager.start_tool_execution(tool_usage_id)
                tool_usage_map[tool_name] = tool_usage_id
            except Exception as e:
                logger.error(f"Failed to start tool execution: {e}")

        # Emit tool call event
        yield {
            "stage": "tool_call",
            "content": event.content or "",
            "metadata": {**(event.metadata or {}), "tool_usage_id": tool_usage_id},
        }

    async def _handle_tool_result_event(
        self,
        event: Any,
        tool_usage_map: dict[str, str],
        tool_results_data: list[dict[str, Any]],
        show_tool_results: bool,
    ) -> AsyncIterator[dict[str, Any]]:
        """Handle tool result events.

        Args:
            event: The tool result event
            tool_usage_map: Map of tool names to usage IDs
            tool_results_data: List to append result data to
            show_tool_results: Whether to yield tool result events

        Yields:
            Tool result events if show_tool_results is True
        """
        # Extract result information
        tool_name = event.metadata.get("tool_name", "unknown") if event.metadata else "unknown"
        success = event.metadata.get("success", False) if event.metadata else False
        result = event.metadata.get("result") if event.metadata else None
        error = event.metadata.get("error") if event.metadata else None
        duration_ms = event.metadata.get("duration_ms") if event.metadata else None

        # Track result data
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
            try:
                await self.memory_manager.complete_tool_execution(
                    tool_usage_id=tool_usage_id,
                    success=success,
                    result=result,
                    error=error,
                    duration_ms=duration_ms,
                )
            except Exception as e:
                logger.error(f"Failed to update tool execution result: {e}")

        # Emit tool result event only if enabled
        if show_tool_results:
            yield {
                "stage": "tool_result",
                "content": event.content or "",
                "metadata": event.metadata,
            }

    async def _handle_content_event(self, event: Any) -> str:
        """Handle content events.

        Args:
            event: The content event

        Returns:
            The response content
        """
        return event.content or ""

    async def process_approval_response(
        self, approval_response: ToolApprovalResponse
    ) -> AsyncIterator[dict[str, Any]]:
        """Process a tool approval response asynchronously.

        This method handles the second phase of tool approval:
        - Validates the tool ID
        - Updates the database
        - Executes approved tools
        - Cleans up pending state

        Args:
            approval_response: The approval response from the user

        Yields:
            Events for tool execution or rejection
        """
        tool_id = approval_response.tool_id

        # Validate that we have a pending approval for this tool
        pending = self._pending_approvals.get(tool_id)
        if not pending:
            # This could happen if:
            # 1. The approval already timed out and was cleaned up
            # 2. The tool_id is invalid
            # 3. The approval was already processed
            logger.warning(
                f"No pending approval found for tool_id: {tool_id}. "
                f"It may have already timed out or been processed."
            )

            # Still update the database if we can (for record keeping)
            if self.memory_manager and tool_id and tool_id != "unknown":
                try:
                    await self.memory_manager.update_tool_approval(
                        tool_id,
                        approved=approval_response.decision == ToolApprovalDecision.APPROVED,
                        user_feedback=approval_response.feedback or "Received after timeout",
                    )
                except Exception as e:
                    logger.error(f"Failed to update late approval in database: {e}")

            # Yield an informational event
            yield {
                "stage": "tool_approval_late",
                "content": f"Approval received too late for tool {tool_id}",
                "metadata": {
                    "tool_id": tool_id,
                    "decision": approval_response.decision.value,
                    "reason": "No pending approval found - likely timed out",
                },
            }
            return

        # Remove from pending approvals
        del self._pending_approvals[tool_id]

        # Update database with decision
        if self.memory_manager and pending.tool_usage_id:
            try:
                await self.memory_manager.update_tool_approval(
                    pending.tool_usage_id,
                    approved=approval_response.decision == ToolApprovalDecision.APPROVED,
                    user_feedback=approval_response.feedback,
                )
            except Exception as e:
                logger.error(f"Failed to update tool approval in database: {e}")

        # Handle based on decision
        if approval_response.decision == ToolApprovalDecision.APPROVED:
            # Emit approval event
            yield {
                "stage": "tool_approved",
                "content": f"Tool approved: {pending.tool_name}",
                "metadata": {"tool_name": pending.tool_name, "tool_id": tool_id},
            }

            # Execute the tool
            if self.memory_manager and pending.tool_usage_id:
                try:
                    await self.memory_manager.start_tool_execution(pending.tool_usage_id)
                except Exception as e:
                    logger.error(f"Failed to start tool execution: {e}")

            # Emit tool call event (reuse original event data)
            yield {
                "stage": "tool_call",
                "content": pending.original_event.content if pending.original_event else "",
                "metadata": {
                    **(pending.original_event.metadata if pending.original_event else {}),
                    "tool_usage_id": pending.tool_usage_id,
                },
            }

            # Note: The actual tool execution will happen in the agentic client
            # and results will flow through the normal stream

        else:
            # Tool was rejected or timed out
            yield {
                "stage": "tool_rejected",
                "content": f"Tool rejected: {pending.tool_name}",
                "metadata": {
                    "tool_name": pending.tool_name,
                    "tool_id": tool_id,
                    "feedback": approval_response.feedback,
                    "decision": approval_response.decision.value,
                },
            }

            logger.info(
                f"Tool {pending.tool_name} was {approval_response.decision.value} "
                f"with feedback: {approval_response.feedback}"
            )

    async def check_expired_approvals(self) -> list[dict[str, Any]]:
        """Check for and handle expired approval requests.

        This should be called periodically to clean up timed-out requests.

        Returns:
            List of timeout events that should be yielded to the stream
        """

        expired_ids = []
        timeout_events = []

        for tool_id, pending in self._pending_approvals.items():
            if pending.is_expired(self._approval_timeout):
                expired_ids.append(tool_id)

        # Process expired approvals
        for tool_id in expired_ids:
            pending = self._pending_approvals[tool_id]
            logger.warning(f"Tool approval timed out for {pending.tool_name} (tool_id: {tool_id})")

            # Remove from pending
            del self._pending_approvals[tool_id]

            # Update database (create a task to run async operation)
            if self.memory_manager and pending.tool_usage_id:

                async def update_timeout(usage_id: str) -> None:
                    try:
                        await self.memory_manager.update_tool_approval(
                            usage_id, approved=False, user_feedback="Approval request timed out"
                        )
                    except Exception as e:
                        logger.error(f"Failed to update timeout in database: {e}")

                # Fire and forget the database update
                asyncio.create_task(update_timeout(pending.tool_usage_id))

            # Create timeout event
            timeout_events.append(
                {
                    "stage": "tool_rejected",
                    "content": f"Tool timed out: {pending.tool_name}",
                    "metadata": {
                        "tool_name": pending.tool_name,
                        "tool_id": tool_id,
                        "feedback": "Approval request timed out",
                        "decision": ToolApprovalDecision.TIMEOUT.value,
                    },
                }
            )

        return timeout_events

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
                            # Track tool calls for later reporting
                            tool_name = (
                                event.metadata.get("tool_name") if event.metadata else "unknown"
                            )
                            tool_args = (
                                event.metadata.get("tool_args", {}) if event.metadata else {}
                            )
                            tool_calls_used.append({"name": tool_name, "args": tool_args})

                            # Delegate to handler
                            async for handler_event in self._handle_tool_call_event(
                                event, turn_id, trace_id, tool_usage_map
                            ):
                                yield handler_event
                        elif event.is_tool_result():
                            # Delegate to handler
                            async for handler_event in self._handle_tool_result_event(
                                event, tool_usage_map, tool_results_data, show_tool_results
                            ):
                                yield handler_event
                        elif event.is_content():
                            # Delegate to handler
                            response_content = await self._handle_content_event(event)

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
