"""AgentManager - Manages multiple active agents and intercepts tool calls for dynamic agent
creation."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Optional

from agents.base import BaseAgent
from agents.memory import MemoryManager
from agents.meta_agent import MetaAgent
from agents.task_execution_agent import TaskExecutionAgent
from agents.tool_result_formatter import tool_result_formatter
from client.mcp_server import MCPServer
from client.models import ModelID
from common.messages import (
    AgentMessage,
    ApprovalRequestMessage,
    ApprovalResponseMessage,
    ChatMessage,
    ErrorMessage,
    Message,
    ThinkingMessage,
    ToolCallMessage,
    ToolResultMessage,
    UserMessage,
)
from common.types import ParameterValue, TaskExecutionContext, ToolCallResult, ToolErrorType
from tools.base import Tool
from tools.registry import (
    ToolRegistry,
    configure_tool_dependencies,
    get_tool_executor,
    get_tool_registry,
)

logger = logging.getLogger(__name__)


class ResponseType(Enum):
    """Types of responses for UI rendering."""

    TEXT = "text"
    ERROR = "error"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    SYSTEM = "system"
    TOOL_APPROVAL_REQUEST = "tool_approval_request"
    TOOL_APPROVED = "tool_approved"
    TOOL_REJECTED = "tool_rejected"
    TOOL_EXECUTION_STARTED = "tool_execution_started"
    TOOL_EXECUTION_COMPLETED = "tool_execution_completed"


@dataclass
class UIResponse:
    """Structured response for UI/CLI rendering."""

    type: ResponseType
    content: str
    agent_id: str
    metadata: Optional[dict[str, Any]] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now()


class AgentManager:
    """
    Manages multiple active agents and intercepts special tool calls.

    Key responsibilities:
    - Routes messages between CLI/UI and active agents
    - Intercepts execute_task tool calls to create TaskExecutionAgents dynamically
    - Manages agent lifecycle (creation, switching, cleanup)
    - Provides unified streaming interface
    - Maintains backward compatibility with existing UI/CLI interface

    TODO: Implement automatic agent switching based on tool calls:
    1. Intercept execute_task tool calls from MetaAgent
    2. Create TaskExecutionAgent with the task and input values
    3. Switch current_agent_id to the new TaskExecutionAgent
    4. Stream responses from TaskExecutionAgent until task completes
    5. Switch back to MetaAgent after task completion

    This requires deeper integration with the tool execution pipeline
    to intercept and modify tool behavior before execution.
    """

    def __init__(
        self,
        agent_name: str = "MetaAgent",
        db_engine: Any = None,
        mcp_servers: Optional[list[str]] = None,
        llm: ModelID = ModelID.CLAUDE_SONNET_4,
    ) -> None:
        """
        Initialize AgentManager.

        Args:
            agent_name: Name for the agent
            db_engine: DatabaseEngine instance
            mcp_servers: List of MCP server paths
            llm: LLM specification for MCP client
        """
        self.agent_name = agent_name
        self.db_engine = db_engine
        self.mcp_servers = mcp_servers or ["tools/mcp_server.py"]
        self.llm = llm

        # Tool registry - initialized once and shared
        self.tool_registry: Optional[ToolRegistry] = None
        self.enabled_tools: list[Tool] = []

        # Global disabled tools (will come from config eventually)
        self.global_disabled_tools = {
            "memory_search",
            "compact_conversation",
            "get_recent_conversations",  # Memory tools disabled during migration
        }

        # Infrastructure components
        self.memory_manager: Optional[MemoryManager] = None
        self.mcp_servers_instances: list[MCPServer] = []

        # Agent instances
        self.meta_agent: Optional[MetaAgent] = None
        self.task_agent: Optional[TaskExecutionAgent] = None

        # CLI communication queues
        self.cli_input_queue: asyncio.Queue = asyncio.Queue()
        self.cli_output_queue: asyncio.Queue = asyncio.Queue()

        # SINGLE shared output channel for all agents
        self.unified_agent_output: asyncio.Queue = asyncio.Queue()

        # Individual input channels per agent
        self.meta_agent_input: asyncio.Queue = asyncio.Queue()
        self.task_agent_input: asyncio.Queue = asyncio.Queue()

        # Current active agent ID
        self.current_agent_id: str = "METAGEN"

        # Persistent agent tasks
        self.run_meta_agent: Optional[asyncio.Task] = None
        self.run_task_agent: Optional[asyncio.Task] = None

        self.router_task: Optional[asyncio.Task] = None

        # FIFO coordination for task completion
        self.pending_task_completions: list[asyncio.Event] = []
        self.pending_task_results: list[str] = []

        # Tool approval configuration
        self._require_tool_approval: bool = False
        self._auto_approve_tools: set[str] = set()

        # Initialization state
        self._initialized = False

    def _get_current_agent(self) -> Any:
        """Get the current active agent based on current_agent_id."""
        if self.current_agent_id == "METAGEN":
            return self.meta_agent
        else:
            return self.task_agent

    def configure_tool_approval(
        self, require_approval: bool = False, auto_approve_tools: Optional[set[str]] = None
    ) -> None:
        """Configure tool approval settings for all agents.

        Args:
            require_approval: Whether to require approval for tool execution
            auto_approve_tools: Set of tool names that don't need approval
        """
        self._require_tool_approval = require_approval
        self._auto_approve_tools = auto_approve_tools or set()

        logger.debug(
            f"🔧 Tool approval configured: require={require_approval}, "
            f"auto_approve={list(self._auto_approve_tools)}"
        )

        # Configure existing agents if already initialized
        if self.meta_agent:
            self.meta_agent.configure_tool_approval(
                require_approval=require_approval,
                auto_approve_tools=list(auto_approve_tools) if auto_approve_tools else None,
                approval_queue=self.meta_agent_input if require_approval else None,
            )

        if self.task_agent:
            self.task_agent.configure_tool_approval(
                require_approval=require_approval,
                auto_approve_tools=list(auto_approve_tools) if auto_approve_tools else None,
                approval_queue=self.task_agent_input if require_approval else None,
            )

    async def _run_meta_agent(self) -> None:
        """MetaAgent runs forever, processing messages from its input queue."""
        logger.debug("🤖 Starting MetaAgent")
        error_count = 0
        max_consecutive_errors = 5

        while True:
            try:
                # Wait for message from AgentManager
                logger.info("🔄 MetaAgent waiting for message from queue...")
                message = await self.meta_agent_input.get()
                # Get message content for logging
                msg_preview = (
                    message.content[:50] if isinstance(message, ChatMessage) else str(message)[:50]
                )
                logger.info(
                    f"📥 MetaAgent received message from queue: "
                    f"{type(message).__name__} - {msg_preview}..."
                )

                # Process message and stream output back to unified queue
                if self.meta_agent is None:
                    logger.error("MetaAgent not initialized")
                    continue

                logger.info(f"🎬 MetaAgent starting to process {type(message).__name__}")
                event_count = 0
                async for msg in self.meta_agent.stream_chat(message):
                    event_count += 1
                    self._log_message(msg, "🎯")
                    await self.unified_agent_output.put(msg)

                logger.info(
                    f"✅ MetaAgent completed processing {type(message).__name__} "
                    f"with {event_count} events"
                )
                # Reset error count on successful processing
                error_count = 0

            except asyncio.CancelledError:
                logger.info("MetaAgent task cancelled")
                break
            except Exception as e:
                error_count += 1
                logger.error(f"MetaAgent encountered an error: {e}", exc_info=True)

                # Send error to output
                await self.unified_agent_output.put(
                    ErrorMessage(
                        error=f"An error occurred: {str(e)}",
                        details={"error": str(e), "error_count": error_count},
                    )
                )

                # If too many errors, wait a bit before retrying
                if error_count >= max_consecutive_errors:
                    wait_time = min(60, 2 ** (error_count - max_consecutive_errors))
                    logger.info(
                        f"MetaAgent is experiencing repeated errors. "
                        f"Waiting {wait_time} seconds before retrying..."
                    )
                    await asyncio.sleep(wait_time)

    async def _run_task_agent(self) -> None:
        """TaskExecutionAgent runs forever, idle until given task."""
        if self.task_agent is None:
            logger.error("TaskExecutionAgent not initialized")
            return

        logger.info(f"Starting TaskExecutionAgent: {self.task_agent.agent_id}")
        error_count = 0
        max_consecutive_errors = 5

        while True:
            try:
                # Wait for task message from AgentManager (via tool interceptor)
                task_message = await self.task_agent_input.get()

                # Log the task content
                if isinstance(task_message, Message):
                    task_preview = getattr(task_message, "content", str(task_message))[:50]
                else:
                    task_preview = str(task_message)[:50]
                logger.info(f"TaskExecutionAgent received task: {task_preview}...")

                # Execute task and stream output back to unified queue
                if self.task_agent is None:
                    logger.error("TaskExecutionAgent not initialized")
                    continue

                async for msg in self.task_agent.stream_chat(task_message):
                    self._log_message(msg, "🤖")
                    await self.unified_agent_output.put(msg)

                logger.info("TaskExecutionAgent completed task execution")

                # Clear current task after completion
                if self.task_agent is not None:
                    self.task_agent.clear_current_task()

                # Reset error count on successful execution
                error_count = 0

            except asyncio.CancelledError:
                logger.info("TaskExecutionAgent task cancelled")
                break
            except Exception as e:
                error_count += 1
                logger.error(f"TaskExecutionAgent encountered an error: {e}", exc_info=True)

                await self.unified_agent_output.put(
                    ErrorMessage(
                        agent_id=self.task_agent.agent_id if self.task_agent else "TASK_UNKNOWN",
                        error=f"Task execution error: {str(e)}",
                        details={"error": str(e), "error_count": error_count},
                    )
                )

                # If too many errors, wait before retrying
                if error_count >= max_consecutive_errors:
                    wait_time = min(60, 2 ** (error_count - max_consecutive_errors))
                    logger.info(
                        f"TaskExecutionAgent is experiencing repeated errors. "
                        f"Waiting {wait_time} seconds before retrying..."
                    )
                    await asyncio.sleep(wait_time)

    async def _route_agent_outputs(self) -> None:
        """ONLY consumer of unified output queue with FIFO coordination."""
        logger.debug("🚀 Starting message router")
        error_count = 0
        max_consecutive_errors = 10  # Higher threshold for router
        message_count = 0

        while True:
            try:
                # Wait for output from any agent
                msg = await self.unified_agent_output.get()
                message_count += 1
                self._log_message(msg, "📨")

                # Forward message directly to CLI
                await self.cli_output_queue.put(msg)

                # Check for task completion via ToolResultMessage
                if (
                    self.task_agent is not None
                    and isinstance(msg, ToolResultMessage)
                    and msg.agent_id == self.task_agent.agent_id
                    and msg.tool_name == "execute_task"
                ):
                    logger.debug(
                        f"🎯 TaskExecutionAgent completed with ToolResultMessage - FIFO queue has "
                        f"{len(self.pending_task_completions)} pending completions"
                    )

                    # Signal the next pending task completion (FIFO order)
                    if self.pending_task_completions:
                        # Store the complete ToolCallResult, not just content string
                        self.pending_task_results.append(msg.result)
                        completion_event = self.pending_task_completions.pop(0)
                        completion_event.set()
                        logger.debug(
                            f"✅ Signaled completion event with complete result, "
                            f"{len(self.pending_task_completions)} remaining"
                        )

                # Reset error count on successful routing
                error_count = 0

            except asyncio.CancelledError:
                logger.info("Router task cancelled")
                break
            except Exception as e:
                error_count += 1
                logger.error(
                    f"Router encountered an error ({error_count}/{max_consecutive_errors}): {e}",
                    exc_info=True,
                )

                # Try to send error to output queue
                try:
                    error_response = UIResponse(
                        type=ResponseType.ERROR,
                        content=f"Router error: {str(e)}",
                        agent_id="ROUTER",
                        metadata={"error": str(e), "error_count": error_count},
                        timestamp=datetime.now(),
                    )
                    await self.cli_output_queue.put(error_response)
                except Exception as inner_e:
                    logger.error(f"Failed to send router error to output: {inner_e}")

                # If too many errors, wait before continuing
                if error_count >= max_consecutive_errors:
                    wait_time = min(30, 2 ** (error_count - max_consecutive_errors))
                    logger.info(
                        f"Router is experiencing repeated errors. "
                        f"Waiting {wait_time} seconds before retrying..."
                    )
                    await asyncio.sleep(wait_time)

    def _log_message(self, msg: Any, prefix: str = "📨") -> None:
        """Helper to log messages in a clean way."""
        msg_type = type(msg).__name__
        content = msg.content[:50] if isinstance(msg, ChatMessage) else ""

        # Only log important message types
        if isinstance(
            msg,
            (
                ApprovalRequestMessage,
                ToolCallMessage,
                ToolResultMessage,
                ErrorMessage,
                AgentMessage,
            ),
        ):
            logger.debug(f"{prefix} [{msg_type}] {content}")
        elif isinstance(msg, ThinkingMessage):
            # Skip thinking messages in logs
            pass

    def _map_stage_to_response_type(self, stage: str) -> ResponseType:
        """Map agent stage to UIResponse type."""
        stage_mapping = {
            "thinking": ResponseType.THINKING,
            "llm_call": ResponseType.THINKING,
            "tool_call": ResponseType.TOOL_CALL,
            "tool_result": ResponseType.TOOL_RESULT,
            "tool_error": ResponseType.ERROR,
            "processing": ResponseType.THINKING,
            "response": ResponseType.TEXT,
            "error": ResponseType.ERROR,
            "tool_approval_request": ResponseType.TOOL_APPROVAL_REQUEST,
            "tool_approved": ResponseType.TOOL_APPROVED,
            "tool_rejected": ResponseType.TOOL_REJECTED,
            "tool_execution_started": ResponseType.TOOL_EXECUTION_STARTED,
            "tool_execution_completed": ResponseType.TOOL_EXECUTION_COMPLETED,
        }
        return stage_mapping.get(stage, ResponseType.SYSTEM)

    async def initialize(self) -> UIResponse:
        """Initialize all components and return status."""
        logger.info("Initializing AgentManager with FIFO architecture")

        try:
            # Create memory manager
            logger.info("🔍 Creating MemoryManager with DatabaseEngine")
            self.memory_manager = MemoryManager(self.db_engine)
            await self.memory_manager.initialize()
            logger.info("Memory manager initialized")

            # Create MCP servers
            for server_path in self.mcp_servers:
                server = MCPServer(server_path=server_path, db_path=str(self.db_engine.db_path))
                await server.start()
                self.mcp_servers_instances.append(server)
            logger.info(f"Started {len(self.mcp_servers_instances)} MCP servers")

            # Configure tool dependencies
            configure_tool_dependencies({"memory_manager": self.memory_manager})

            # Initialize tool registry once for all agents
            logger.info("Discovering and registering tools...")
            self.tool_registry = get_tool_registry()
            await self.tool_registry.discover_and_register_tools(
                core_tools_dir="tools/core", mcp_servers=self.mcp_servers_instances
            )

            # Get all tools and filter globally disabled ones
            assert self.tool_registry is not None
            all_tools = self.tool_registry.get_all_tools()
            # Convert dict tools to Tool objects
            self.enabled_tools = [
                Tool.from_dict(tool)
                for tool in all_tools
                if tool["name"] not in self.global_disabled_tools
            ]
            logger.info(
                f"Tool discovery complete: {len(self.enabled_tools)} tools enabled "
                f"({len(self.global_disabled_tools)} globally disabled)"
            )

            # Create MetaAgent
            self.meta_agent = MetaAgent(
                agent_id="METAGEN",
                instructions=None,
                memory_manager=self.memory_manager,
                llm_config={"llm": self.llm, "api_key": None},
                mcp_servers=self.mcp_servers_instances,
                available_tools=self.enabled_tools,
                max_iterations=50,  # Allow deeply nested tool calls and complex workflows
            )
            await self.meta_agent.initialize()

            # Configure tool approval if enabled
            if self._require_tool_approval:
                self.meta_agent.configure_tool_approval(
                    require_approval=self._require_tool_approval,
                    auto_approve_tools=list(self._auto_approve_tools),
                    approval_queue=self.meta_agent_input,
                )

            # Create single TaskExecutionAgent with execute_task disabled
            self.task_agent = TaskExecutionAgent(
                agent_id="TASK_AGENT_1",
                memory_manager=self.memory_manager,
                llm_config={"llm": self.llm, "api_key": None},
                mcp_servers=self.mcp_servers_instances,
                available_tools=self.enabled_tools,
                disabled_tools={"execute_task"},  # Prevent recursion
            )
            await self.task_agent.initialize()

            # Configure tool approval if enabled
            if self._require_tool_approval:
                self.task_agent.configure_tool_approval(
                    require_approval=self._require_tool_approval,
                    auto_approve_tools=list(self._auto_approve_tools),
                    approval_queue=self.task_agent_input,
                )

            # Register tool interceptor
            tool_executor = get_tool_executor()
            tool_executor.register_interceptor("execute_task", self._intercept_execute_task)

            # Start persistent agent tasks
            logger.debug("🚀 Starting persistent agent tasks...")
            self.run_meta_agent = asyncio.create_task(self._run_meta_agent())
            logger.debug("✅ Started MetaAgent task")
            self.run_task_agent = asyncio.create_task(self._run_task_agent())
            logger.debug("✅ Started TaskAgent task")
            self.router_task = asyncio.create_task(self._route_agent_outputs())
            logger.debug("✅ Started Router task")

            self._initialized = True

            # Get available tools
            tools = await self.meta_agent.get_available_tools()
            tool_names = [tool.name for tool in tools]

            logger.info(f"Available tools ({len(tool_names)}): {', '.join(tool_names)}")

            return UIResponse(
                type=ResponseType.SYSTEM,
                content="✓ AgentManager initialized successfully",
                agent_id="SYSTEM",
                metadata={
                    "agent_name": self.agent_name,
                    "agents": ["METAGEN", "TASK_AGENT_1"],
                    "memory_path": str(self.db_engine.db_path),
                    "available_tools": tool_names,
                    "llm": self.llm,
                    "architecture": "FIFO bidirectional streaming",
                },
            )

        except Exception as e:
            logger.error(f"Initialization failed: {e}", exc_info=True)
            return UIResponse(
                type=ResponseType.ERROR,
                content=f"Failed to initialize: {str(e)}",
                agent_id="SYSTEM",
                metadata={"error_type": type(e).__name__},
            )

    async def chat_stream(self, message: Message) -> AsyncIterator[Message]:
        """
        Simple bidirectional stream using persistent agents and unified output queue.

        Sends user message to MetaAgent and streams all agent outputs back to CLI.
        """
        # Get message content for logging
        msg_preview = (
            message.content[:50] if isinstance(message, ChatMessage) else str(message)[:50]
        )
        logger.debug(f"🚀 Chat stream started with message: {msg_preview}...")

        if not self._initialized:
            logger.debug("❌ Agent not initialized")
            yield ErrorMessage(
                error="Agent not initialized. Call initialize() first.", agent_id="SYSTEM"
            )
            return

        try:
            # Send message to MetaAgent input queue
            logger.info(f"📤 Sending {type(message).__name__} to MetaAgent input queue")
            logger.debug(f"📤 Full message: {message}")
            await self.meta_agent_input.put(message)
            logger.info(f"✅ {type(message).__name__} sent to MetaAgent input queue")

            # Stream outputs from CLI output queue
            # Router task is already forwarding all agent outputs here
            while True:
                try:
                    # Get next message with timeout
                    msg = await asyncio.wait_for(self.cli_output_queue.get(), timeout=0.1)
                    self._log_message(msg, "📥")
                    yield msg

                    # Check if this is a final response from MetaAgent
                    if isinstance(msg, AgentMessage) and msg.agent_id == "METAGEN" and msg.final:
                        # MetaAgent completed its response
                        logger.debug("🏁 Got final response from MetaAgent, breaking loop")
                        break
                    elif isinstance(msg, ErrorMessage):
                        logger.debug("❌ Got error response, breaking loop")
                        break

                except asyncio.TimeoutError:
                    # Normal behavior - just continue waiting
                    continue

        except Exception as e:
            logger.error(f"Error in chat_stream: {e}", exc_info=True)
            yield ErrorMessage(error=f"Error: {str(e)}", agent_id="SYSTEM")

    async def handle_tool_approval_response(
        self, approval_message: ApprovalResponseMessage
    ) -> None:
        """Handle tool approval response from UI/CLI.

        Routes the approval message to the appropriate agent.

        Args:
            approval_message: The approval response message from the user
        """
        logger.debug(
            f"🔨 Handling tool approval response: tool_id={approval_message.tool_id}, "
            f"decision={approval_message.decision}, agent_id={approval_message.agent_id}"
        )

        # Route to the appropriate agent based on agent_id
        if approval_message.agent_id == "METAGEN":
            await self.meta_agent_input.put(approval_message)
        elif approval_message.agent_id == self.task_agent.agent_id if self.task_agent else None:
            await self.task_agent_input.put(approval_message)
        else:
            logger.warning(f"Unknown agent_id in approval response: {approval_message.agent_id}")

    def _parse_agent_response(self, response: str) -> list[UIResponse]:
        """
        Parse agent response and extract tool calls, tool results, and text.

        This method identifies <function_calls> and <function_result> blocks
        and separates them from regular text content.
        """
        parts = []
        current_text = ""
        in_function_call = False
        in_function_result = False
        function_call_content = ""
        function_result_content = ""

        lines = response.split("\n")

        for line in lines:
            if "<function_calls>" in line:
                # Save any text before the function call
                if current_text.strip():
                    parts.append(
                        UIResponse(
                            type=ResponseType.TEXT,
                            content=current_text.strip(),
                            agent_id=self.current_agent_id,
                        )
                    )
                    current_text = ""

                in_function_call = True
                function_call_content = ""

                # Start tool call indicator
                parts.append(
                    UIResponse(
                        type=ResponseType.TOOL_CALL,
                        content="🔧 Calling tools...",
                        agent_id=self.current_agent_id,
                        metadata={"status": "started"},
                    )
                )

            elif "</function_calls>" in line:
                in_function_call = False

                # Parse the function call content to extract tool names
                tool_names = self._extract_tool_names(function_call_content)
                if tool_names:
                    parts.append(
                        UIResponse(
                            type=ResponseType.TOOL_CALL,
                            content=f"📞 Called: {', '.join(tool_names)}",
                            agent_id=self.current_agent_id,
                            metadata={"tools": tool_names, "status": "completed"},
                        )
                    )

                function_call_content = ""

            elif "<function_result>" in line:
                # Save any text before the function result
                if current_text.strip():
                    parts.append(
                        UIResponse(
                            type=ResponseType.TEXT,
                            content=current_text.strip(),
                            agent_id=self.current_agent_id,
                        )
                    )
                    current_text = ""

                in_function_result = True
                function_result_content = ""

            elif "</function_result>" in line:
                in_function_result = False

                # Parse and format the function result
                formatted_result = tool_result_formatter.format_tool_result(function_result_content)
                if formatted_result:
                    parts.append(
                        UIResponse(
                            type=ResponseType.TOOL_RESULT,
                            content=formatted_result,
                            agent_id=self.current_agent_id,
                            metadata={"raw_result": function_result_content.strip()},
                        )
                    )

                function_result_content = ""

            elif in_function_call:
                function_call_content += line + "\n"
            elif in_function_result:
                function_result_content += line + "\n"
            else:
                current_text += line + "\n"

        # Add any remaining text
        if current_text.strip():
            parts.append(
                UIResponse(
                    type=ResponseType.TEXT,
                    content=current_text.strip(),
                    agent_id=self.current_agent_id,
                )
            )

        return parts

    def _extract_tool_names(self, function_call_content: str) -> list[str]:
        """Extract tool names from function call XML content."""
        import re

        # Find all <invoke name="tool_name"> patterns
        pattern = r'<invoke name="([^"]+)">'
        matches = re.findall(pattern, function_call_content)
        return matches

    async def search_memory(self, query: str, limit: int = 10) -> list[UIResponse]:
        """Build context for a query (replaces simple search)."""
        if not self._initialized:
            return [
                UIResponse(
                    type=ResponseType.ERROR, content="Agent not initialized.", agent_id="SYSTEM"
                )
            ]

        try:
            current_agent = self._get_current_agent()
            context = await current_agent.build_context(query)
            responses = []

            # Show what context was built
            conversation_msgs = [msg for msg in context if msg["role"] in ["user", "assistant"]]
            if not conversation_msgs:
                responses.append(
                    UIResponse(
                        type=ResponseType.SYSTEM,
                        content=f"No conversation context found for: {query}",
                        agent_id=self.current_agent_id,
                    )
                )
            else:
                responses.append(
                    UIResponse(
                        type=ResponseType.SYSTEM,
                        content=(
                            f"Built context with {len(conversation_msgs)} conversation "
                            f"messages for: {query}"
                        ),
                        agent_id=self.current_agent_id,
                    )
                )

                # Show recent conversation messages (limit to what user requested)
                for msg in conversation_msgs[-limit * 2 :]:  # *2 because user+assistant pairs
                    role_prefix = "You: " if msg["role"] == "user" else f"{self.current_agent_id}: "
                    responses.append(
                        UIResponse(
                            type=ResponseType.TEXT,
                            content=role_prefix + msg["content"],
                            agent_id=self.current_agent_id,
                            metadata={"context_result": True, "role": msg["role"]},
                        )
                    )

            return responses

        except Exception as e:
            return [
                UIResponse(
                    type=ResponseType.ERROR,
                    content=f"Context building failed: {str(e)}",
                    agent_id="SYSTEM",
                )
            ]

    async def _intercept_execute_task(
        self, tool_call_id: str, tool_name: str, parameters: dict[str, Any]
    ) -> ToolCallResult:
        """
        Intercept execute_task calls using FIFO coordination with single TaskExecutionAgent.

        Creates completion Event, adds to FIFO queue, sends task to agent,
        and waits for router to signal completion when task finishes.

        Args:
            tool_name: Should be "execute_task"
            parameters: Tool parameters containing task_id and input_values

        Returns:
            ToolCallResult with the actual task execution result
        """
        logger.info(f"Intercepting execute_task with parameters: {parameters}")

        # Create completion event and add to FIFO queue
        completion_event = asyncio.Event()
        self.pending_task_completions.append(completion_event)
        logger.info(
            f"Added completion event to FIFO queue - now has "
            f"{len(self.pending_task_completions)} pending"
        )

        try:
            # Get task definition from storage
            task_id = parameters.get("task_id")
            input_values = parameters.get("input_values", {})

            if not task_id:
                return ToolCallResult(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    content="Missing required parameter: task_id",
                    is_error=True,
                    error="Missing task_id",
                    error_type=ToolErrorType.INVALID_ARGS,
                    user_display="Task ID is required for execution",
                    metadata={},
                )

            # Get task definition from storage
            if self.memory_manager is None:
                return ToolCallResult(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    content="Memory manager not initialized",
                    is_error=True,
                    error="System not initialized",
                    error_type=ToolErrorType.EXECUTION_ERROR,
                    user_display="System initialization error",
                    metadata={},
                )

            # Get task from memory manager
            task = await self.memory_manager.get_task(task_id)
            if not task:
                return ToolCallResult(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    content=f"Task definition not found: {task_id}",
                    is_error=True,
                    error="Task not found",
                    error_type=ToolErrorType.INVALID_ARGS,
                    user_display=f"Task {task_id} not found",
                    metadata={},
                )

            # Convert input values to typed parameter values
            typed_values = {}
            for key, value in input_values.items():
                # Find parameter in task definition
                param = next((p for p in task.definition.input_schema if p.name == key), None)
                if param:
                    typed_values[key] = ParameterValue(value=value, parameter_type=param.type)

            # Create execution context with tool_call_id
            context = TaskExecutionContext(
                task_id=task_id,
                task_name=task.name,
                instructions=task.definition.instructions,
                input_values=typed_values,
                tool_call_id=tool_call_id,  # Pass the original tool_call_id
                retry_count=0,
                timeout_seconds=None,
                allowed_tools=None,
            )

            # Set current task on the agent
            if self.task_agent is None:
                return ToolCallResult(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    content="Task agent not initialized",
                    is_error=True,
                    error="Task agent not available",
                    error_type=ToolErrorType.EXECUTION_ERROR,
                    user_display="Task execution agent is not available",
                    metadata={},
                )

            self.task_agent.set_current_task(context)

            # Build task prompt and send to TaskExecutionAgent as UserMessage
            task_prompt = self.task_agent.build_task_prompt(context)
            task_message = UserMessage(content=task_prompt)
            await self.task_agent_input.put(task_message)

            logger.info(f"Sent task '{task.name}' to TaskExecutionAgent, waiting for completion")

            # Wait for our turn in the FIFO queue (router will set this event)
            await completion_event.wait()

            # Get result from FIFO queue (router now puts ToolCallResult objects)
            if self.pending_task_results:
                task_result = self.pending_task_results.pop(0)

                # Router should have put a ToolCallResult from ToolResultMessage
                if isinstance(task_result, ToolCallResult):
                    logger.info(f"Task execution completed: {task_result.user_display}")
                    return task_result
                else:
                    # This shouldn't happen with the new design
                    logger.error(f"Unexpected result type from router: {type(task_result)}")
                    return ToolCallResult(
                        tool_name=tool_name,
                        tool_call_id=f"execute_task_{task_id}",
                        content="Task completed but result format was unexpected",
                        is_error=True,
                        error="Invalid result format from task execution",
                        error_type=ToolErrorType.EXECUTION_ERROR,
                        user_display="Task execution error: Invalid result format",
                        metadata={"task_id": task_id, "result_type": str(type(task_result))},
                    )
            else:
                # No result captured - this is an error
                logger.error("Task completed but no result captured in FIFO queue")
                return ToolCallResult(
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    content="Task completed but no result captured",
                    is_error=True,
                    error="No result captured from task execution",
                    error_type=ToolErrorType.EXECUTION_ERROR,
                    user_display="Task execution completed but result was not captured",
                    metadata={"task_id": task_id},
                )

        except Exception as e:
            logger.error(f"Error in task execution: {e}", exc_info=True)

            # Remove our completion event if we failed before execution
            if completion_event in self.pending_task_completions:
                self.pending_task_completions.remove(completion_event)

            return ToolCallResult(
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                content=f"Task execution failed: {str(e)}",
                is_error=True,
                error=str(e),
                error_type=ToolErrorType.EXECUTION_ERROR,
                user_display=f"Task execution error: {str(e)}",
                metadata={},
            )

    async def get_system_info(self) -> UIResponse:
        """Get system information."""
        if not self._initialized:
            return UIResponse(
                type=ResponseType.ERROR, content="Agent not initialized.", agent_id="SYSTEM"
            )

        try:
            # Get info from MetaAgent
            if self.meta_agent is None:
                return UIResponse(
                    type=ResponseType.ERROR, content="MetaAgent not initialized.", agent_id="SYSTEM"
                )

            info = self.meta_agent.get_agent_info()
            tools = await self.meta_agent.get_available_tools()
            model = await self.meta_agent.get_current_model()

            return UIResponse(
                type=ResponseType.SYSTEM,
                content=f"Agent: {info['agent_id']}\nModel: {model}\nTools: {len(tools)} available",
                agent_id="METAGEN",
                metadata={
                    "agent_info": info,
                    "model": model,
                    "tools": [t.name for t in tools],
                    "architecture": "FIFO bidirectional streaming",
                    "agents": [
                        "METAGEN",
                        self.task_agent.agent_id if self.task_agent else "TASK_UNKNOWN",
                    ],
                },
            )

        except Exception as e:
            return UIResponse(
                type=ResponseType.ERROR,
                content=f"Failed to get system info: {str(e)}",
                agent_id="SYSTEM",
            )

    async def cleanup(self) -> UIResponse:
        """Clean up resources."""
        try:
            # Cancel persistent tasks
            if self.run_meta_agent and not self.run_meta_agent.done():
                self.run_meta_agent.cancel()
            if self.run_task_agent and not self.run_task_agent.done():
                self.run_task_agent.cancel()
            if self.router_task and not self.router_task.done():
                self.router_task.cancel()

            # Cleanup agents
            if self.meta_agent:
                if self.meta_agent.llm_client:
                    await self.meta_agent.llm_client.close()
                await self.meta_agent.cleanup()
            if self.task_agent:
                if self.task_agent.llm_client:
                    await self.task_agent.llm_client.close()
                await self.task_agent.cleanup()

            # Stop all MCP servers
            for server in self.mcp_servers_instances:
                await server.stop()
            self.mcp_servers_instances.clear()

            self._initialized = False

            return UIResponse(
                type=ResponseType.SYSTEM, content="Agent shut down successfully", agent_id="SYSTEM"
            )

        except Exception as e:
            return UIResponse(
                type=ResponseType.ERROR, content=f"Cleanup error: {str(e)}", agent_id="SYSTEM"
            )

    def _log_agent_message(
        self, context: str, message: AgentMessage, outgoing: bool = False
    ) -> None:
        """Log agent message details.

        Args:
            context: Context string (e.g., "MetaAgent", "Sending to MetaAgent")
            message: The agent message
            outgoing: Whether this is an outgoing message
        """
        direction = "📤" if outgoing else "📥"

        if isinstance(message, UserMessage):
            logger.debug(f"{direction} {context} received USER message: {message.content[:50]}...")
        elif isinstance(message, ApprovalResponseMessage):
            logger.debug(
                f"{direction} {context} received TOOL_APPROVAL message for tool_id: "
                f"{message.tool_id}"
            )
        else:
            logger.debug(f"{direction} {context} received message type: {type(message).__name__}")

    async def _route_approval_message(
        self, approval_message: ApprovalResponseMessage, tool_id: str
    ) -> bool:
        """Route approval message to the appropriate agent.

        Args:
            approval_message: The approval message to route
            tool_id: The tool ID being approved/rejected

        Returns:
            True if message was routed, False otherwise
        """
        # Check both agents for pending approval
        agents_to_check: list[tuple[str, BaseAgent, asyncio.Queue]] = []
        if self.meta_agent:
            agents_to_check.append(("METAGEN", self.meta_agent, self.meta_agent_input))
        if self.task_agent:
            agents_to_check.append(
                (self.task_agent.agent_id, self.task_agent, self.task_agent_input)
            )

        # Route approval to the agent specified in the approval message
        for agent_id, agent, input_queue in agents_to_check:
            if agent_id == approval_message.agent_id:
                logger.info(f"Routing approval to agent {agent_id} via message queue")
                await input_queue.put(approval_message)
                return True

        logger.warning(f"No agent found with ID {approval_message.agent_id} for approval")
        return False
