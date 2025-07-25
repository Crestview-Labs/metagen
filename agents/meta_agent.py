"""MetaAgent - Personal agent with context-aware memory and MCP tool integration."""

import logging
from typing import Any, Optional

from opentelemetry import trace

from agents.base import AgentMessage, BaseAgent, ContextSummary

logger = logging.getLogger(__name__)


class MetaAgent(BaseAgent):
    """
    Personal meta-agent that:
    - Maintains continuous conversation flow with context-aware memory
    - Uses MCPx for tool calling capabilities (memory search, conversation compaction)
    - Leverages LLM intelligence to decide when and how to use tools
    - Automatically manages context discovery and memory organization
    """

    def __init__(
        self,
        agent_id: str = "METAGEN",
        instructions: Optional[str] = None,
        memory_manager: Any = None,
        agentic_client: Any = None,
        mcp_servers: Optional[list[str]] = None,
    ) -> None:
        # Initialize OpenTelemetry tracer
        self.tracer = trace.get_tracer(__name__)
        """
        Initialize MetaAgent.
        
        Args:
            agent_id: Agent identifier (defaults to "METAGEN")
            instructions: System instructions
            memory_manager: Memory manager for conversation storage
            agentic_client: Agentic client for LLM + tool calling
            mcp_servers: List of MCP server paths (defaults to ["tools/mcp_server.py"])
        """
        default_instructions = """You are MetaAgent, a superintelligent personal assistant with
comprehensive tool access and task management capabilities.

## Core Responsibilities

### 1. Task Management (Primary Responsibility)
You are the central task manager responsible for:
- **Search existing tasks** using `list_tasks` to find reusable solutions
- **Create new tasks** using `create_task` for non-trivial, multi-step jobs that can be reused
- **Execute tasks** using `execute_task` to delegate complex work to TaskExecutionAgent
- **Update tasks** (when tooling becomes available) to improve reusable solutions

**MANDATORY: You MUST use task management tools**
- When asked about tasks: ALWAYS call `list_tasks` tool, never describe tasks in text
- When creating tasks: ALWAYS call `create_task` tool, never just describe what you would create
- When executing tasks: ALWAYS call `execute_task` tool with actual parameters
- NEVER respond with text descriptions of tasks - ALWAYS use the actual tools

**CRITICAL: Task Creation Standards**
When creating tasks, define them like formal tools with proper schemas:
- Use EXACT parameter names that match function signatures
- Define clear input/output schemas with types and validation
- Write instructions as if creating a function specification
- Ensure parameter names in task definition match exactly what you'll send during execution

### 2. Direct Tool Usage for Simple Jobs
For trivial, single-step operations, use tools directly:
- `read_file`, `write_file`, `search_files` for simple file operations
- `gmail_search`, `drive_search_files` for basic searches
- Any single-step operation that doesn't benefit from reuse

### 3. Smart Task vs Direct Tool Decision Making

**CREATE TASKS for non-trivial jobs that are:**
- Multi-step processes (3+ distinct operations)
- Complex workflows that could be reused
- Jobs requiring specific business logic or validation
- Operations that other users might need to repeat
- Processes that benefit from structured input/output parameters

**USE TOOLS DIRECTLY for trivial jobs like:**
- Reading a single file
- Writing simple content to a file
- Basic search operations
- Single API calls
- One-off operations with no reuse value

**Key Principle: REUSABILITY**
Before creating a task, ask: "Would this process be valuable for future requests?"
If yes, create a task. If no, use tools directly.

### 4. Memory and Context Management
- Use memory tools when users reference past conversations
- Maintain conversation continuity across sessions
- Be proactive in leveraging conversation history

## Example Decision Flow

User Request: "Write 'Hello World' to test.txt"
→ **Direct tool usage**: `write_file(path="test.txt", content="Hello World")`
→ Reason: Simple, single-step, no reuse value

User Request: "Create a weekly report from my email and calendar data"
→ **Task creation approach**:
1. `list_tasks` to check for existing report generation tasks
2. If none exist, `create_task` with formal schema:
   ```
   name: "weekly_report_generator"
   input_parameters: [
     {"name": "start_date", "type": "string", "required": true},
     {"name": "end_date", "type": "string", "required": true}, 
     {"name": "output_file", "type": "string", "required": true},
     {"name": "include_calendar", "type": "boolean", "required": false}
   ]
   ```
3. `execute_task` with EXACT parameter names: start_date, end_date, output_file, include_calendar
→ Reason: Multi-step, reusable, formal schema prevents parameter mismatches

Be intelligent, efficient, and always consider the reusability factor when deciding between
task creation and direct tool usage."""

        super().__init__(
            agent_id=agent_id,
            instructions=instructions or default_instructions,
            agentic_client=agentic_client,
            memory_manager=memory_manager,
        )

        self.mcp_servers = mcp_servers or ["tools/mcp_server.py"]

        # Current conversation state
        self.current_conversation: list[AgentMessage] = []
        self.active_contexts: list[ContextSummary] = []

        # Tool result display setting (default to False for cleaner output)
        self.show_tool_results: bool = False

    async def build_context(self, query: str, max_tokens: int = 10000) -> list[dict[str, Any]]:
        """
        Build comprehensive context for a query by combining all memory tiers.

        Current implementation: Conversation history only
        TODO: Add semantic search across compact and long-term memories

        Args:
            query: The query to build context for
            max_tokens: Maximum tokens for context (for future token management)

        Returns:
            List of message dictionaries for LLM context
        """
        conversation = []

        # System message with instructions and tool information
        system_content = self.instructions

        if self.agentic_client:
            tools = await self.agentic_client.get_available_tools()
            logger.debug(f"Found {len(tools)} available tools")
            for tool in tools:
                logger.debug(f"Tool available: {tool['name']}")

            tool_descriptions = []
            for tool in tools:
                tool_descriptions.append(f"- {tool['name']}: {tool['description']}")

            system_content += "\\n\\nAvailable tools:\\n" + "\\n".join(tool_descriptions)
            logger.debug(f"System content length: {len(system_content)} chars")

        conversation.append({"role": "system", "content": system_content})

        # 1. Recent uncompacted conversation history (always included)
        if self.memory_manager:
            try:
                turns = await self.memory_manager.storage.get_turns_by_agent(
                    agent_id=self.agent_id,
                    limit=10,  # TODO: Make this dynamic based on max_tokens
                )

                # Convert turns to conversation format
                for turn in turns:
                    # Always add user query if non-empty
                    if turn.user_query and turn.user_query.strip():
                        conversation.append({"role": "user", "content": turn.user_query})

                    # Only add assistant response if non-empty
                    if turn.agent_response and turn.agent_response.strip():
                        conversation.append({"role": "assistant", "content": turn.agent_response})
            except Exception as e:
                logger.debug(f"Error getting recent conversation: {e}")

        # TODO: 2. Semantic search across compact memories
        # if self.memory_manager:
        #     try:
        #         relevant_compact = await self.memory_manager.search_compact_memories(
        #             agent_id=self.agent_id,
        #             query=query,
        #             limit=5  # Get top 5 relevant compact memories
        #         )
        #
        #         # Add relevant compact memories as system messages
        #         for compact in relevant_compact:
        #             conversation.append({
        #                 "role": "system",
        #                 "content": f"Relevant context: {compact['title']}\n{compact['content']}"
        #             })
        #     except Exception as e:
        #         print(f"🔍 DEBUG: Error searching compact memories: {e}")

        # TODO: 3. Semantic search across long-term memories
        # if self.memory_manager:
        #     try:
        #         relevant_long_term = await self.memory_manager.search_long_term_memories(
        #             agent_id=self.agent_id,
        #             query=query,
        #             limit=3  # Get top 3 relevant long-term memories
        #         )
        #
        #         # Add relevant long-term memories as system context
        #         for memory in relevant_long_term:
        #             conversation.append({
        #                 "role": "system",
        #                 "content": f"Agent knowledge: {memory['title']}\n{memory['content']}"
        #             })
        #     except Exception as e:
        #         print(f"🔍 DEBUG: Error searching long-term memories: {e}")

        # TODO: 4. Token management and intelligent prioritization
        # - Count tokens in current context
        # - If over max_tokens, prioritize: recent conversations > relevant long-term > compact
        # - Trim older/less relevant content first
        # - Ensure system message and most recent conversation always included

        return conversation
