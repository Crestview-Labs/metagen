"""Tests for LLM client factory."""

from unittest.mock import patch

import pytest

from client.anthropic_client import AnthropicClient
from client.factory import LLMClientFactory
from client.gemini_client import GeminiClient
from client.openai_client import OpenAIClient


@pytest.mark.unit
class TestLLMClientFactory:
    """Test LLM client factory functionality."""

    def test_create_anthropic_client(self) -> None:
        """Test creating Anthropic client."""
        factory = LLMClientFactory()

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            client = factory.create_client("anthropic", model="claude-3-sonnet")

            assert isinstance(client, AnthropicClient)
            assert client.default_model == "claude-3-sonnet"

    def test_create_openai_client(self) -> None:
        """Test creating OpenAI client."""
        factory = LLMClientFactory()

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            client = factory.create_client("openai", model="gpt-4")

            assert isinstance(client, OpenAIClient)
            assert client.default_model == "gpt-4"

    def test_create_gemini_client(self) -> None:
        """Test creating Gemini client."""
        factory = LLMClientFactory()

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            client = factory.create_client("gemini", model="gemini-pro")

            assert isinstance(client, GeminiClient)
            assert client.model_name == "gemini-pro"

    def test_invalid_provider(self) -> None:
        """Test error handling for invalid provider."""
        factory = LLMClientFactory()

        with pytest.raises(ValueError) as exc_info:
            factory.create_client("invalid_provider")

        assert "Unknown provider" in str(exc_info.value)

    def test_client_with_api_key(self) -> None:
        """Test creating client with explicit API key."""
        factory = LLMClientFactory()

        # Should not need environment variable when API key is provided
        client = factory.create_client("anthropic", api_key="explicit-key")

        assert isinstance(client, AnthropicClient)
        assert client.api_key == "explicit-key"

    def test_case_insensitive_provider(self) -> None:
        """Test provider names are case insensitive."""
        factory = LLMClientFactory()

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            # Test various cases
            client1 = factory.create_client("ANTHROPIC")
            client2 = factory.create_client("Anthropic")
            client3 = factory.create_client("anthropic")

            assert isinstance(client1, AnthropicClient)
            assert isinstance(client2, AnthropicClient)
            assert isinstance(client3, AnthropicClient)

    def test_provider_aliases(self) -> None:
        """Test provider aliases work correctly."""
        factory = LLMClientFactory()

        with patch.dict(
            "os.environ",
            {
                "ANTHROPIC_API_KEY": "test-key",
                "OPENAI_API_KEY": "test-key",
                "GEMINI_API_KEY": "test-key",
            },
        ):
            # Test common aliases
            claude = factory.create_client("claude")
            assert isinstance(claude, AnthropicClient)

            gpt = factory.create_client("gpt")
            assert isinstance(gpt, OpenAIClient)

            google = factory.create_client("google")
            assert isinstance(google, GeminiClient)
