"""AgentManager - Manages multiple active agents and intercepts tool calls for dynamic agent
creation."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Optional

from agents.meta_agent import MetaAgent
from agents.task_execution_agent import TaskExecutionAgent
from agents.tool_approval import ToolApprovalResponse
from agents.tool_result_formatter import tool_result_formatter
from client.agentic_client import AgenticClient
from client.mcp_server import MCPServer
from client.models import ModelID
from memory import MemoryManager, SQLiteBackend
from tools.base import ToolResult
from tools.registry import configure_tool_dependencies, get_tool_executor

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


@dataclass
class AgentMessage:
    """Message from agent to AgentManager with attribution and timing."""

    agent_id: str
    stage_event: dict
    timestamp: float = field(default_factory=time.time)


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
        db_manager: Any = None,
        mcp_servers: Optional[list[str]] = None,
        llm: ModelID = ModelID.CLAUDE_SONNET_4,
    ) -> None:
        """
        Initialize AgentManager.

        Args:
            agent_name: Name for the agent
            db_manager: DatabaseManager instance
            mcp_servers: List of MCP server paths
            llm: LLM specification for MCP client
        """
        self.agent_name = agent_name
        self.db_manager = db_manager
        self.mcp_servers = mcp_servers or ["tools/mcp_server.py"]
        self.llm = llm

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
        self.approval_timeout_task: Optional[asyncio.Task] = None

        # FIFO coordination for task completion
        self.pending_task_completions: list[asyncio.Event] = []
        self.pending_task_results: list[str] = []

        # Tool approval configuration
        self._require_tool_approval: bool = False
        self._auto_approve_tools: set[str] = set()
        self._approval_timeout: float = 30.0
        self.approval_response_queue: asyncio.Queue = asyncio.Queue()

        # Initialization state
        self._initialized = False

    def _get_current_agent(self) -> Any:
        """Get the current active agent based on current_agent_id."""
        if self.current_agent_id == "METAGEN":
            return self.meta_agent
        else:
            return self.task_agent

    def configure_tool_approval(
        self,
        require_approval: bool = False,
        auto_approve_tools: Optional[set[str]] = None,
        approval_timeout: float = 30.0,
    ) -> None:
        """Configure tool approval settings for all agents.

        Args:
            require_approval: Whether to require approval for tool execution
            auto_approve_tools: Set of tool names that don't need approval
            approval_timeout: Timeout in seconds for approval
        """
        self._require_tool_approval = require_approval
        self._auto_approve_tools = auto_approve_tools or set()
        self._approval_timeout = approval_timeout

        logger.info(
            f"Tool approval configured: require={require_approval}, "
            f"auto_approve={list(self._auto_approve_tools)}, "
            f"timeout={approval_timeout}s"
        )

        # Configure existing agents if already initialized
        if self.meta_agent:
            self.meta_agent.configure_tool_approval(
                require_approval=require_approval,
                auto_approve_tools=auto_approve_tools,
                approval_timeout=approval_timeout,
                approval_response_queue=self.approval_response_queue,
            )

        if self.task_agent:
            self.task_agent.configure_tool_approval(
                require_approval=require_approval,
                auto_approve_tools=auto_approve_tools,
                approval_timeout=approval_timeout,
                approval_response_queue=self.approval_response_queue,
            )

    async def _create_agentic_client(self) -> AgenticClient:
        """Create a new agentic client instance for an agent."""
        client = AgenticClient(llm=self.llm, mcp_servers=self.mcp_servers_instances)
        await client.initialize()
        return client

    async def _run_meta_agent(self) -> None:
        """MetaAgent runs forever, processing messages from its input queue."""
        logger.info("Starting MetaAgent")
        error_count = 0
        max_consecutive_errors = 5

        while True:
            try:
                # Wait for message from AgentManager
                message = await self.meta_agent_input.get()
                logger.info(f"MetaAgent processing message: {message[:50]}...")

                # Process message and stream output back to unified queue
                if self.meta_agent is None:
                    logger.error("MetaAgent not initialized")
                    continue

                async for stage_event in self.meta_agent.stream_chat(message):
                    await self.unified_agent_output.put(AgentMessage("METAGEN", stage_event))

                logger.info("MetaAgent completed processing message")
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
                    AgentMessage(
                        "METAGEN",
                        {
                            "stage": "error",
                            "content": f"An error occurred: {str(e)}",
                            "metadata": {"error": str(e), "error_count": error_count},
                        },
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
                # Wait for task prompt from AgentManager (via tool interceptor)
                task_prompt = await self.task_agent_input.get()
                logger.info(f"TaskExecutionAgent received task: {task_prompt[:50]}...")

                # Execute task and stream output back to unified queue
                if self.task_agent is None:
                    logger.error("TaskExecutionAgent not initialized")
                    continue

                async for stage_event in self.task_agent.stream_chat(task_prompt):
                    await self.unified_agent_output.put(
                        AgentMessage(self.task_agent.agent_id, stage_event)
                    )

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
                    AgentMessage(
                        self.task_agent.agent_id if self.task_agent else "TASK_UNKNOWN",
                        {
                            "stage": "error",
                            "content": f"Task execution error: {str(e)}",
                            "metadata": {"error": str(e), "error_count": error_count},
                        },
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

    async def _check_approval_timeouts(self) -> None:
        """Periodically check for timed-out approval requests."""
        logger.info("Starting approval timeout checker")

        while True:
            try:
                # Wait 5 seconds between checks
                await asyncio.sleep(5.0)

                # Check all agents for expired approvals
                agents_to_check = []
                if self.meta_agent:
                    agents_to_check.append(("METAGEN", self.meta_agent))
                if self.task_agent:
                    agents_to_check.append((self.task_agent.agent_id, self.task_agent))

                for agent_id, agent in agents_to_check:
                    # Get timeout events from the agent
                    timeout_events = await agent.check_expired_approvals()

                    # Send timeout events to the output queue
                    for event in timeout_events:
                        await self.unified_agent_output.put(AgentMessage(agent_id, event))

            except asyncio.CancelledError:
                logger.info("Approval timeout checker cancelled")
                break
            except Exception as e:
                logger.error(f"Error in approval timeout checker: {e}", exc_info=True)
                # Continue checking even if there's an error
                await asyncio.sleep(1.0)

    async def _route_agent_outputs(self) -> None:
        """ONLY consumer of unified output queue with FIFO coordination."""
        logger.info("Starting message router")
        error_count = 0
        max_consecutive_errors = 10  # Higher threshold for router

        while True:
            try:
                # Wait for output from any agent
                msg = await self.unified_agent_output.get()

                # Check for task completion using FIFO assumption
                if (
                    self.task_agent is not None
                    and msg.agent_id == self.task_agent.agent_id
                    and msg.stage_event["stage"] == "response"
                ):
                    logger.info(
                        f"TaskExecutionAgent completed - FIFO queue has "
                        f"{len(self.pending_task_completions)} pending completions"
                    )

                    # Signal the next pending task completion (FIFO order)
                    if self.pending_task_completions:
                        self.pending_task_results.append(msg.stage_event["content"])
                        completion_event = self.pending_task_completions.pop(0)
                        completion_event.set()
                        logger.info(
                            f"Signaled completion event, "
                            f"{len(self.pending_task_completions)} remaining"
                        )

                # Always forward to CLI
                ui_response = UIResponse(
                    type=self._map_stage_to_response_type(msg.stage_event["stage"]),
                    content=msg.stage_event["content"],
                    agent_id=msg.agent_id,
                    metadata=msg.stage_event.get("metadata", {}),
                    timestamp=datetime.fromtimestamp(msg.timestamp),
                )
                await self.cli_output_queue.put(ui_response)

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
        }
        return stage_mapping.get(stage, ResponseType.SYSTEM)

    async def initialize(self) -> UIResponse:
        """Initialize all components and return status."""
        logger.info("Initializing AgentManager with FIFO architecture")

        try:
            # Create memory manager
            logger.info("🔍 Creating SQLiteBackend with DatabaseManager")
            backend = SQLiteBackend(self.db_manager)
            self.memory_manager = MemoryManager(backend)
            await self.memory_manager.initialize()
            logger.info("Memory manager initialized")

            # Create MCP servers
            for server_path in self.mcp_servers:
                server = MCPServer(server_path=server_path, db_path=str(self.db_manager.db_path))
                await server.start()
                self.mcp_servers_instances.append(server)
            logger.info(f"Started {len(self.mcp_servers_instances)} MCP servers")

            # Configure tool dependencies
            configure_tool_dependencies(
                {"storage": self.memory_manager.storage, "memory_manager": self.memory_manager}
            )

            # Create MetaAgent
            meta_client = await self._create_agentic_client()
            self.meta_agent = MetaAgent(
                agent_id="METAGEN",
                instructions=None,
                memory_manager=self.memory_manager,
                agentic_client=meta_client,
            )
            await self.meta_agent.initialize()

            # Configure tool approval if enabled
            if self._require_tool_approval:
                self.meta_agent.configure_tool_approval(
                    require_approval=self._require_tool_approval,
                    auto_approve_tools=self._auto_approve_tools,
                    approval_timeout=self._approval_timeout,
                    approval_response_queue=self.approval_response_queue,
                )

            # Create single TaskExecutionAgent with execute_task disabled
            task_client = await self._create_agentic_client()
            # Disable execute_task for TaskExecutionAgent to prevent recursion
            task_client.disabled_tools.add("execute_task")
            self.task_agent = TaskExecutionAgent(
                agent_id="TASK_AGENT_1",
                agentic_client=task_client,
                memory_manager=self.memory_manager,
            )
            await self.task_agent.initialize()

            # Configure tool approval if enabled
            if self._require_tool_approval:
                self.task_agent.configure_tool_approval(
                    require_approval=self._require_tool_approval,
                    auto_approve_tools=self._auto_approve_tools,
                    approval_timeout=self._approval_timeout,
                    approval_response_queue=self.approval_response_queue,
                )

            # Register tool interceptor
            tool_executor = get_tool_executor()
            tool_executor.register_interceptor("execute_task", self._intercept_execute_task)

            # Start persistent agent tasks
            self.run_meta_agent = asyncio.create_task(self._run_meta_agent())
            self.run_task_agent = asyncio.create_task(self._run_task_agent())
            self.router_task = asyncio.create_task(self._route_agent_outputs())

            # Start approval timeout checker if approval is enabled
            if self._require_tool_approval:
                self.approval_timeout_task = asyncio.create_task(self._check_approval_timeouts())

            self._initialized = True

            # Get available tools
            tools = await self.meta_agent.get_available_tools()
            tool_names = [tool["name"] for tool in tools]

            logger.info(f"Available tools ({len(tool_names)}): {', '.join(tool_names)}")

            return UIResponse(
                type=ResponseType.SYSTEM,
                content="✓ AgentManager initialized successfully",
                agent_id="SYSTEM",
                metadata={
                    "agent_name": self.agent_name,
                    "agents": ["METAGEN", "TASK_AGENT_1"],
                    "memory_path": str(self.db_manager.db_path),
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

    async def chat_stream(self, message: str) -> AsyncIterator[UIResponse]:
        """
        Simple bidirectional stream using persistent agents and unified output queue.

        Sends user message to MetaAgent and streams all agent outputs back to CLI.
        """
        logger.info(f"Chat stream started with message: {message[:50]}...")

        if not self._initialized:
            yield UIResponse(
                type=ResponseType.ERROR,
                content="Agent not initialized. Call initialize() first.",
                agent_id="SYSTEM",
            )
            return

        try:
            # Send message to MetaAgent input queue
            await self.meta_agent_input.put(message)

            # Stream outputs from CLI output queue
            # Router task is already forwarding all agent outputs here
            while True:
                try:
                    # Get next UI response with timeout
                    ui_response = await asyncio.wait_for(self.cli_output_queue.get(), timeout=0.1)
                    yield ui_response

                    # Check if this is a final response from MetaAgent
                    if ui_response.agent_id == "METAGEN" and ui_response.type == ResponseType.TEXT:
                        # MetaAgent completed its response
                        break

                except asyncio.TimeoutError:
                    # Check if agents are still processing
                    # In future, we could add activity tracking here
                    continue

        except Exception as e:
            logger.error(f"Error in chat_stream: {e}", exc_info=True)
            yield UIResponse(
                type=ResponseType.ERROR,
                content=f"Error: {str(e)}",
                agent_id="SYSTEM",
                metadata={"error_type": type(e).__name__},
            )

    async def handle_tool_approval_response(self, approval_response: ToolApprovalResponse) -> None:
        """Handle tool approval response from UI/CLI.

        Routes the approval to the correct agent and processes it asynchronously.

        Args:
            approval_response: The approval response from the user
        """
        logger.info(
            f"Handling tool approval response: tool_id={approval_response.tool_id}, "
            f"decision={approval_response.decision}"
        )

        # Determine which agent should handle this approval
        # For now, we'll check both agents for pending approvals
        agents_to_check = []
        if self.meta_agent:
            agents_to_check.append(("METAGEN", self.meta_agent))
        if self.task_agent:
            agents_to_check.append((self.task_agent.agent_id, self.task_agent))

        # Find the agent with this pending approval
        handled = False
        for agent_id, agent in agents_to_check:
            if approval_response.tool_id in agent._pending_approvals:
                logger.info(f"Routing approval to agent {agent_id}")

                # Process the approval and emit events
                async for event in agent.process_approval_response(approval_response):
                    # Send events to the unified output queue
                    await self.unified_agent_output.put(AgentMessage(agent_id, event))

                handled = True
                break

        if not handled:
            logger.warning(
                f"No agent found with pending approval for tool_id: {approval_response.tool_id}. "
                f"The approval may have already timed out."
            )

            # Still send a notification event
            await self.unified_agent_output.put(
                AgentMessage(
                    "SYSTEM",
                    {
                        "stage": "tool_approval_orphaned",
                        "content": f"No pending approval found for tool {approval_response.tool_id}",
                        "metadata": {
                            "tool_id": approval_response.tool_id,
                            "decision": approval_response.decision.value,
                        },
                    },
                )
            )

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
        self, tool_name: str, parameters: dict[str, Any]
    ) -> ToolResult:
        """
        Intercept execute_task calls using FIFO coordination with single TaskExecutionAgent.

        Creates completion Event, adds to FIFO queue, sends task to agent,
        and waits for router to signal completion when task finishes.

        Args:
            tool_name: Should be "execute_task"
            parameters: Tool parameters containing task_id and input_values

        Returns:
            ToolResult with the actual task execution result
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
                return ToolResult(
                    success=False,
                    llm_content="Missing required parameter: task_id",
                    error="Missing task_id",
                    user_display="Task ID is required for execution",
                    metadata={"tool_name": tool_name},
                )

            # Get task definition from storage
            if self.memory_manager is None:
                return ToolResult(
                    success=False,
                    llm_content="Memory manager not initialized",
                    error="System not initialized",
                    user_display="System initialization error",
                    metadata={"tool_name": tool_name},
                )

            # Access storage backend directly as it has get_task method
            # TODO: Add proper type for storage backend that includes task methods
            storage = self.memory_manager.storage  # type: ignore[attr-defined]
            task = await storage.get_task(task_id)  # type: ignore[attr-defined]
            if not task:
                return ToolResult(
                    success=False,
                    llm_content=f"Task definition not found: {task_id}",
                    error="Task not found",
                    user_display=f"Task {task_id} not found",
                    metadata={"tool_name": tool_name},
                )

            # Create TaskExecutionRequest
            from memory.storage.task_models import TaskExecutionRequest

            task_request = TaskExecutionRequest.create_for_task(
                task_id=task_id, input_values=input_values
            )

            # Set current task on the agent
            if self.task_agent is None:
                return ToolResult(
                    success=False,
                    llm_content="Task agent not initialized",
                    error="Task agent not available",
                    user_display="Task execution agent is not available",
                    metadata={"tool_name": tool_name},
                )

            self.task_agent.set_current_task(task_request)

            # Build task prompt and send to TaskExecutionAgent
            task_prompt = self.task_agent.build_task_prompt(task_request)
            await self.task_agent_input.put(task_prompt)

            logger.info(f"Sent task '{task.name}' to TaskExecutionAgent, waiting for completion")

            # Wait for our turn in the FIFO queue (router will set this event)
            await completion_event.wait()

            # Get result from FIFO queue (router puts results in same order)
            if self.pending_task_results:
                final_result = self.pending_task_results.pop(0)
            else:
                final_result = "Task completed but no result captured"

            logger.info(f"Task execution completed with result: {final_result[:100]}...")

            return ToolResult(
                success=True,
                llm_content=final_result,
                user_display=f"Task completed: {final_result}",
                error=None,
                metadata={"task_execution": "completed", "task_id": task_id},
            )

        except Exception as e:
            logger.error(f"Error in task execution: {e}", exc_info=True)

            # Remove our completion event if we failed before execution
            if completion_event in self.pending_task_completions:
                self.pending_task_completions.remove(completion_event)

            return ToolResult(
                success=False,
                llm_content=f"Task execution failed: {str(e)}",
                error=str(e),
                user_display=f"Task execution error: {str(e)}",
                metadata={"tool_name": tool_name},
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
                content=f"Agent: {info['name']}\nModel: {model}\nTools: {len(tools)} available",
                agent_id="METAGEN",
                metadata={
                    "agent_info": info,
                    "model": model,
                    "tools": [t["name"] for t in tools],
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
            if self.approval_timeout_task and not self.approval_timeout_task.done():
                self.approval_timeout_task.cancel()

            # Cleanup agents
            if self.meta_agent:
                await self.meta_agent.agentic_client.close()
                await self.meta_agent.cleanup()
            if self.task_agent:
                await self.task_agent.agentic_client.close()
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
