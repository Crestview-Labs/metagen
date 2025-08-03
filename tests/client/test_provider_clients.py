"""Tests for provider clients (Anthropic, OpenAI, Gemini)."""

import asyncio
import os
from enum import Enum
from typing import Any

import pytest
import pytest_asyncio
from pydantic import BaseModel, Field

from client.anthropic_client import AnthropicClient
from client.base_provider_client import BaseProviderClient
from client.gemini_client import GeminiClient
from client.llm_client import LLMClient
from client.models import REASONING_MODELS, STRUCTURED_OUTPUT_MODELS, ModelID, get_model
from client.openai_client import OpenAIClient
from client.types import LLMMessage, LLMMessageRole, LLMStreamEventType


# Test models for structured output
class SimpleResponse(BaseModel):
    """Simple response model for testing structured output."""

    answer: str
    confidence: float = Field(ge=0.0, le=1.0)


class EntityType(str, Enum):
    """Types of entities that can be extracted."""

    LANDMARK = "landmark"
    STRUCTURE = "structure"
    BUILDING = "building"
    MONUMENT = "monument"
    TOWER = "tower"
    PERSON = "person"
    PLACE = "place"
    ORGANIZATION = "organization"


class ExtractedEntity(BaseModel):
    """Model for entity extraction testing."""

    name: str = Field(description="The name of the entity")
    entity_type: EntityType = Field(description="The type of entity")
    attributes: dict = Field(default_factory=dict)


@pytest.fixture
def api_keys() -> dict[str, str]:
    """Get API keys for testing."""
    return {
        "anthropic": os.getenv("ANTHROPIC_API_KEY", "test-anthropic-key"),
        "openai": os.getenv("OPENAI_API_KEY", "test-openai-key"),
        "gemini": os.getenv("GEMINI_API_KEY", "test-gemini-key"),
    }


@pytest_asyncio.fixture
async def get_provider_client(api_keys: dict[str, str]) -> Any:
    """Factory to create provider clients for testing."""
    clients = []

    async def _create_client(model_id: ModelID) -> BaseProviderClient:
        """Create a provider client for the given model."""
        # Create LLMClient to get the provider client
        llm_client = LLMClient(model=model_id)
        client = llm_client.provider
        await client.initialize()
        clients.append(client)
        return client

    yield _create_client

    # Cleanup
    for client in clients:
        try:
            await client.close()
        except Exception:
            # Ignore errors during cleanup - this can happen if the event loop is closing
            pass

    # Give a small delay to allow httpx to finish cleanup
    await asyncio.sleep(0.1)


@pytest.mark.unit
class TestProviderClients:
    """Unit tests for provider clients."""

    def test_provider_client_creation(self, api_keys: dict[str, str]) -> None:
        """Test that we can create each type of provider client."""
        anthropic = AnthropicClient(api_key=api_keys["anthropic"])
        assert anthropic.api_key == api_keys["anthropic"]
        assert anthropic.name == "Anthropic"

        openai = OpenAIClient(api_key=api_keys["openai"])
        assert openai.api_key == api_keys["openai"]
        assert openai.name == "OpenAI"

        gemini = GeminiClient(api_key=api_keys["gemini"])
        assert gemini.api_key == api_keys["gemini"]
        assert "Gemini" in gemini.name

    def test_message_conversion_basic(self) -> None:
        """Test basic message conversion for each provider."""
        messages = [
            LLMMessage(role=LLMMessageRole.USER, content="Hello"),
            LLMMessage(role=LLMMessageRole.ASSISTANT, content="Hi there!"),
        ]

        # Anthropic
        anthropic = AnthropicClient(api_key="test-key")
        anthropic_msgs = anthropic._convert_messages_to_anthropic(messages)
        assert len(anthropic_msgs) == 2
        assert anthropic_msgs[0]["role"] == "user"
        assert anthropic_msgs[1]["role"] == "assistant"

        # OpenAI
        openai = OpenAIClient(api_key="test-key")
        openai_msgs = openai._convert_messages_to_openai(messages)
        assert len(openai_msgs) == 2
        assert openai_msgs[0]["role"] == "user"
        assert openai_msgs[1]["role"] == "assistant"

        # Gemini
        gemini = GeminiClient(api_key="test-key")
        gemini_msgs = gemini._convert_messages_to_gemini_format(messages)
        assert len(gemini_msgs) == 2
        assert gemini_msgs[0]["role"] == "user"
        assert gemini_msgs[1]["role"] == "model"  # Gemini uses "model" instead of "assistant"


@pytest.mark.integration
@pytest.mark.asyncio
class TestProviderClientsIntegration:
    """Integration tests with real provider APIs."""

    @pytest.mark.parametrize("model_id", REASONING_MODELS)
    @pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY")
        and not os.getenv("OPENAI_API_KEY")
        and not os.getenv("GEMINI_API_KEY"),
        reason="No API keys found for integration tests",
    )
    async def test_generate_basic(self, model_id: ModelID, get_provider_client: Any) -> None:
        """Test basic generation with all reasoning models."""
        # Skip specific models that might not be available
        if model_id == ModelID.O3_PRO:
            pytest.skip("O3_PRO requires special access")

        # Get the provider for this model
        model_info = get_model(model_id.value)
        provider_name = model_info.provider.value.upper()

        # Skip if no API key for this provider
        if not os.getenv(f"{provider_name}_API_KEY"):
            if provider_name == "GOOGLE":
                provider_name = "GEMINI"
            if not os.getenv(f"{provider_name}_API_KEY"):
                pytest.skip(f"No API key for {provider_name}")

        # Create provider client
        client = await get_provider_client(model_id)

        # Test generation
        # O3 works better with simple, direct prompts
        if "o3" in model_id.value.lower():
            messages = [LLMMessage(role=LLMMessageRole.USER, content="What is 2+2?")]
        else:
            messages = [
                LLMMessage(
                    role=LLMMessageRole.USER, content="Respond with exactly: 'Hello from testing'"
                )
            ]

        response = await client.generate(
            messages=messages,
            temperature=0.0,  # For deterministic output
            max_tokens=4096,
        )

        assert isinstance(response, LLMMessage)
        assert response.content is not None
        assert len(response.content) > 0

        # Check for expected content based on model type
        if "o3" in model_id.value.lower():
            # O3 should answer the math question
            assert "4" in response.content or "four" in response.content.lower()
        else:
            # Other models should follow the exact instruction
            assert "hello" in response.content.lower()

        # Verify usage data
        if response.usage:  # Some providers might not always return usage
            assert response.usage.input_tokens > 0
            assert response.usage.output_tokens > 0
            assert response.usage.total_tokens > 0

    @pytest.mark.parametrize("model_id", STRUCTURED_OUTPUT_MODELS)
    @pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY")
        and not os.getenv("OPENAI_API_KEY")
        and not os.getenv("GEMINI_API_KEY"),
        reason="No API keys found for integration tests",
    )
    async def test_generate_structured(self, model_id: ModelID, get_provider_client: Any) -> None:
        """Test structured output generation with all structured output models."""
        # Get the provider for this model
        model_info = get_model(model_id.value)
        provider_name = model_info.provider.value.upper()

        # Skip if no API key for this provider
        if not os.getenv(f"{provider_name}_API_KEY"):
            if provider_name == "GOOGLE":
                provider_name = "GEMINI"
            if not os.getenv(f"{provider_name}_API_KEY"):
                pytest.skip(f"No API key for {provider_name}")

        # Create provider client
        client = await get_provider_client(model_id)

        # Test structured generation
        messages = [
            LLMMessage(
                role=LLMMessageRole.USER,
                content="What is the capital of France? Answer with high confidence.",
            )
        ]

        result = await client.generate_structured(
            messages=messages, response_model=SimpleResponse, temperature=0.0
        )

        assert isinstance(result, SimpleResponse)
        assert "paris" in result.answer.lower()
        assert result.confidence >= 0.8  # Should be high confidence

    @pytest.mark.parametrize("model_id", STRUCTURED_OUTPUT_MODELS)
    async def test_generate_structured_complex(
        self, model_id: ModelID, get_provider_client: Any
    ) -> None:
        """Test complex structured output with entity extraction."""
        # Get the provider for this model
        model_info = get_model(model_id.value)
        provider_name = model_info.provider.value.upper()

        # Skip if no API key for this provider
        if not os.getenv(f"{provider_name}_API_KEY"):
            if provider_name == "GOOGLE":
                provider_name = "GEMINI"
            if not os.getenv(f"{provider_name}_API_KEY"):
                pytest.skip(f"No API key for {provider_name}")

        # Create provider client
        client = await get_provider_client(model_id)

        # Test entity extraction
        messages = [
            LLMMessage(
                role=LLMMessageRole.USER,
                content="Extract entity: The Eiffel Tower is a 330-meter tall "
                "iron lattice tower in Paris, France.",
            )
        ]

        result = await client.generate_structured(
            messages=messages, response_model=ExtractedEntity, temperature=0.0
        )

        assert isinstance(result, ExtractedEntity)
        assert "eiffel" in result.name.lower() or "tower" in result.name.lower()
        assert isinstance(result.entity_type, EntityType)
        # The Eiffel Tower could be classified as any of these
        assert result.entity_type in [
            EntityType.LANDMARK,
            EntityType.STRUCTURE,
            EntityType.BUILDING,
            EntityType.MONUMENT,
            EntityType.TOWER,
        ]
        # Attributes extraction is optional - models may or may not populate it
        # The important part is that the entity was correctly identified

    @pytest.mark.parametrize("model_id", REASONING_MODELS)
    async def test_streaming(self, model_id: ModelID, get_provider_client: Any) -> None:
        """Test streaming functionality."""
        # Skip specific models that might not be available
        if model_id == ModelID.O3_PRO:
            pytest.skip("O3_PRO requires special access")

        # Get the provider for this model
        model_info = get_model(model_id.value)
        provider_name = model_info.provider.value.upper()

        # Skip if no API key for this provider
        if not os.getenv(f"{provider_name}_API_KEY"):
            if provider_name == "GOOGLE":
                provider_name = "GEMINI"
            if not os.getenv(f"{provider_name}_API_KEY"):
                pytest.skip(f"No API key for {provider_name}")

        # Skip Gemini for now as streaming is not implemented
        if "gemini" in model_id.value.lower():
            pytest.skip("Gemini streaming not yet implemented")

        # Create provider client
        client = await get_provider_client(model_id)

        # Test streaming
        messages = [LLMMessage(role=LLMMessageRole.USER, content="Count from 1 to 5")]

        chunks = []
        async for event in await client.generate(messages=messages, stream=True, max_tokens=100):
            chunks.append(event)

        assert len(chunks) > 0
        # Should have received multiple chunks
        content_chunks = [c for c in chunks if c.type == LLMStreamEventType.CONTENT]
        assert len(content_chunks) > 1  # Streaming should produce multiple chunks
