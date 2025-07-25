"""Memory operation tools."""

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from client.base_client import BaseClient
from memory.storage.manager import MemoryManager
from memory.storage.memory_models import CompactMemory
from memory.storage.models import ConversationTurn
from tools.base import BaseLLMTool

logger = logging.getLogger(__name__)


# Schemas for MemorySearch tool
class MemorySearchInput(BaseModel):
    """Input for memory search operations."""

    query: str = Field(..., description="What the user is looking for")
    context: Optional[str] = Field(
        None, description="Additional context about what type of information is needed"
    )


class MemorySearchOutput(BaseModel):
    """Output from memory search operations."""

    response: str = Field(
        ..., description="LLM-formatted response with relevant memories and context"
    )
    memory_stats: dict[str, int] = Field(..., description="Statistics about memories analyzed")


class MemorySearchTool(BaseLLMTool):
    """Tool for LLM-based intelligent memory search across all three tiers."""

    # TODO: Implement hierarchical summaries to reduce LLM input size
    # - Create progressive summarization: detailed → medium → high-level summaries
    # - Use chunking strategy for large memory sets
    # - Implement memory relevance pre-filtering before LLM analysis

    # TODO: Add support for large context models for better memory search
    # - Integrate Gemini Flash (1M context) for comprehensive memory analysis
    # - Use Gemini Pro (2M context) for extensive historical searches
    # - Implement dynamic model selection based on memory size

    def __init__(self, memory_manager: MemoryManager, llm_client: BaseClient):
        instructions = """You are an intelligent memory search system. Given a user's search query,
analyze the available memories and return the most relevant results.

SEARCH QUERY: {{QUERY}}

AVAILABLE MEMORIES:
{{MEMORIES}}

Your task:
1. **Understand the search intent** - What is the user actually looking for?
2. **Analyze semantic relevance** - Which memories relate to the query by meaning,
   not just keywords?
3. **Prioritize by usefulness** - Rank results by how helpful they would be for
   the user's current context
4. **Return structured results** - Provide the most relevant memories with explanations

Consider:
- Semantic similarity (topics, concepts, themes)
- Temporal relevance (recent vs historical context)
- Memory type importance (preferences > knowledge > summaries > raw conversations)
- User intent and context

Return the most relevant memories with clear explanations of why they match."""

        super().__init__(
            name="memory_search",
            description="Intelligently search agent memory using semantic understanding",
            input_schema=MemorySearchInput,
            output_schema=MemorySearchOutput,
            instructions=instructions,
            llm_client=llm_client,
            task_type="analysis",
        )
        self.memory_manager = memory_manager

    async def _gather_all_memories(self) -> list[dict[str, Any]]:
        """Gather all available memories from the memory manager."""
        memories = []

        # Get recent conversation turns
        recent_turns = await self.memory_manager.get_recent_turns(days=7, limit=50)
        for turn in recent_turns:
            memories.append(
                {
                    "memory_type": "conversations",
                    "id": turn.id,
                    "content": f"User: {turn.user_query}\nAgent: {turn.agent_response}",
                    "timestamp": turn.timestamp,
                    "metadata": turn.user_metadata,
                }
            )

        # Get compact memories
        compact_mems = await self.memory_manager.get_recent_compact_memories(limit=20)
        for mem in compact_mems:
            memories.append(
                {
                    "memory_type": "compact",
                    "id": mem.id,
                    "content": mem.summary,
                    "key_points": mem.key_points,
                    "timestamp": mem.created_at,
                }
            )

        return memories

    def _format_memories_for_llm(self, memories: list[dict[str, Any]]) -> str:
        """Format memories into a structured string for LLM analysis."""
        formatted_parts = []

        for mem in memories:
            mem_type = mem.get("memory_type", "unknown")
            mem_id = mem.get("id", "no-id")
            content = mem.get("content", "")

            formatted_parts.append(f"[{mem_type.upper()}] ID: {mem_id[:8]}...")
            formatted_parts.append(content[:500])  # Truncate long content
            if "key_points" in mem:
                formatted_parts.append(f"Key Points: {', '.join(mem['key_points'][:3])}")
            formatted_parts.append("")  # Empty line between memories

        return "\n".join(formatted_parts)

    def _build_prompt(self, input_data: BaseModel) -> str:
        """Build the prompt for the LLM."""
        # Cast to specific type
        search_input: MemorySearchInput = input_data  # type: ignore[assignment]

        # Gather memories for prompt building
        import asyncio

        memories = asyncio.run(self._gather_all_memories())
        formatted_memories = self._format_memories_for_llm(memories)

        prompt = self.instructions.replace("{{QUERY}}", search_input.query)
        prompt = prompt.replace("{{MEMORIES}}", formatted_memories)

        if search_input.context:
            prompt += f"\n\nADDITIONAL CONTEXT:\n{search_input.context}"

        return prompt

    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """Use LLM to intelligently search and analyze memories."""
        # Cast to specific type
        search_input: MemorySearchInput = input_data  # type: ignore[assignment]
        try:
            # Gather all available memories for LLM analysis
            memories = await self._gather_all_memories()

            # Count memories by type for stats
            memory_stats = {"semantic": 0, "compact": 0, "conversations": 0}
            for memory in memories:
                memory_type = memory.get("memory_type", "conversations")
                memory_stats[memory_type] = memory_stats.get(memory_type, 0) + 1

            # Format memories for LLM
            _ = self._format_memories_for_llm(memories)  # TODO: Use when LLM is integrated

            # Build prompt with query and optional context
            _ = self._build_prompt(search_input)  # TODO: Use when LLM is integrated

            # Use BaseLLMTool's LLM calling to get intelligent response
            # TODO: Once BaseLLMTool is properly integrated, this will call the LLM
            # For now, return a placeholder response
            llm_response = f"""Based on your query "{search_input.query}",
here are the relevant memories:

[Placeholder - LLM analysis would go here]

Analyzed {sum(memory_stats.values())} total memories:
- {memory_stats["semantic"]} semantic memories (knowledge/preferences)
- {memory_stats["compact"]} compact summaries
- {memory_stats["conversations"]} conversation turns"""

            return MemorySearchOutput(response=llm_response, memory_stats=memory_stats)

        except Exception as e:
            logger.error(f"Error in memory search: {str(e)}", exc_info=True)
            return MemorySearchOutput(
                response=f"Error searching memories: {str(e)}",
                memory_stats={"semantic": 0, "compact": 0, "conversations": 0},
            )

    def _format_display(self, output: BaseModel) -> str:
        """Format search results for display."""
        # Cast to specific type
        search_output: MemorySearchOutput = output  # type: ignore[assignment]
        # Return the LLM-formatted response directly
        return search_output.response


# Schemas for CompactConversation tool
class CompactConversationInput(BaseModel):
    """Input for conversation compaction."""

    agent_id: str = Field(..., description="Agent ID to compact conversations for")
    max_input_tokens: int = Field(
        50000, description="Maximum input tokens to process (limited by LLM context)"
    )
    max_output_length: int = Field(2000, description="Maximum length of output in tokens")


class CompactConversationOutput(BaseModel):
    """Output of conversation compaction."""

    agent_id: str = Field(..., description="Agent ID this compact memory belongs to")
    title: str = Field(..., description="Brief description of the conversation period")
    content: str = Field(
        ...,
        description="Chronological summary of conversations including key points, "
        "decisions, and outcomes",
    )
    start_conversation_id: str = Field(
        ..., description="ID of the first conversation turn that was compacted"
    )
    end_conversation_id: str = Field(
        ..., description="ID of the last conversation turn that was compacted"
    )


class CompactConversationTool(BaseLLMTool):
    """Tool for compacting conversations using LLM."""

    def __init__(self, memory_manager: MemoryManager, llm_client: BaseClient):
        self.memory_manager = memory_manager
        instructions = """Analyze and compact this conversation into a structured
memory for the specified agent.

Agent ID: {{AGENT_ID}}

Conversation:
{{CONVERSATIONS}}

Create a compact memory that captures the chronological flow and key information
from this conversation period.

Your output should include:
1. **Title**: A brief description that captures the main theme or time period
2. **Content**: A comprehensive chronological summary
   (maximum {{MAX_OUTPUT_LENGTH}} tokens) that includes:
   - Key points and decisions made
   - User preferences expressed
   - Important feedback received
   - Task progress and outcomes
   - Tools used and their effectiveness
   - Any patterns or insights observed

The content should maintain chronological order while highlighting the most
important information for future reference."""

        super().__init__(
            name="compact_conversation",
            description="Compacts conversations into chronological summaries for a specific agent",
            input_schema=CompactConversationInput,
            output_schema=CompactConversationOutput,
            instructions=instructions,
            llm_client=llm_client,
            task_type="summarization",
        )

    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """Compact conversations by collecting them internally."""
        # Cast to specific type
        compact_input: CompactConversationInput = input_data  # type: ignore[assignment]
        try:
            # Get uncompacted conversations for this agent
            # Using get_uncompacted_turns which is the actual method name
            conversations = await self.memory_manager.get_uncompacted_turns(
                token_limit=compact_input.max_input_tokens
            )

            if not conversations:
                return CompactConversationOutput(
                    agent_id=compact_input.agent_id,
                    title="No conversations to compact",
                    content="No uncompacted conversations found for this agent.",
                    start_conversation_id="none",
                    end_conversation_id="none",
                )

            # Track conversation range
            start_id = conversations[0].id if conversations else "unknown"
            end_id = conversations[-1].id if conversations else "unknown"

            # Format conversations and build prompt
            formatted_convs = self._format_conversations(conversations)
            # TODO: Use when LLM is integrated
            _ = self._build_prompt_with_conversations(compact_input, formatted_convs)

            # TODO: Call LLM with prompt once BaseLLMTool is properly integrated
            # For now, return placeholder
            return CompactConversationOutput(
                agent_id=compact_input.agent_id,
                title="Conversations from "
                + str(conversations[0].timestamp if conversations[0].timestamp else "unknown")
                + " to "
                + str(conversations[-1].timestamp if conversations[-1].timestamp else "unknown"),
                content="Placeholder compaction of "
                + str(len(conversations))
                + " conversation turns",
                start_conversation_id=start_id,
                end_conversation_id=end_id,
            )

        except Exception as e:
            logger.error(f"Error compacting conversations: {str(e)}", exc_info=True)
            return CompactConversationOutput(
                agent_id=compact_input.agent_id,
                title="Error during compaction",
                content=f"Error: {str(e)}",
                start_conversation_id="error",
                end_conversation_id="error",
            )

    def _format_conversations(self, conversations: list[ConversationTurn]) -> str:
        """Format conversation turns for readability."""
        formatted_convs = []
        for conv in conversations:
            # ConversationTurn objects have direct attributes
            timestamp = conv.timestamp
            turn_number = conv.turn_number
            user_query = conv.user_query
            agent_response = conv.agent_response

            # Format as a complete turn
            if timestamp:
                turn_header = (
                    f"[{timestamp}] Turn {turn_number}:" if turn_number else f"[{timestamp}] Turn:"
                )
            else:
                turn_header = f"Turn {turn_number}:" if turn_number else "Turn:"

            formatted = f"{turn_header}\nUser: {user_query}\nAssistant: {agent_response}"
            formatted_convs.append(formatted)

        return "\n\n".join(formatted_convs)

    def _build_prompt_with_conversations(
        self, input_data: CompactConversationInput, formatted_conversations: str
    ) -> str:
        """Build prompt with formatted conversations."""
        prompt = self.instructions
        prompt = prompt.replace("{{CONVERSATIONS}}", formatted_conversations)
        prompt = prompt.replace("{{MAX_OUTPUT_LENGTH}}", str(input_data.max_output_length))
        prompt = prompt.replace("{{AGENT_ID}}", input_data.agent_id)
        return prompt

    def _build_prompt(self, input_data: BaseModel) -> str:
        """This method is not used as we override _execute_impl."""
        return ""

    def _format_display(self, output: BaseModel) -> str:
        """Format compacted conversation for display."""
        # Cast to specific type
        compact_output: CompactConversationOutput = output  # type: ignore[assignment]
        lines = [f"=== {compact_output.title} ==="]
        lines.append(f"Agent: {compact_output.agent_id}")
        lines.append(f"\n{compact_output.content}")
        return "\n".join(lines)


# Long-Term Memory Building Schemas
class BuildLongTermMemoriesInput(BaseModel):
    """Input schema for building long-term memories from compact memories."""

    agent_id: str = Field(..., description="Agent ID to build memories for")
    max_compact_memories: int = Field(
        20, description="Maximum number of unprocessed compact memories to process"
    )


class LongTermMemoryData(BaseModel):
    """Schema for a single long-term memory."""

    id: Optional[str] = Field(
        None, description="Memory ID if updating existing, None if creating new"
    )
    agent_id: str = Field(..., description="Agent ID this memory belongs to")
    title: str = Field(..., description="Brief description of the memory")
    content: str = Field(
        ...,
        description="Full detailed memory including key points, preferences, "
        "user feedback summary, etc.",
    )
    action: str = Field(..., description="Action taken: 'create' or 'update'")


class BuildLongTermMemoriesOutput(BaseModel):
    """Output schema for building long-term memories."""

    memories_created: list[str] = Field(
        default_factory=list, description="IDs of newly created long-term memories"
    )
    memories_updated: list[str] = Field(
        default_factory=list, description="IDs of updated long-term memories"
    )
    start_compact_memory_id: str = Field(
        ..., description="ID of the first compact memory that was processed"
    )
    end_compact_memory_id: str = Field(
        ..., description="ID of the last compact memory that was processed"
    )


# TODO: Design and implement Knowledge Graph extraction and maintenance
# separately from agent memories


class BuildLongTermMemoriesTool(BaseLLMTool):
    """Tool for building long-term memories from compact memories using LLM."""

    def __init__(self, memory_manager: MemoryManager, llm_client: BaseClient):
        instructions = """Analyze compact memories and build/update long-term
memories for the agent.

You will be given:
1. Compact memories to analyze from a specific time range
2. Existing long-term memories that may need updating

Your task:
1. **Analyze the compact memories** for patterns, preferences, and important information
2. **Review existing long-term memories** (if any) for potential updates
3. **Decide for each piece of information** whether to:
   - Update an existing long-term memory (if new info relates to existing content)
   - Create a new long-term memory (if info represents distinct new knowledge)

For MetaAgent memories, focus on:
- General user preferences and working patterns
- Task-agnostic tool usage preferences
- User feedback on task creation and agent interactions
- Communication style preferences
- Overall system usage patterns

For TaskExecutionAgent memories, focus on:
- Task-specific implementation approaches
- User preferences within the task context
- Tool effectiveness for specific task types
- User feedback on task execution
- Lessons learned and optimizations discovered

For each long-term memory, provide:
- **ID**: If updating existing memory, use its ID; if creating new, leave as null
- **Action**: "create" for new memories, "update" for modified existing ones
- **Title**: Brief description that captures the essence
- **Content**: Full detailed memory including:
  - Key points and insights
  - User preferences observed
  - Feedback received and incorporated
  - Patterns identified
  - Recommendations for future interactions

Guidelines for updates:
- **Merge intelligently**: When updating, combine new information with existing content
- **Preserve important details**: Don't lose valuable information from existing memories
- **Avoid duplicates**: If new info is already covered, don't create redundant memories
- **Keep content comprehensive**: Include all relevant details in the content field

Focus on creating memories that will help personalize and improve future agent interactions."""

        super().__init__(
            name="build_long_term_memories",
            description="Builds long-term memories from compact memories for a specific agent",
            input_schema=BuildLongTermMemoriesInput,
            output_schema=BuildLongTermMemoriesOutput,
            instructions=instructions,
            llm_client=llm_client,
            task_type="extraction",
        )
        self.memory_manager = memory_manager

    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """Build long-term memories from unprocessed compact memories."""
        # Cast to specific type
        build_input: BuildLongTermMemoriesInput = input_data  # type: ignore[assignment]
        try:
            # Get unprocessed compact memories for this agent
            # get_unprocessed_compact_memories doesn't take arguments
            compact_memories = await self.memory_manager.get_unprocessed_compact_memories()

            if not compact_memories:
                return BuildLongTermMemoriesOutput(
                    memories_created=[],
                    memories_updated=[],
                    start_compact_memory_id="none",
                    end_compact_memory_id="none",
                )

            # Get existing long-term memories for this agent
            # TODO: Implement get_long_term_memories_by_agent method in MemoryManager
            # For now, return empty list since method doesn't exist
            existing_memories: list[Any] = []
            # existing_memories = await self.memory_manager.get_long_term_memories_by_agent(
            #     agent_id=build_input.agent_id
            # )

            # Track the range of compact memories processed
            start_id = compact_memories[0].id if compact_memories else "unknown"
            end_id = compact_memories[-1].id if compact_memories else "unknown"

            # Format compact memories for LLM
            formatted_compact = self._format_compact_memories(compact_memories)

            # Format existing long-term memories
            formatted_existing = self._format_existing_memories(existing_memories)

            # Build prompt
            _ = self._build_prompt_for_long_term(  # TODO: Use when LLM is integrated
                agent_id=build_input.agent_id,
                compact_memories=formatted_compact,
                existing_memories=formatted_existing,
            )

            # TODO: Call LLM once BaseLLMTool is properly integrated
            # For now, return placeholder
            return BuildLongTermMemoriesOutput(
                memories_created=["placeholder_new_1", "placeholder_new_2"],
                memories_updated=["placeholder_update_1"],
                start_compact_memory_id=start_id,
                end_compact_memory_id=end_id,
            )

        except Exception as e:
            logger.error(f"Error building long-term memories: {str(e)}", exc_info=True)
            return BuildLongTermMemoriesOutput(
                memories_created=[],
                memories_updated=[],
                start_compact_memory_id="error",
                end_compact_memory_id="error",
            )

    def _format_compact_memories(self, compact_memories: list[CompactMemory]) -> str:
        """Format compact memories for LLM processing."""
        formatted = []
        for i, memory in enumerate(compact_memories, 1):
            mem_text = f"Compact Memory {i}:"
            mem_text += f"\n  Summary: {memory.summary}"
            mem_text += f"\n  Key Points: {', '.join(memory.key_points)}"
            mem_text += f"\n  Created: {memory.created_at}"
            mem_text += f"\n  Time Range: {memory.start_time} to {memory.end_time}"
            formatted.append(mem_text)
        return "\n\n".join(formatted)

    def _format_existing_memories(self, existing_memories: list[dict[str, Any]]) -> str:
        """Format existing long-term memories for LLM processing."""
        if not existing_memories:
            return "No existing long-term memories for this agent."

        formatted = []
        for i, memory in enumerate(existing_memories, 1):
            mem_text = f"Memory {i} (ID: {memory.get('id', 'unknown')}):"
            mem_text += f"\n  Title: {memory.get('title', 'N/A')}"
            mem_text += f"\n  Content: {memory.get('content', 'N/A')}"
            formatted.append(mem_text)
        return "\n\n".join(formatted)

    def _build_prompt_for_long_term(
        self, agent_id: str, compact_memories: str, existing_memories: str
    ) -> str:
        """Build prompt for long-term memory extraction."""
        prompt = self.instructions
        prompt = prompt.replace("{{AGENT_ID}}", agent_id)
        prompt += f"\n\nCompact Memories to Process:\n{compact_memories}"
        prompt += f"\n\nExisting Long-Term Memories:\n{existing_memories}"
        return prompt

    def _build_prompt(self, input_data: BaseModel) -> str:
        """This method is not used as we override _execute_impl."""
        return ""

    def _format_display(self, output: BaseModel) -> str:
        """Format long-term memory building results for display."""
        # Cast to specific type
        build_output: BuildLongTermMemoriesOutput = output  # type: ignore[assignment]
        lines = ["=== Long-Term Memory Building Results ==="]
        lines.append(
            f"Compact memories processed: {build_output.start_compact_memory_id} to "
            f"{build_output.end_compact_memory_id}"
        )
        lines.append(f"\nMemories created: {len(build_output.memories_created)}")
        if build_output.memories_created:
            for mem_id in build_output.memories_created[:5]:  # Show first 5
                lines.append(f"  - {mem_id}")
            if len(build_output.memories_created) > 5:
                lines.append(f"  ... and {len(build_output.memories_created) - 5} more")

        lines.append(f"\nMemories updated: {len(build_output.memories_updated)}")
        if build_output.memories_updated:
            for mem_id in build_output.memories_updated[:5]:  # Show first 5
                lines.append(f"  - {mem_id}")
            if len(build_output.memories_updated) > 5:
                lines.append(f"  ... and {len(build_output.memories_updated) - 5} more")

        return "\n".join(lines)
