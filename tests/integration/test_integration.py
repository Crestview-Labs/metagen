"""Integration tests for MetaAgent architecture."""

import logging
import os
import tempfile
from pathlib import Path

import pytest

# Load environment variables from experimental/.env
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from agents.meta_agent import MetaAgent
from client.agentic_client import AgenticClient
from client.models import ModelID
from db.manager import DatabaseManager
from memory.storage.manager import MemoryManager
from memory.storage.sqlite_backend import SQLiteBackend

# Set up test logger
logger = logging.getLogger(__name__)


@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set - skipping integration tests",
)
@pytest.mark.asyncio
class TestMetaAgentIntegration:
    """Integration tests for the MetaAgent architecture."""

    async def test_meta_agent_basic_functionality(self) -> None:
        """Test basic MetaAgent functionality with memory."""
        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        try:
            # Initialize components
            db_manager = DatabaseManager(db_path)
            await db_manager.initialize()
            storage_backend = SQLiteBackend(db_manager)
            await storage_backend.initialize()

            memory_manager = MemoryManager(storage_backend)
            await memory_manager.initialize()

            # Create Agentic client
            agentic_client = AgenticClient(
                llm=ModelID.CLAUDE_SONNET_4, api_key=os.getenv("ANTHROPIC_API_KEY")
            )

            # Create MetaAgent
            meta_agent = MetaAgent(
                agent_id="METAGEN", agentic_client=agentic_client, memory_manager=memory_manager
            )

            # Test basic conversation
            responses = []
            async for event in meta_agent.stream_chat("Hello! Can you help me test the system?"):
                responses.append(event)
                logger.info(f"Agent event: {event}")

            # Verify we got responses
            assert len(responses) > 0

            # Check that we got a final response
            final_responses = [r for r in responses if r.get("stage") == "response"]
            assert len(final_responses) > 0

            # Verify response has content
            final_response = final_responses[-1]
            assert "content" in final_response
            assert isinstance(final_response["content"], str)
            assert len(final_response["content"]) > 0

            logger.info("✅ MetaAgent basic functionality test passed")

        finally:
            # Cleanup
            await memory_manager.close()
            await storage_backend.close()
            await db_manager.close()
            os.unlink(str(db_path))

    async def test_meta_agent_memory_persistence(self) -> None:
        """Test that MetaAgent conversations are persisted in memory."""
        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        try:
            # Initialize components
            db_manager = DatabaseManager(db_path)
            await db_manager.initialize()
            storage_backend = SQLiteBackend(db_manager)
            await storage_backend.initialize()

            memory_manager = MemoryManager(storage_backend)
            await memory_manager.initialize()

            # Create Agentic client
            agentic_client = AgenticClient(
                llm=ModelID.CLAUDE_SONNET_4, api_key=os.getenv("ANTHROPIC_API_KEY")
            )

            # Create MetaAgent
            meta_agent = MetaAgent(
                agent_id="METAGEN", agentic_client=agentic_client, memory_manager=memory_manager
            )

            # Send a message
            test_query = "My name is TestUser and I like pizza"
            responses = []
            async for event in meta_agent.stream_chat(test_query):
                responses.append(event)

            # Verify response
            assert len(responses) > 0

            # Check that conversation was stored in memory
            recent_conversations = await memory_manager.get_recent_conversations(limit=5)
            assert len(recent_conversations) > 0

            # Find our conversation
            our_conversation = None
            for conv in recent_conversations:
                if test_query in conv.user_query:
                    our_conversation = conv
                    break

            assert our_conversation is not None
            assert our_conversation.agent_id == "METAGEN"
            assert test_query in our_conversation.user_query
            assert len(our_conversation.agent_response) > 0

            logger.info("✅ MetaAgent memory persistence test passed")

        finally:
            # Cleanup
            await memory_manager.close()
            await storage_backend.close()
            await db_manager.close()
            os.unlink(str(db_path))


if __name__ == "__main__":
    """Run integration tests manually."""
    import asyncio

    async def run_tests() -> None:
        logger.info("🧪 Running MetaAgent Integration Tests...")
        logger.warning("⚠️  Note: These tests require ANTHROPIC_API_KEY and may incur costs")

        if not os.getenv("ANTHROPIC_API_KEY"):
            logger.warning("❌ No Anthropic API key found. Set ANTHROPIC_API_KEY")
            return

        logger.info("🔑 Anthropic API key found")
        logger.info("🚀 Run with: pytest tests/test_integration.py -v")

    asyncio.run(run_tests())
