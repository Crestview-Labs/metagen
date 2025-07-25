"""Agentic Client - LLM client with tool calling capabilities using unified tool system."""

import json
import logging
import time
from typing import Any, AsyncIterator, Optional, Union

from opentelemetry import trace

from client.base_client import (
    TOOL_ERROR_MESSAGES,
    BaseClient,
    GenerationResponse,
    Message,
    Role,
    StreamChunk,
    StreamEvent,
    ToolErrorType,
    ToolResult,
)
from client.factory import LLMClientFactory
from client.mcp_server import MCPServer
from client.models import ModelID, get_model
from tools.registry import get_tool_executor, get_tool_registry

logger = logging.getLogger(__name__)

# DISABLED TOOLS: Memory tools temporarily disabled for TypeScript CLI migration
DISABLED_TOOLS = {
    "memory_search",
    "compact_conversation",
    "get_recent_conversations",  # Also disable this memory-related tool
}


class AgenticClient(BaseClient):
    """
    Agentic Client that integrates LLM with tool calling capabilities.

    Uses MCPServer instances to manage server lifecycle separately from client logic.
    """

    def __init__(
        self,
        llm: ModelID = ModelID.CLAUDE_SONNET_4,
        api_key: Optional[str] = None,
        mcp_servers: Optional[list[MCPServer]] = None,
    ):
        """
        Initialize MCP client with unified tool system.

        Args:
            llm: Model ID enum
            api_key: API key (optional, will use environment or .env)
            mcp_servers: List of MCPServer instances (optional)
        """
        # Create LLM provider first
        self.llm_provider = self._create_llm_client(llm, api_key)
        # Then initialize parent with explicit api_key
        super().__init__(api_key=api_key)

        self.mcp_servers = mcp_servers or []
        self._initialized = False
        self.tracer = trace.get_tracer(__name__)
        self._recent_tool_calls: list[dict[str, Any]] = []  # For deduplication in agentic loops

        # Performance metrics
        self.last_llm_duration_ms: float = 0
        self.last_tools_duration_ms: float = 0

        # Per-instance tool filtering (in addition to global disabled tools)
        self.disabled_tools: set[str] = set()

        # Initialize unified tool system
        self.tool_registry = get_tool_registry()
        self.tool_executor = get_tool_executor()

    def add_server(self, server: MCPServer) -> None:
        """Add an MCPServer instance to this client."""
        if self._initialized:
            raise RuntimeError("Cannot add servers after initialization")
        self.mcp_servers.append(server)

    def _get_api_key(self) -> str:
        """Get API key from underlying LLM client."""
        return getattr(self.llm_provider, "api_key", "mcp-client")

    def _create_llm_client(self, llm: ModelID, api_key: Optional[str]) -> BaseClient:
        """Create LLM client from ModelID."""
        # Get model info from ModelID
        model_info = get_model(llm.value)
        provider_name = model_info.provider.value
        model = llm.value

        factory = LLMClientFactory()
        return factory.create_client(provider_name, model=model, api_key=api_key)

    async def initialize(self, tool_dependencies: Optional[dict[str, Any]] = None) -> None:
        """Initialize the MCP client, LLM, and unified tool system.

        Args:
            tool_dependencies: Optional dependencies for tools (e.g., memory_manager, llm_client)
        """
        if self._initialized:
            return

        # Initialize the underlying LLM client
        await self.llm_provider.initialize()

        # Configure tool dependencies if provided
        if tool_dependencies:
            from tools.registry import configure_tool_dependencies

            configure_tool_dependencies(tool_dependencies)

        # Configure disabled tools
        self.tool_registry.set_disabled_tools(DISABLED_TOOLS)

        # Discover and register all tools (core + MCP)
        await self.tool_registry.discover_and_register_tools(
            core_tools_dir="tools/core", mcp_servers=self.mcp_servers
        )

        self._initialized = True

        # Log available tools
        all_tools = self.tool_registry.get_all_tools()
        core_tool_count = len(self.tool_executor.core_tools)
        mcp_tool_count = len(all_tools) - core_tool_count
        logger.info(
            f"MCP client initialized with {len(all_tools)} tools "
            f"({core_tool_count} core, {mcp_tool_count} MCP)"
        )

    def _should_continue_tool_loop(
        self,
        iteration: int,
        max_iterations: int,
        tokens_used: int,
        max_token_budget: int,
        current_response: GenerationResponse,
    ) -> bool:
        """
        Smart loop protection - determines if tool loop should continue.

        Args:
            iteration: Current iteration number
            max_iterations: Maximum allowed iterations
            tokens_used: Total tokens used so far
            max_token_budget: Maximum token budget
            current_response: Current LLM response

        Returns:
            bool: True if loop should continue, False otherwise
        """
        # Hard limits
        if iteration >= max_iterations:
            logger.info(f"🔍 DEBUG: Stopping tool loop - max iterations reached ({max_iterations})")
            return False
        if tokens_used >= max_token_budget:
            logger.info(
                f"🔍 DEBUG: Stopping tool loop - token budget exceeded "
                f"({tokens_used}/{max_token_budget})"
            )
            return False

        # No tool calls = natural termination
        if not (hasattr(current_response, "tool_calls") and current_response.tool_calls):
            logger.info("🔍 DEBUG: Stopping tool loop - no more tool calls")
            return False

        # Continue the loop - let individual tool execution handle limits
        return True

    async def generate(
        self,
        messages: list[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Union[GenerationResponse, AsyncIterator[StreamEvent]]:
        """
        Generate text with tool calling capabilities.

        This method orchestrates LLM + tool calling.
        """
        if not self._initialized:
            await self.initialize()

        # Get all tools from unified registry (core + MCP, filtered by global and
        # per-instance disabled tools)
        all_tools = self.tool_registry.get_all_tools()
        llm_tools = [tool for tool in all_tools if tool["name"] not in self.disabled_tools]

        # Get initial response from LLM with tools
        logger.info(
            f"🔍 DEBUG: Sending {len(messages)} messages to LLM with "
            f"{len(llm_tools)} available tools"
        )
        logger.info(f"🔍 DEBUG: Available tools: {[t['name'] for t in llm_tools]}")
        logger.info(
            f"🔍 DEBUG: Total message length: {sum(len(m.content) for m in messages)} chars"
        )

        # Track LLM timing
        llm_start_time = time.time()
        response = await self.llm_provider.generate(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
            tools=llm_tools,
            **kwargs,
        )
        self.last_llm_duration_ms = (time.time() - llm_start_time) * 1000

        if stream:
            # For streaming, we need to handle tool calls differently
            return await self._handle_streaming_with_tools(
                messages, model, temperature, max_tokens, **kwargs
            )

        # At this point, response must be GenerationResponse since stream=False
        assert isinstance(response, GenerationResponse)

        # Handle tool calls if any
        if hasattr(response, "tool_calls") and response.tool_calls:
            logger.info(
                f"🔍 DEBUG: LLM decided to use tools: "
                f"{[tc.get('name') for tc in response.tool_calls]}"
            )
            return await self._handle_tool_calls(
                messages, response, model, temperature, max_tokens, **kwargs
            )
        else:
            logger.info(
                f"🔍 DEBUG: LLM response without tool calls - length: "
                f"{len(response.content) if response.content else 0} chars"
            )
            return response

    async def _handle_tool_calls(
        self,
        messages: list[Message],
        initial_response: GenerationResponse,
        model: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> GenerationResponse:
        """Handle tool calls with safe agentic loop."""
        current_messages = messages.copy()
        current_response = initial_response

        # Safe agentic loop configuration
        # TODO: Make max_iterations and max_token_budget configurable parameters
        max_iterations = 100  # Allow many iterations for complex tasks
        max_token_budget = 1000000  # Allow up to 1M tokens for complex tasks
        iteration = 0
        tokens_used = 0

        # Reset tool call tracking for this conversation
        self._recent_tool_calls = []

        # Get all tools from unified registry for subsequent calls (filtered)
        all_tools = self.tool_registry.get_all_tools()
        llm_tools = [tool for tool in all_tools if tool["name"] not in self.disabled_tools]

        while self._should_continue_tool_loop(
            iteration, max_iterations, tokens_used, max_token_budget, current_response
        ):
            iteration += 1
            logger.info(f"🔍 DEBUG: Safe agentic loop iteration {iteration}/{max_iterations}")
            logger.info(
                f"🔍 DEBUG: Current message count: {len(current_messages)}, "
                f"tokens used: {tokens_used}"
            )

            # Check tool execution limits
            total_tools_called = len(self._recent_tool_calls)
            tool_call_counts: dict[str, int] = {}
            for tc in self._recent_tool_calls:
                key = f"{tc['name']}:{json.dumps(tc['args'], sort_keys=True)}"
                tool_call_counts[key] = tool_call_counts.get(key, 0) + 1

            # Execute all tool calls
            tool_results = []
            tools_total_duration_ms = 0
            for i, tool_call in enumerate(current_response.tool_calls or []):
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("arguments", {})

                # Skip if no tool name
                if not tool_name:
                    logger.warning(f"Tool call {i + 1} has no name, skipping")
                    continue
                tool_call_id = tool_call.get("id", f"call_{i}")
                logger.info(
                    f"🔍 DEBUG: Tool call {i + 1}/{len(current_response.tool_calls or [])}: "
                    f"'{tool_name}' with args: {tool_args}"
                )

                # Check tool execution limits
                max_tools_per_turn = 100
                max_repeated_calls = 5

                # Check total tools limit
                if total_tools_called >= max_tools_per_turn:
                    error_msg = TOOL_ERROR_MESSAGES[ToolErrorType.RESOURCE_LIMIT].format(
                        limit_type="total tools per turn",
                        current=total_tools_called,
                        max_allowed=max_tools_per_turn,
                        tool_name=tool_name,
                    )
                    tool_results.append(
                        ToolResult(
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            content=error_msg,
                            is_error=True,
                            error_type=ToolErrorType.RESOURCE_LIMIT,
                        )
                    )
                    continue

                # Check repeated calls limit
                tool_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                call_count = tool_call_counts.get(tool_key, 0)
                if call_count >= max_repeated_calls:
                    error_msg = TOOL_ERROR_MESSAGES[ToolErrorType.LOOP_DETECTED].format(
                        tool_name=tool_name, tool_args=json.dumps(tool_args), count=call_count
                    )
                    tool_results.append(
                        ToolResult(
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            content=error_msg,
                            is_error=True,
                            error_type=ToolErrorType.LOOP_DETECTED,
                        )
                    )
                    continue

                # Update tracking
                total_tools_called += 1
                tool_call_counts[tool_key] = call_count + 1
                self._recent_tool_calls.append({"name": tool_name, "args": tool_args})

                try:
                    tool_start_time = time.time()
                    result = await self.call_tool(tool_name, tool_args)
                    tool_duration_ms = int((time.time() - tool_start_time) * 1000)
                    tools_total_duration_ms += tool_duration_ms
                    # Safely parse the CallToolResult to dictionary for formatting
                    try:
                        result_dict = self.parse_call_tool_result(result)
                    except Exception as parse_error:
                        logger.error(
                            f"🔍 DEBUG: Failed to parse tool result for "
                            f"'{tool_name}': {parse_error}"
                        )
                        result_dict = {
                            "success": False,
                            "content": "",
                            "error": f"Failed to parse tool result: {str(parse_error)}",
                        }
                    logger.info(
                        f"🔍 DEBUG: Tool '{tool_name}' returned success: "
                        f"{result_dict.get('success', 'unknown')} in {tool_duration_ms:.1f}ms"
                    )

                    if result_dict.get("success"):
                        tool_results.append(
                            ToolResult(
                                tool_call_id=tool_call_id,
                                tool_name=tool_name,
                                content=result_dict.get("content", ""),
                                is_error=False,
                            )
                        )
                    else:
                        tool_results.append(
                            ToolResult(
                                tool_call_id=tool_call_id,
                                tool_name=tool_name,
                                content=result_dict.get("error", "Unknown error"),
                                is_error=True,
                                error_type=ToolErrorType.EXECUTION_ERROR,
                            )
                        )
                except Exception as e:
                    logger.error(f"🔍 DEBUG: Tool '{tool_name}' failed: {str(e)}")
                    error_msg = TOOL_ERROR_MESSAGES[ToolErrorType.EXECUTION_ERROR].format(
                        error_detail=str(e)
                    )
                    tool_results.append(
                        ToolResult(
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            content=error_msg,
                            is_error=True,
                            error_type=ToolErrorType.EXECUTION_ERROR,
                        )
                    )

            # Add assistant message with tool calls
            assistant_msg = Message(
                role=Role.ASSISTANT,
                content=current_response.content or "",
                tool_calls=current_response.tool_calls,
            )
            current_messages.append(assistant_msg)

            # Add tool results as a proper tool result message
            if tool_results:
                tool_result_msg = Message(
                    role=Role.USER,
                    content="",  # Empty content for tool result messages
                    tool_results=tool_results,
                )
                current_messages.append(tool_result_msg)

                logger.info(f"🔍 DEBUG: Sending {len(tool_results)} tool results back to LLM")
                for tr in tool_results:
                    logger.info(
                        f"🔍 DEBUG: Tool result - {tr.tool_name}: "
                        f"{'error' if tr.is_error else 'success'}"
                    )

            # Update total tools duration
            self.last_tools_duration_ms = tools_total_duration_ms

            logger.info(
                f"🔍 DEBUG: Sending {len(current_messages)} messages back to LLM for follow-up"
            )

            # Get follow-up response with tools still available (safe agentic loop)
            follow_up = await self.llm_provider.generate(
                messages=current_messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=llm_tools,  # Keep tools available - smart loop protection prevents runaway
                **kwargs,
            )

            # Track token usage for budget management
            if hasattr(follow_up, "usage") and follow_up.usage:
                tokens_used += getattr(follow_up.usage, "total_tokens", 0)

            logger.info(
                f"🔍 DEBUG: Follow-up response has tool_calls: "
                f"{hasattr(follow_up, 'tool_calls') and bool(follow_up.tool_calls)}"
            )

            current_response = follow_up  # type: ignore[assignment]

            # Continue loop - _should_continue_tool_loop handles termination logic

        # Log loop completion reason
        if iteration >= max_iterations:
            logger.info(
                f"🔍 DEBUG: Tool loop completed - max iterations reached ({max_iterations})"
            )
        elif tokens_used >= max_token_budget:
            logger.info(
                f"🔍 DEBUG: Tool loop completed - token budget exceeded "
                f"({tokens_used}/{max_token_budget})"
            )
        else:
            logger.info("🔍 DEBUG: Tool loop completed - no more tool calls needed")

        return current_response

    async def _handle_streaming_with_tools(
        self,
        messages: list[Message],
        model: Optional[str],
        temperature: float,
        max_tokens: Optional[int],
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent]:
        """Handle streaming response with tool calling support."""
        logger.info("🔍 DEBUG: Streaming with tools - implementing streaming tool calls")

        # Initialize performance tracking
        self.last_tools_duration_ms = 0
        tools_total_duration_ms = 0

        # Get all tools from unified registry (filtered)
        all_tools = self.tool_registry.get_all_tools()
        llm_tools = [tool for tool in all_tools if tool["name"] not in self.disabled_tools]

        # Helper function to check tool execution limits
        def check_tool_limits(
            tool_name: str,
            tool_args: dict[str, Any],
            total_tools: int,
            tool_counts: dict[str, int],
            max_tools: int,
            max_repeated: int,
        ) -> tuple[bool, Optional[str], Optional[ToolErrorType]]:
            """Check if tool execution should proceed based on limits.
            Returns: (should_execute, error_message, error_type)
            """
            # Check total tools limit
            if total_tools >= max_tools:
                error_msg = TOOL_ERROR_MESSAGES[ToolErrorType.RESOURCE_LIMIT].format(
                    limit_type="total tools per turn",
                    current=total_tools,
                    max_allowed=max_tools,
                    tool_name=tool_name,
                )
                return False, error_msg, ToolErrorType.RESOURCE_LIMIT

            # Check repeated calls limit
            tool_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
            call_count = tool_counts.get(tool_key, 0)
            if call_count >= max_repeated:
                error_msg = TOOL_ERROR_MESSAGES[ToolErrorType.LOOP_DETECTED].format(
                    tool_name=tool_name, tool_args=json.dumps(tool_args), count=call_count
                )
                return False, error_msg, ToolErrorType.LOOP_DETECTED

            return True, None, None

        # Create a generator that yields streaming events
        async def stream_generator() -> AsyncIterator[StreamEvent]:
            nonlocal tools_total_duration_ms

            # Initialize tracking inside generator
            total_tools_called = 0
            tool_call_counts: dict[str, int] = {}
            max_tools_per_turn = 100
            max_repeated_calls = 5

            with self.tracer.start_as_current_span("mcp_client.stream_generator") as gen_span:
                gen_span.set_attribute("tool.count", len(llm_tools))
                gen_span.set_attribute("llm.model", model or "default")

                # First, get the initial response to check for tool calls
                logger.info("🔍 DEBUG: About to call LLM provider for initial response")
                with self.tracer.start_as_current_span("llm.initial_call") as llm_span:
                    llm_span.set_attribute("llm.messages", len(messages))
                    llm_span.set_attribute("llm.temperature", temperature)
                    llm_span.set_attribute("llm.max_tokens", max_tokens or 0)

                    try:
                        response = await self.llm_provider.generate(
                            messages=messages,
                            model=model,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            stream=False,  # We'll implement proper streaming later
                            tools=llm_tools,
                            **kwargs,
                        )
                        logger.info("🔍 DEBUG: Got initial LLM response")
                        # Response must be GenerationResponse since stream=False
                        assert isinstance(response, GenerationResponse)
                        logger.info(f"🔍 DEBUG: Response content: {response.content[:200]}...")
                        logger.info(
                            f"🔍 DEBUG: Response has tool_calls: {hasattr(response, 'tool_calls')}"
                        )
                        if hasattr(response, "tool_calls"):
                            logger.info(
                                f"🔍 DEBUG: Tool calls count: "
                                f"{len(response.tool_calls) if response.tool_calls else 0}"
                            )
                        llm_span.set_attribute(
                            "has_tool_calls",
                            bool(hasattr(response, "tool_calls") and response.tool_calls),
                        )
                    except Exception as e:
                        logger.error(f"🔍 DEBUG: LLM call failed: {e}")
                        llm_span.record_exception(e)
                        raise

                # If there are tool calls, yield them as events and execute
                if hasattr(response, "tool_calls") and response.tool_calls:
                    logger.info(
                        f"🔍 DEBUG: Streaming - LLM decided to use tools: "
                        f"{[tc.get('name') for tc in response.tool_calls]}"
                    )

                    with self.tracer.start_as_current_span(
                        "tool_execution_phase"
                    ) as tool_phase_span:
                        tool_phase_span.set_attribute("tool_call.count", len(response.tool_calls))

                        # Add assistant message with tool calls first
                        assistant_msg = Message(
                            role=Role.ASSISTANT,
                            content=response.content or "",
                            tool_calls=response.tool_calls,
                        )
                        current_messages = messages.copy()
                        current_messages.append(assistant_msg)

                        # Execute tool calls and collect results
                        tool_results = []

                        for i, tool_call in enumerate(response.tool_calls):
                            tool_name = tool_call.get("name")
                            tool_args = tool_call.get("arguments", {})
                            tool_call_id = tool_call.get("id", f"call_{i}")

                            if not tool_name:
                                logger.warning(f"Tool call {i + 1} has no name, skipping")
                                continue

                            with self.tracer.start_as_current_span(
                                f"tool.{tool_name}"
                            ) as tool_span:
                                tool_span.set_attribute("tool.name", tool_name)
                                tool_span.set_attribute("tool.index", i)
                                tool_span.set_attribute("tool.args", str(tool_args))

                                # Check tool execution limits
                                should_execute, error_msg, error_type = check_tool_limits(
                                    tool_name,
                                    tool_args,
                                    total_tools_called,
                                    tool_call_counts,
                                    max_tools_per_turn,
                                    max_repeated_calls,
                                )

                                # Yield tool call event
                                yield StreamEvent.tool_call(tool_name, tool_args)

                                if not should_execute:
                                    # Yield error result and continue to next tool
                                    yield StreamEvent.tool_result(
                                        tool_name, False, error=error_msg, error_type=error_type
                                    )
                                    tool_results.append(
                                        ToolResult(
                                            tool_call_id=tool_call_id,
                                            tool_name=tool_name,
                                            content=error_msg or "Tool execution not allowed",
                                            is_error=True,
                                            error_type=error_type,
                                        )
                                    )
                                    continue

                                # Update tracking
                                total_tools_called += 1
                                tool_key = f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                                tool_call_counts[tool_key] = tool_call_counts.get(tool_key, 0) + 1

                                try:
                                    # Execute tool with timing
                                    tool_span.add_event("tool_execution_start")
                                    tool_start_time = time.time()
                                    result = await self.call_tool(tool_name, tool_args)
                                    tool_duration_ms = int((time.time() - tool_start_time) * 1000)
                                    tools_total_duration_ms += tool_duration_ms

                                    # Safely parse result with error handling
                                    try:
                                        result_dict = self.parse_call_tool_result(result)
                                    except Exception as parse_error:
                                        logger.error(
                                            f"❌ Failed to parse tool result for {tool_name}: "
                                            f"{parse_error}"
                                        )
                                        result_dict = {
                                            "success": False,
                                            "content": "",
                                            "error": (
                                                f"Failed to parse tool result: {str(parse_error)}"
                                            ),
                                        }

                                    tool_span.add_event("tool_execution_complete")
                                    tool_span.set_attribute(
                                        "tool.success", result_dict.get("success", False)
                                    )
                                    tool_span.set_attribute(
                                        "tool.result_size", len(str(result_dict))
                                    )

                                    # Yield tool result event with duration
                                    success = result_dict.get("success", False)
                                    if success:
                                        yield StreamEvent.tool_result(
                                            tool_name,
                                            True,
                                            result_dict,
                                            duration_ms=tool_duration_ms,
                                        )
                                        tool_results.append(
                                            ToolResult(
                                                tool_call_id=tool_call_id,
                                                tool_name=tool_name,
                                                content=result_dict.get("content", ""),
                                                is_error=False,
                                            )
                                        )
                                    else:
                                        yield StreamEvent.tool_result(
                                            tool_name,
                                            False,
                                            error=result_dict.get("error", "Unknown error"),
                                            duration_ms=tool_duration_ms,
                                        )
                                        tool_results.append(
                                            ToolResult(
                                                tool_call_id=tool_call_id,
                                                tool_name=tool_name,
                                                content=result_dict.get("error", "Unknown error"),
                                                is_error=True,
                                                error_type=ToolErrorType.EXECUTION_ERROR,
                                            )
                                        )

                                except Exception as e:
                                    logger.error(f"❌ Tool {tool_name} failed: {e}")
                                    tool_span.record_exception(e)
                                    tool_span.set_attribute("tool.success", False)

                                    error_msg = TOOL_ERROR_MESSAGES[
                                        ToolErrorType.EXECUTION_ERROR
                                    ].format(error_detail=str(e))
                                    yield StreamEvent.tool_result(
                                        tool_name,
                                        False,
                                        error=error_msg,
                                        error_type=ToolErrorType.EXECUTION_ERROR,
                                    )
                                    tool_results.append(
                                        ToolResult(
                                            tool_call_id=tool_call_id,
                                            tool_name=tool_name,
                                            content=error_msg,
                                            is_error=True,
                                            error_type=ToolErrorType.EXECUTION_ERROR,
                                        )
                                    )

                        # Add tool results as proper tool result message
                        if tool_results:
                            tool_result_msg = Message(
                                role=Role.USER,
                                content="",  # Empty content for tool result messages
                                tool_results=tool_results,
                            )
                            current_messages.append(tool_result_msg)

                        # Implement agentic loop in streaming mode
                        # Configuration for agentic loop limits
                        # TODO: Make these configurable via AgentConfig class

                        # Maximum number of LLM round-trips (iterations)
                        # Each iteration is: LLM response → tool execution → back to LLM
                        max_iterations = 50

                        # Maximum total tool calls allowed in this conversation turn
                        # Prevents runaway tool usage in complex workflows
                        max_tools_per_turn = 100

                        # Maximum times the same tool can be called with identical arguments
                        # Prevents infinite loops from confused LLM behavior
                        max_repeated_calls = 5

                        # Maximum token budget for the entire turn (1M tokens)
                        # Includes all LLM calls and tool results
                        max_token_budget = 1_000_000
                        iteration = 0
                        tokens_used = 0
                        current_response = response

                        # Reset tool call tracking (for backward compatibility)
                        self._recent_tool_calls = []

                        while self._should_continue_tool_loop(
                            iteration,
                            max_iterations,
                            tokens_used,
                            max_token_budget,
                            current_response,
                        ):
                            iteration += 1
                            logger.info(
                                f"🔍 DEBUG: Streaming agentic loop iteration "
                                f"{iteration}/{max_iterations}"
                            )

                            # Get follow-up response
                            follow_up = await self.llm_provider.generate(
                                messages=current_messages,
                                model=model,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                stream=False,
                                tools=llm_tools,
                                **kwargs,
                            )

                            # Since stream=False, follow_up must be GenerationResponse
                            assert isinstance(follow_up, GenerationResponse)

                            # Track token usage
                            if hasattr(follow_up, "usage") and follow_up.usage:
                                tokens_used += getattr(follow_up.usage, "total_tokens", 0)

                            current_response = follow_up

                            # If response has tool calls, execute them
                            if hasattr(follow_up, "tool_calls") and follow_up.tool_calls:
                                logger.info(
                                    f"🔍 DEBUG: Streaming - Follow-up wants tools: "
                                    f"{[tc.get('name') for tc in follow_up.tool_calls]}"
                                )

                                # Add assistant message if it has content
                                if follow_up.content:
                                    current_messages.append(
                                        Message(role=Role.ASSISTANT, content=follow_up.content)
                                    )
                                    # Also yield the content
                                    yield StreamEvent.from_content(
                                        StreamChunk(content=follow_up.content)
                                    )

                                # Add assistant message with tool calls
                                assistant_msg = Message(
                                    role=Role.ASSISTANT,
                                    content=follow_up.content or "",
                                    tool_calls=follow_up.tool_calls,
                                )
                                current_messages.append(assistant_msg)

                                # Execute new tool calls
                                tool_results = []
                                for i, tool_call in enumerate(follow_up.tool_calls):
                                    tool_name = tool_call.get("name")
                                    tool_args = tool_call.get("arguments", {})
                                    tool_call_id = tool_call.get("id", f"call_{i}")

                                    if not tool_name:
                                        logger.warning(f"Tool call {i + 1} has no name, skipping")
                                        continue

                                    # Check tool execution limits
                                    should_execute, error_msg, error_type = check_tool_limits(
                                        tool_name,
                                        tool_args,
                                        total_tools_called,
                                        tool_call_counts,
                                        max_tools_per_turn,
                                        max_repeated_calls,
                                    )

                                    # Yield tool call event
                                    yield StreamEvent.tool_call(tool_name, tool_args)

                                    if not should_execute:
                                        # Yield error result and continue to next tool
                                        yield StreamEvent.tool_result(
                                            tool_name, False, error=error_msg, error_type=error_type
                                        )
                                        tool_results.append(
                                            ToolResult(
                                                tool_call_id=tool_call_id,
                                                tool_name=tool_name,
                                                content=error_msg or "Tool execution not allowed",
                                                is_error=True,
                                                error_type=error_type,
                                            )
                                        )
                                        continue

                                    # Update tracking
                                    total_tools_called += 1
                                    tool_key = (
                                        f"{tool_name}:{json.dumps(tool_args, sort_keys=True)}"
                                    )
                                    tool_call_counts[tool_key] = (
                                        tool_call_counts.get(tool_key, 0) + 1
                                    )

                                    try:
                                        tool_start_time = time.time()
                                        result = await self.call_tool(tool_name, tool_args)
                                        tool_duration_ms = int(
                                            (time.time() - tool_start_time) * 1000
                                        )
                                        tools_total_duration_ms += tool_duration_ms
                                        try:
                                            result_dict = self.parse_call_tool_result(result)
                                        except Exception as parse_error:
                                            result_dict = {
                                                "success": False,
                                                "content": "",
                                                "error": (
                                                    f"Failed to parse tool result: "
                                                    f"{str(parse_error)}"
                                                ),
                                            }

                                        success = result_dict.get("success", False)
                                        if success:
                                            yield StreamEvent.tool_result(
                                                tool_name,
                                                True,
                                                result_dict,
                                                duration_ms=tool_duration_ms,
                                            )
                                            tool_results.append(
                                                ToolResult(
                                                    tool_call_id=tool_call_id,
                                                    tool_name=tool_name,
                                                    content=result_dict.get("content", ""),
                                                    is_error=False,
                                                )
                                            )
                                        else:
                                            yield StreamEvent.tool_result(
                                                tool_name,
                                                False,
                                                error=result_dict.get("error", "Unknown error"),
                                                duration_ms=tool_duration_ms,
                                            )
                                            tool_results.append(
                                                ToolResult(
                                                    tool_call_id=tool_call_id,
                                                    tool_name=tool_name,
                                                    content=result_dict.get(
                                                        "error", "Unknown error"
                                                    ),
                                                    is_error=True,
                                                    error_type=ToolErrorType.EXECUTION_ERROR,
                                                )
                                            )

                                    except Exception as e:
                                        logger.error(f"❌ Streaming tool {tool_name} failed: {e}")
                                        error_msg = TOOL_ERROR_MESSAGES[
                                            ToolErrorType.EXECUTION_ERROR
                                        ].format(error_detail=str(e))
                                        yield StreamEvent.tool_result(
                                            tool_name,
                                            False,
                                            error=error_msg,
                                            error_type=ToolErrorType.EXECUTION_ERROR,
                                        )
                                        tool_results.append(
                                            ToolResult(
                                                tool_call_id=tool_call_id,
                                                tool_name=tool_name,
                                                content=error_msg,
                                                is_error=True,
                                                error_type=ToolErrorType.EXECUTION_ERROR,
                                            )
                                        )

                                # Add tool results as proper tool result message for next iteration
                                if tool_results:
                                    tool_result_msg = Message(
                                        role=Role.USER,
                                        content="",  # Empty content for tool result messages
                                        tool_results=tool_results,
                                    )
                                    current_messages.append(tool_result_msg)

                            else:
                                # No more tool calls - yield final content and break
                                logger.info("🔍 DEBUG: Streaming - Final response, no more tools")
                                if follow_up.content:
                                    yield StreamEvent.from_content(
                                        StreamChunk(content=follow_up.content)
                                    )
                                break

                        # If we exit due to limits, yield any remaining content
                        if iteration >= max_iterations:
                            logger.info(
                                "🔍 DEBUG: Streaming loop completed - max iterations reached"
                            )
                        elif tokens_used >= max_token_budget:
                            logger.info(
                                "🔍 DEBUG: Streaming loop completed - token budget exceeded"
                            )

                        # Update total tools duration
                        self.last_tools_duration_ms = tools_total_duration_ms

                        # Make sure we always yield some final content
                        if hasattr(current_response, "content") and current_response.content:
                            yield StreamEvent.from_content(
                                StreamChunk(content=current_response.content)
                            )

                else:
                    logger.info("🔍 DEBUG: Streaming - LLM response without tool calls")
                    # No tool calls, just yield the response content
                    yield StreamEvent.from_content(StreamChunk(content=response.content))
                    # Update total tools duration (0 in this case)
                    self.last_tools_duration_ms = tools_total_duration_ms

        # Return the generator
        return stream_generator()

    async def call_tool(self, tool_name: str, parameters: dict[str, Any]) -> Any:
        """Call a tool using the unified tool executor."""
        with self.tracer.start_as_current_span(f"tool.{tool_name}") as span:
            span.set_attribute("tool.name", tool_name)
            span.set_attribute("tool.parameters", str(parameters)[:500])  # Limit to 500 chars

            logger.info(f"🔧 Calling tool: {tool_name} with params: {parameters}")

            try:
                span.add_event("tool_execution_start")

                # Use unified tool executor (handles both core and MCP tools)
                result = await self.tool_executor.execute(tool_name, parameters)

                span.add_event("tool_execution_complete")
                span.set_attribute("tool.success", result.success)
                span.set_attribute("tool.result_length", len(str(result.llm_content)))

                if result.error:
                    span.set_attribute("tool.error", result.error)

                logger.info(f"🔧 Tool {tool_name} returned: {str(result.llm_content)[:100]}...")
                return result

            except Exception as e:
                span.record_exception(e)
                span.set_attribute("tool.success", False)
                span.set_attribute("tool.error", str(e))
                logger.error(f"🔧 Tool {tool_name} failed: {e}")
                raise

    def parse_call_tool_result(self, result: Any) -> dict[str, Any]:
        """Parse ToolResult to dictionary for convenience."""
        return {
            "success": result.success,
            "content": result.llm_content or "",
            "error": result.error,
        }

    async def generate_structured(
        self,
        messages: list[Message],
        response_model: type,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> Any:
        """Generate structured output - NOT IMPLEMENTED for MCP client.

        MCP client is for tool calling, not structured generation.
        Use structured_client for instructor-based structured outputs.
        """
        raise NotImplementedError(
            "generate_structured not supported by MCP client. Use structured_client instead."
        )

    async def close(self) -> None:
        """Close the MCP client and underlying LLM."""
        if self.llm_provider:
            try:
                await self.llm_provider.close()
            except Exception as e:
                logger.warning(f"Error closing LLM provider: {e}")

        # Note: MCPServers should be stopped separately
        # This allows for better control over server lifecycle

        self._initialized = False

    async def get_available_tools(self) -> list[dict[str, Any]]:
        """Get list of available tools from all servers (excluding disabled tools)."""
        # Use unified tool registry instead of direct server access
        if not self._initialized:
            await self.initialize()

        # Get all tools and filter out per-instance disabled tools
        all_tools = self.tool_registry.get_all_tools()
        return [tool for tool in all_tools if tool["name"] not in self.disabled_tools]

    def get_tool_schema(self, tool_name: str) -> dict[str, Any]:
        """Get schema for a specific tool."""
        for server in self.mcp_servers:
            if server.is_running:
                for tool in server.get_tools():
                    if tool["name"] == tool_name:
                        # Return full tool info including name for compatibility
                        return {
                            "name": tool["name"],
                            "description": tool["description"],
                            "input_schema": tool["input_schema"],
                        }
        raise ValueError(f"Tool {tool_name} not found")

    @property
    def name(self) -> str:
        """Client name."""
        server_count = len([s for s in self.mcp_servers if s.is_running])
        return f"MCP-{getattr(self.llm_provider, 'name', 'LLM')}-{server_count}servers"
