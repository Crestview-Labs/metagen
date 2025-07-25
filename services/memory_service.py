"""Memory management service that calls core memory tools inline."""

import logging
from typing import Any

from client.base_client import BaseClient
from memory.storage.manager import MemoryManager
from tools.core.memory_tools import (
    BuildLongTermMemoriesInput,
    BuildLongTermMemoriesOutput,
    BuildLongTermMemoriesTool,
    CompactConversationInput,
    CompactConversationOutput,
    CompactConversationTool,
)

logger = logging.getLogger(__name__)


class MemoryManagementService:
    """Service for on-demand memory management operations.

    This service calls the same core tools that agents use for memory operations.
    """

    def __init__(self, memory_manager: MemoryManager, llm_client: BaseClient):
        """Initialize memory management service."""
        self.memory_manager = memory_manager
        self.llm_client = llm_client

        # Initialize tools (same ones agents use)
        self.compact_conversation_tool = CompactConversationTool(memory_manager, llm_client)
        self.build_long_term_memories_tool = BuildLongTermMemoriesTool(memory_manager, llm_client)

    async def compact_conversations(
        self, agent_id: str, max_input_tokens: int = 50000, max_output_length: int = 2000
    ) -> dict[str, Any]:
        """Compact uncompacted conversations for a specific agent.

        Args:
            agent_id: ID of the agent whose conversations to compact
            max_input_tokens: Maximum input tokens to process
            max_output_length: Maximum output length in tokens

        Returns:
            Dictionary with compaction results
        """
        # Call the compact conversation tool
        input_data = CompactConversationInput(
            agent_id=agent_id,
            max_input_tokens=max_input_tokens,
            max_output_length=max_output_length,
        )

        base_result = await self.compact_conversation_tool._execute_impl(input_data)
        # Cast to specific output type
        result = CompactConversationOutput.model_validate(base_result.model_dump())

        # Store the compact memory
        # For now, we'll return the result without storing
        # TODO: Update to match the new store_compact_memory signature
        compact_id = f"compact_{result.start_conversation_id}_{result.end_conversation_id}"

        return {
            "compact_memory_id": compact_id,
            "title": result.title,
            "conversation_range": {
                "start": result.start_conversation_id,
                "end": result.end_conversation_id,
            },
        }

    async def build_long_term_memories(
        self, agent_id: str, max_compact_memories: int = 20
    ) -> dict[str, Any]:
        """Build long-term memories from unprocessed compact memories for an agent.

        Args:
            agent_id: ID of the agent to build memories for
            max_compact_memories: Maximum number of compact memories to process

        Returns:
            Dictionary with memory building results
        """
        # Call the build long-term memories tool
        input_data = BuildLongTermMemoriesInput(
            agent_id=agent_id, max_compact_memories=max_compact_memories
        )

        base_result = await self.build_long_term_memories_tool._execute_impl(input_data)
        # Cast to specific output type
        result = BuildLongTermMemoriesOutput.model_validate(base_result.model_dump())

        return {
            "memories_created": result.memories_created,
            "memories_updated": result.memories_updated,
            "compact_memory_range": {
                "start": result.start_compact_memory_id,
                "end": result.end_compact_memory_id,
            },
        }

    async def get_memory_stats(self, agent_id: str) -> dict[str, Any]:
        """Get memory statistics for an agent.

        Args:
            agent_id: Agent ID to get stats for

        Returns:
            Dictionary with memory statistics
        """
        # Get memory statistics from the manager
        stats = await self.memory_manager.get_agent_memory_stats(agent_id)

        return {
            "agent_id": agent_id,
            "conversation_turns": stats.get("conversation_count", 0),
            "compact_memories": stats.get("compact_count", 0),
            "long_term_memories": stats.get("long_term_count", 0),
            "last_compaction": stats.get("last_compaction", None),
            "last_long_term_build": stats.get("last_long_term_build", None),
        }
