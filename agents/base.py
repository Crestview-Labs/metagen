"""Base Agent - Clean implementation following agentic-loop-refactor-plan.md"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Optional, Union

from agents.tool_tracker import ToolTracker, TrackedTool
from client.llm_client import LLMClient
from client.models import ModelID
from common.messages import (
    AgentMessage,
    ApprovalDecision,
    ApprovalRequestMessage,
    ApprovalResponseMessage,
    Direction,
    ErrorMessage,
    Message,
    ThinkingMessage,
    ToolCallMessage,
    ToolCallRequest,
    ToolErrorMessage,
    ToolResultMessage,
    ToolStartedMessage,
    UsageMessage,
    UserMessage,
)
from common.models import ToolExecutionStage, TurnStatus
from common.types import (
    ToolCall,
    ToolCallResult,
    ToolErrorType,
    ToolExecution,
    TurnCompletionRequest,
    TurnCreationRequest,
)
from tools.base import Tool
from tools.registry import get_tool_executor

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all agents with clean agentic loop implementation."""

    def __init__(
        self,
        agent_id: str,
        instructions: str,
        memory_manager: Any,
        llm_config: Optional[dict] = None,
        mcp_servers: Optional[list] = None,
        available_tools: Optional[list[Tool]] = None,
        disabled_tools: Optional[set[str]] = None,
        llm_client: Optional[LLMClient] = None,
        model: Optional[str] = None,
        max_iterations: int = 5,
        show_tool_results: bool = False,
        **kwargs: Any,
    ) -> None:
        """Initialize base agent.

        Args:
            agent_id: Unique identifier for this agent
            instructions: System instructions for the agent
            memory_manager: Memory manager instance
            llm_config: LLM configuration dict (contains 'llm' and 'api_key')
            mcp_servers: List of MCP server instances
            available_tools: List of available tools
            disabled_tools: Set of tool names to disable for this agent
            llm_client: LLM client for generation (created from llm_config if not provided)
            model: Model to use for generation
            max_iterations: Maximum iterations for recursive tool calling
            show_tool_results: Whether to show tool results to user
            **kwargs: Additional arguments
        """
        self.agent_id = agent_id
        self.instructions = instructions
        self.memory_manager = memory_manager
        self.llm_config = llm_config
        self.mcp_servers = mcp_servers or []
        self.disabled_tools = disabled_tools or set()

        # Filter out disabled tools from available tools
        all_tools = available_tools or []
        self.tools = [tool for tool in all_tools if tool.name not in self.disabled_tools]

        self.llm_client = llm_client
        self.model = model
        self._max_iterations = max_iterations
        self.show_tool_results = show_tool_results

        # Tool approval configuration
        self._require_tool_approval = False
        self._auto_approve_tools: set[str] = set()
        self._approval_queue: Optional[asyncio.Queue] = None

        # Tool tracker - created per tool batch
        self._tool_tracker: Optional[ToolTracker] = None

        # Initialization state
        self._initialized = False

        logger.info(f"Created {self.__class__.__name__} with id: {agent_id}")

    async def initialize(self) -> None:
        """Initialize the agent."""
        if self._initialized:
            return

        # Create LLM client if not provided but config is available
        if not self.llm_client and self.llm_config:
            model_id = self.llm_config.get("llm", ModelID.CLAUDE_SONNET_4)
            self.llm_client = LLMClient(model=model_id, api_key=self.llm_config.get("api_key"))

        # Initialize LLM client
        if self.llm_client:
            await self.llm_client.initialize()

        self._initialized = True
        logger.info(f"Initialized agent {self.agent_id}")

    def configure_tool_approval(
        self,
        require_approval: bool = True,
        auto_approve_tools: Optional[list[str]] = None,
        approval_queue: Optional[asyncio.Queue] = None,
    ) -> None:
        """Configure tool approval settings.

        Args:
            require_approval: Whether to require approval for tools
            auto_approve_tools: List of tool names to auto-approve
            approval_queue: Queue for receiving approval messages
                (required if require_approval=True)
        """
        self._require_tool_approval = require_approval
        self._auto_approve_tools = set(auto_approve_tools or [])
        self._approval_queue = approval_queue

        if require_approval and not approval_queue:
            raise ValueError("approval_queue is required when require_approval=True")

        logger.info(
            f"Tool approval configured for {self.agent_id}: "
            f"require={require_approval}, auto_approve={list(self._auto_approve_tools)}"
        )

    async def stream_chat(self, message: Message) -> AsyncIterator[Message]:
        """Single entry point for all messages to agent.

        Handles message type switching:
        - UserMessage → generate_stream_with_tools
        - ApprovalResponseMessage → process approval

        Args:
            message: Any message type from the unified message system

        Yields:
            Response messages back to the user
        """
        if isinstance(message, UserMessage):
            # Build context including conversation history
            context_messages = await self.build_context(message.content)

            # Add the current user message to the context
            messages = context_messages + [message]

            # Stream the response
            async for response in self.generate_stream_with_tools(messages):
                yield response

        elif isinstance(message, ApprovalResponseMessage):
            logger.info(
                f"🔔 BaseAgent.stream_chat received ApprovalResponseMessage "
                f"for tool: {message.tool_id}"
            )
            # Process approval immediately
            await self._process_approval_response(message)
            # No yield - the blocked tool flow will continue and yield

        else:
            yield ErrorMessage(
                direction=Direction.AGENT_TO_USER,
                error=f"Unknown message type: {type(message).__name__}",
            )

    async def generate_stream_with_tools(
        self, messages: list[Message], **kwargs: Any
    ) -> AsyncIterator[Message]:
        """Generate streaming response with recursive tool support.

        Core loop that handles:
        1. LLM streaming
        2. Tool execution (inline)
        3. Recursive tool calls
        4. Message yielding
        """
        # Initialize
        turn_id = await self._create_turn(messages)

        # Yield initial thinking
        yield ThinkingMessage(content="Processing your request...")

        try:
            # Run the main conversation loop
            async for message in self._run_conversation_loop(turn_id, messages, **kwargs):
                yield message
        except Exception as e:
            # Handle any errors that occur during processing
            logger.error(f"Error in conversation loop: {e}", exc_info=True)

            # Yield error message to user
            yield ErrorMessage(direction=Direction.AGENT_TO_USER, error=str(e))

            # Complete the turn with error status
            await self._complete_turn_with_error(turn_id, str(e))
            raise

    async def _run_conversation_loop(
        self, turn_id: str, messages: list[Message], **kwargs: Any
    ) -> AsyncIterator[Message]:
        """Run the main conversation loop with tool support."""
        current_messages = messages.copy()
        iteration = 0

        # Track all content and tool usage for final turn update
        all_response_content = []
        all_tool_calls = []
        all_tool_results = []

        # For passing tool results between iterations
        previous_tool_calls = None
        previous_tool_results = None

        # For duplicate tool call prevention
        tool_call_history: dict[str, int] = {}  # key: "tool_name:args_hash" -> count

        # Main conversation loop
        while iteration < self._max_iterations:
            iteration += 1
            logger.debug(f"🔄 Agentic loop iteration {iteration}")

            # Get LLM stream (previous_tool_calls/results are None on first iteration)
            if not self.llm_client:
                raise RuntimeError("LLM client not initialized")

            llm_stream = self.llm_client.generate_stream_with_tools(
                current_messages,
                self.tools,
                tool_calls=previous_tool_calls,
                tool_results=previous_tool_results,
                **kwargs,
            )

            # Process this iteration
            content_buffer = ""
            tool_requests = None

            # Stream LLM response (now yields Message objects directly)
            last_agent_message = None
            async for message in llm_stream:
                # Set agent_id on all messages from LLM
                message.agent_id = self.agent_id

                if isinstance(message, AgentMessage):
                    content_buffer += message.content
                    last_agent_message = message
                    # Don't yield yet - we might need to set final=True
                    # yield message  # Now has correct agent_id

                elif isinstance(message, ToolCallMessage):
                    # If we had buffered agent message, yield it now (not final)
                    if last_agent_message:
                        yield last_agent_message
                        last_agent_message = None
                    # Store tool calls for processing
                    tool_requests = message.tool_calls
                    yield message  # Now has correct agent_id

                elif isinstance(message, UsageMessage):
                    yield message  # Now has correct agent_id

            # Track content
            if content_buffer:
                all_response_content.append(content_buffer)

            # Check if tools were requested
            if not tool_requests and content_buffer:
                # Got content but no tools, conversation complete
                # Mark the last agent message as final before yielding
                if last_agent_message:
                    last_agent_message.final = True
                    yield last_agent_message
                break
            elif last_agent_message:
                # Had content but also tools - yield the non-final message
                yield last_agent_message
            elif not tool_requests and not content_buffer:
                # No content and no tools - this shouldn't happen
                logger.error("LLM returned neither content nor tool requests")
                yield ErrorMessage(error="Unexpected empty response from LLM")
                break

            # Handle tool flow inline
            tool_executions = []
            assert tool_requests is not None  # We checked above that we have tool requests
            async for item in self._handle_tool_flow(tool_requests, turn_id, tool_call_history):
                if isinstance(item, Message):
                    # Yield messages as they come
                    yield item
                elif isinstance(item, list):
                    # Final result - list of executions
                    tool_executions = item
                    break

            if not tool_executions:
                # No tools executed (timeout/error)
                break

            # Track executions for final turn update
            for execution in tool_executions:
                all_tool_calls.append(execution.tool_call)
                all_tool_results.append(execution.result)

            # Prepare for next iteration
            previous_tool_calls = [ex.tool_call for ex in tool_executions]
            previous_tool_results = [ex.result for ex in tool_executions]

            logger.info(
                f"🎯 Iteration {iteration} complete, tool results: "
                f"{[r.content[:50] for r in previous_tool_results]}"
            )

            # Clear for next iteration
            tool_requests = None

            # Loop continues...

        # Warn if hit iteration limit
        if iteration >= self._max_iterations:
            logger.warning(f"Hit max iterations ({self._max_iterations})")
            yield ErrorMessage(
                error="Maximum conversation iterations reached", details={"iterations": iteration}
            )

        # Complete turn with all data
        await self._complete_turn(turn_id, all_response_content, all_tool_calls, all_tool_results)

    async def _handle_tool_flow(
        self, tool_requests: list[ToolCallRequest], turn_id: str, tool_call_history: dict[str, int]
    ) -> AsyncIterator[Union[Message, list[ToolExecution]]]:
        """Handle complete tool flow including approvals.

        This generator:
        1. Yields Messages during execution
        2. Returns list[ToolExecution] as final yield

        Flow:
        - Create ToolTracker
        - Add tools (determine approval needs)
        - Handle approvals if needed
        - Execute tools
        - Yield results
        """
        # Create tracker for this tool batch
        assert self._tool_tracker is None, "ToolTracker should be None"

        self._tool_tracker = ToolTracker(memory_manager=self.memory_manager, agent_id=self.agent_id)

        # Process all tool requests
        valid_tools = 0
        max_repeated_calls = 3  # Configurable limit

        for request in tool_requests:
            tool_id = request.tool_id
            tool_name = request.tool_name
            tool_args = request.tool_args

            # Check for duplicate tool calls
            tool_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
            call_count = tool_call_history.get(tool_key, 0)

            if call_count >= max_repeated_calls:
                # Reject due to too many repeated calls
                tracked_tool = TrackedTool(
                    tool_id=tool_id,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    stage=ToolExecutionStage.REJECTED,
                    agent_id=self.agent_id,
                    turn_id=turn_id,
                    error=f"Tool '{tool_name}' called too many times with same arguments",
                )
            else:
                # Validate tool exists
                tool = self._find_tool(tool_name)
                if not tool:
                    # Add as rejected
                    tracked_tool = TrackedTool(
                        tool_id=tool_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        stage=ToolExecutionStage.REJECTED,
                        agent_id=self.agent_id,
                        turn_id=turn_id,
                        error="Tool not found",
                    )
                else:
                    # Update call history
                    tool_call_history[tool_key] = call_count + 1

                    # Check if needs approval
                    needs_approval = self._tool_requires_approval(tool_name)
                    tracked_tool = TrackedTool(
                        tool_id=tool_id,
                        tool_name=tool_name,
                        tool_args=tool_args,
                        stage=(
                            ToolExecutionStage.PENDING_APPROVAL
                            if needs_approval
                            else ToolExecutionStage.APPROVED
                        ),
                        agent_id=self.agent_id,
                        turn_id=turn_id,
                    )
                    valid_tools += 1

            await self._tool_tracker.add_tool(tracked_tool)

        # No valid tools?
        if valid_tools == 0:
            self._tool_tracker = None
            yield []  # Empty execution list
            return

        # Check for pending approvals
        pending_tools: list[TrackedTool] = self._tool_tracker.get_tools_by_stage(
            ToolExecutionStage.PENDING_APPROVAL
        )

        if pending_tools:
            # Emit approval requests
            for tool in pending_tools:  # type: ignore[assignment]
                assert isinstance(tool, TrackedTool)  # Help mypy understand
                yield ApprovalRequestMessage(
                    agent_id=self.agent_id,
                    tool_id=tool.tool_id,
                    tool_name=tool.tool_name,
                    tool_args=tool.tool_args,
                )

            # Wait for ALL approvals to complete
            # ToolTracker will receive approvals one at a time via _process_approval_response
            # It will only signal when ALL pending tools have been approved/rejected
            approval_event = self._tool_tracker.wait_for_approvals()

            logger.info(f"Waiting for {len(pending_tools)} tool approvals...")

            # Must have approval queue configured
            assert self._approval_queue is not None, (
                "Approval queue must be configured for tool approval"
            )

            await self._wait_for_approvals_from_queue(
                pending_tools, self._approval_queue, approval_event
            )

        # Get all tools to execute
        approved_tools: list[TrackedTool] = self._tool_tracker.get_tools_by_stage(
            ToolExecutionStage.APPROVED
        )
        rejected_tools: list[TrackedTool] = self._tool_tracker.get_tools_by_stage(
            ToolExecutionStage.REJECTED
        )

        # Emit execution started events for approved tools
        for tool in approved_tools:  # type: ignore[assignment]
            assert isinstance(tool, TrackedTool)  # Help mypy understand
            yield ToolStartedMessage(tool_id=tool.tool_id, tool_name=tool.tool_name)

        # Execute all tools (approved and rejected)
        execution_results = await self._execute_approved_tools()

        # Build final execution list and yield results
        executions = []

        for result in execution_results:
            # Find tracked tool
            all_tools = approved_tools + rejected_tools
            found_tool: Optional[TrackedTool] = next(
                (t for t in all_tools if t.tool_id == result.tool_call_id), None
            )

            if not found_tool:
                logger.error(f"No tracked tool for result: {result.tool_call_id}")
                continue

            # Create tool call
            tool_call = ToolCall(
                id=found_tool.tool_id, name=found_tool.tool_name, arguments=found_tool.tool_args
            )

            # Create execution record
            executions.append(ToolExecution(tool_call=tool_call, result=result))

            # Yield result message
            assert result.tool_call_id is not None  # We always set tool_call_id
            if result.is_error:
                yield ToolErrorMessage(
                    tool_id=result.tool_call_id,
                    tool_name=result.tool_name,
                    error=result.error or "Unknown error",
                )
            else:
                # Only yield tool result if configured to show them
                if self.show_tool_results:
                    yield ToolResultMessage(
                        tool_id=result.tool_call_id,
                        tool_name=result.tool_name,
                        result=result.content,  # Full content
                    )

        # Clean up tracker
        self._tool_tracker = None

        # Return executions as final yield
        logger.info(f"🎯 _handle_tool_flow returning {len(executions)} executions")
        yield executions

    async def _process_approval_response(self, approval: ApprovalResponseMessage) -> None:
        """Process tool approval response.

        Updates ToolTracker with the decision.
        ToolTracker will automatically signal when all approvals are complete.
        """
        logger.info(f"🎯 BaseAgent._process_approval_response called for tool: {approval.tool_id}")

        if not self._tool_tracker:
            logger.error(f"No active ToolTracker for approval: {approval.tool_id}")
            return

        # Validate the tool exists in tracker
        tool = self._tool_tracker.get_tool(approval.tool_id)
        if not tool:
            logger.error(f"Unexpected approval for tool: {approval.tool_id}")
            return

        # Validate it's actually pending approval
        if tool.stage != ToolExecutionStage.PENDING_APPROVAL:
            logger.warning(
                f"Tool {approval.tool_id} not pending approval, current stage: {tool.stage}"
            )
            return

        # Update tool state
        if approval.decision == ApprovalDecision.APPROVED.value:
            await self._tool_tracker.update_stage(
                approval.tool_id, ToolExecutionStage.APPROVED, user_feedback=approval.feedback
            )
            logger.info(f"Tool {approval.tool_id} approved")
        else:
            await self._tool_tracker.update_stage(
                approval.tool_id, ToolExecutionStage.REJECTED, user_feedback=approval.feedback
            )
            logger.info(f"Tool {approval.tool_id} rejected: {approval.feedback}")

        # ToolTracker will check if all approvals are complete
        # and signal the waiting event if so

    async def _wait_for_approvals_from_queue(
        self,
        pending_tools: list[TrackedTool],
        approval_queue: asyncio.Queue,
        approval_event: asyncio.Event,
    ) -> None:
        """Wait for approval messages by monitoring the input queue in a separate task.

        Creates a task that pulls messages from the input queue and processes approvals,
        while the main coroutine waits on the approval event.

        Args:
            pending_tools: List of tools waiting for approval
            approval_queue: The agent's input queue to pull messages from
            approval_event: Event that will be set when all approvals are complete
        """
        pending_count = len(pending_tools)
        logger.info(f"Starting queue monitor for {pending_count} tool approvals...")

        async def queue_monitor() -> None:
            """Monitor the input queue for approval messages."""
            while not approval_event.is_set():
                try:
                    # Use wait_for to avoid blocking forever
                    message = await asyncio.wait_for(approval_queue.get(), timeout=0.1)

                    # We should ONLY receive approval messages while waiting
                    assert isinstance(message, ApprovalResponseMessage), (
                        f"Expected ApprovalResponseMessage while waiting for approvals, "
                        f"got {type(message).__name__}"
                    )

                    logger.info(f"Queue monitor received approval for tool: {message.tool_id}")

                    # Process the approval
                    await self._process_approval_response(message)

                except asyncio.TimeoutError:
                    continue
                except AssertionError as e:
                    logger.error(f"Protocol violation: {e}")
                    raise
                except Exception as e:
                    logger.error(f"Error monitoring queue for approvals: {e}", exc_info=True)
                    raise

        # Start the queue monitor task
        monitor_task = asyncio.create_task(queue_monitor())

        try:
            # Wait for all approvals to complete
            await approval_event.wait()
            logger.info("All tool approvals resolved via queue monitoring")
        finally:
            # Clean up the monitor task
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass

    def _find_tool(self, tool_name: str) -> Optional[Tool]:
        """Find a tool by name."""
        return next((t for t in self.tools if t.name == tool_name), None)

    def _tool_requires_approval(self, tool_name: str) -> bool:
        """Check if a tool requires approval."""
        return self._require_tool_approval and tool_name not in self._auto_approve_tools

    async def _execute_approved_tools(self) -> list[ToolCallResult]:
        """Execute all approved tools."""
        if not self._tool_tracker:
            return []

        # Get approved tools
        approved_tools = self._tool_tracker.get_tools_by_stage(ToolExecutionStage.APPROVED)

        # Execute them
        results = []
        for tool in approved_tools:  # type: ignore[assignment]
            # Update stage to executing
            await self._tool_tracker.update_stage(tool.tool_id, ToolExecutionStage.EXECUTING)

            # Execute the tool
            try:
                executor = get_tool_executor()
                # Create ToolCall object
                tool_call = ToolCall(id=tool.tool_id, name=tool.tool_name, arguments=tool.tool_args)
                result = await executor.execute(tool_call)

                # Update tracker with result
                await self._tool_tracker.update_stage(
                    tool.tool_id, ToolExecutionStage.COMPLETED, result=result
                )
                results.append(result)

            except Exception as e:
                logger.error(f"Tool execution failed: {e}")
                error_result = ToolCallResult(
                    tool_name=tool.tool_name,
                    tool_call_id=tool.tool_id,
                    content=str(e),
                    is_error=True,
                    error=str(e),
                    error_type=ToolErrorType.EXECUTION_ERROR,
                    user_display=None,
                )

                await self._tool_tracker.update_stage(
                    tool.tool_id, ToolExecutionStage.FAILED, error=str(e)
                )

                results.append(error_result)

        # Also include rejected tools as error results
        rejected_tools = self._tool_tracker.get_tools_by_stage(ToolExecutionStage.REJECTED)

        for tool in rejected_tools:  # type: ignore[assignment]
            error_result = ToolCallResult(
                tool_name=tool.tool_name,
                tool_call_id=tool.tool_id,
                content=tool.error or "Tool rejected",
                is_error=True,
                error=tool.error or "Tool rejected",
                error_type=ToolErrorType.USER_REJECTED
                if tool.user_feedback
                else ToolErrorType.INVALID_ARGS,
                user_display=tool.user_feedback,
            )
            results.append(error_result)

        return results

    async def _create_turn(self, messages: list[Message]) -> str:
        """Create a new conversation turn."""
        # Extract user message
        user_message = next(
            (msg.content for msg in reversed(messages) if isinstance(msg, UserMessage)), ""
        )

        # Create turn request
        request = TurnCreationRequest(
            user_query=user_message,
            agent_id=self.agent_id,
            task_id=self.get_current_task_id(),
            user_metadata={"timestamp": datetime.now().isoformat()},
        )

        # Create turn with IN_PROGRESS status
        turn_id: str = await self.memory_manager.create_turn(request)
        return turn_id

    async def _complete_turn(
        self,
        turn_id: str,
        response_content: list[str],
        tool_calls: list[ToolCall],
        tool_results: list[ToolCallResult],
    ) -> None:
        """Complete a conversation turn."""
        # Join all response content
        final_response = "\n".join(response_content)

        # Create completion request
        request = TurnCompletionRequest(
            turn_id=turn_id,
            agent_response=final_response,
            tool_calls=tool_calls,
            tool_results=tool_results,
            status=TurnStatus.COMPLETED,
        )

        # Complete the turn
        await self.memory_manager.complete_turn(request)

    async def _complete_turn_with_error(self, turn_id: str, error_message: str) -> None:
        """Complete a conversation turn with error status."""
        # Create completion request with error
        request = TurnCompletionRequest(
            turn_id=turn_id,
            agent_response="",
            tool_calls=[],
            tool_results=[],
            status=TurnStatus.ERROR,
            error_details=error_message,
        )

        # Complete the turn
        await self.memory_manager.complete_turn(request)

    def get_current_task_id(self) -> Optional[str]:
        """Get current task ID - override in subclasses."""
        return None

    @abstractmethod
    async def build_context(self, query: str) -> list[Message]:
        """Build relevant context for a query.

        This single method replaces all the overlapping context methods.
        It searches across conversations, compact memories, and semantic memories
        to build the most relevant context for the given query.

        Args:
            query: The query to build context for

        Returns:
            List of Message objects (UserMessage/AgentMessage) for context
        """
        pass

    async def cleanup(self) -> None:
        """Clean up resources."""
        # Clean up any pending tool trackers
        self._tool_tracker = None

    async def get_available_tools(self) -> list[Tool]:
        """Get list of available tools for this agent."""
        return self.tools

    async def get_current_model(self) -> Optional[str]:
        """Get current model being used."""
        return self.model

    def is_initialized(self) -> bool:
        """Check if agent is initialized."""
        return self._initialized

    def get_agent_info(self) -> dict[str, Any]:
        """Get agent information."""
        return {
            "agent_id": self.agent_id,
            "agent_type": self.__class__.__name__,
            "model": self.model,
            "tools": [t.name for t in self.tools],
            "tool_approval_required": self._require_tool_approval,
            "auto_approve_tools": list(self._auto_approve_tools),
            "initialized": self._initialized,
        }
