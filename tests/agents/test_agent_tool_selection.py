"""Tests for agent tool selection and usage patterns.

This module tests how agents select appropriate tools for tasks,
chain multiple tools, and handle tool approval flows.
"""

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from pydantic import BaseModel, Field

from agents.memory import MemoryManager
from agents.meta_agent import MetaAgent
from client.models import ModelID
from common.messages import (
    AgentMessage,
    ThinkingMessage,
    ToolResultMessage,
    ToolStartedMessage,
    UserMessage,
)
from tools.base import BaseCoreTool
from tools.registry import get_tool_executor, get_tool_registry


class CalculatorInput(BaseModel):
    """Input for calculator tool."""

    expression: str = Field(description="Mathematical expression to evaluate")


class CalculatorOutput(BaseModel):
    """Output for calculator tool."""

    result: float
    expression: str


class CalculatorTool(BaseCoreTool):
    """Simple calculator tool for testing."""

    def __init__(self) -> None:
        super().__init__(
            name="calculator",
            description="Perform basic arithmetic calculations",
            input_schema=CalculatorInput,
            output_schema=CalculatorOutput,
        )

    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """Execute calculation."""
        # Cast to specific type
        assert isinstance(input_data, CalculatorInput)
        calc_input: CalculatorInput = input_data
        try:
            # Simple eval for testing (don't do this in production!)
            result = eval(calc_input.expression, {"__builtins__": {}}, {})
            return CalculatorOutput(result=float(result), expression=calc_input.expression)
        except Exception as e:
            raise RuntimeError(f"Calculation error: {str(e)}")


class WeatherInput(BaseModel):
    """Input for weather tool."""

    location: str = Field(description="Location to get weather for")


class WeatherOutput(BaseModel):
    """Output for weather tool."""

    location: str
    temperature: int
    condition: str


class WeatherTool(BaseCoreTool):
    """Mock weather tool for testing."""

    def __init__(self) -> None:
        super().__init__(
            name="get_weather",
            description="Get current weather for a location",
            input_schema=WeatherInput,
            output_schema=WeatherOutput,
        )

    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """Return mock weather data."""
        # Cast to specific type
        assert isinstance(input_data, WeatherInput)
        weather_input: WeatherInput = input_data
        return WeatherOutput(location=weather_input.location, temperature=72, condition="sunny")


class SearchInput(BaseModel):
    """Input for search tool."""

    query: str = Field(description="Search query")


class SearchOutput(BaseModel):
    """Output for search tool."""

    query: str
    results: list[str]
    num_results: int


class SearchTool(BaseCoreTool):
    """Mock search tool for testing."""

    def __init__(self) -> None:
        super().__init__(
            name="web_search",
            description="Search the web for information",
            input_schema=SearchInput,
            output_schema=SearchOutput,
        )

    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """Return mock search results."""
        # Cast to specific type
        assert isinstance(input_data, SearchInput)
        search_input: SearchInput = input_data
        return SearchOutput(
            query=search_input.query, results=["Result 1", "Result 2", "Result 3"], num_results=3
        )


@pytest.mark.integration
@pytest.mark.llm
class TestAgentToolSelection:
    """Test how agents select and use tools."""

    # Use memory_manager fixture from conftest.py

    @pytest_asyncio.fixture
    async def agent_with_tools(
        self, memory_manager: MemoryManager
    ) -> AsyncGenerator[MetaAgent, None]:
        """Create MetaAgent with test tools."""
        # Register test tools
        executor = get_tool_executor()
        registry = get_tool_registry()

        executor.register_core_tool(CalculatorTool())
        executor.register_core_tool(WeatherTool())
        executor.register_core_tool(SearchTool())

        # Get available Tool schemas from registry's executor
        available_tools = []
        for tool_name, tool in registry.executor.core_tools.items():
            if tool_name not in registry.disabled_tools:
                available_tools.append(tool.get_tool_schema())

        # Create MetaAgent
        agent = MetaAgent(
            agent_id="test-meta-agent",
            memory_manager=memory_manager,
            llm_config={
                "llm": ModelID.CLAUDE_SONNET_4,
                "api_key": os.getenv("ANTHROPIC_API_KEY"),
                "max_iterations": 10,
                "max_tools_per_turn": 50,
            },
            available_tools=available_tools,
        )
        # Enable tool result display for testing
        agent.show_tool_results = True

        await agent.initialize()

        yield agent

        # Cleanup: Remove registered tools to avoid state pollution
        executor.core_tools.clear()

    async def test_agent_selects_appropriate_tool(self, agent_with_tools: MetaAgent) -> None:
        """Test agent selects the right tool for the task."""
        response = ""
        tools_used = []
        tool_results = []
        all_messages = []

        user_message = UserMessage(session_id="test-session", content="What's 25 multiplied by 4?")
        async for message in agent_with_tools.stream_chat(user_message):
            all_messages.append(message)
            if isinstance(message, ToolStartedMessage):
                tools_used.append(message.tool_name)
            elif isinstance(message, ToolResultMessage):
                tool_results.append(message.result)
            elif isinstance(message, AgentMessage):
                # Capture the agent's response
                response = message.content

        # Should use calculator tool
        assert "calculator" in tools_used
        # Debug: print what we actually got
        # Check in tool results or response
        assert "100" in response or any("100" in str(r) for r in tool_results)

    async def test_agent_chains_multiple_tools(self, agent_with_tools: MetaAgent) -> None:
        """Test agent can chain multiple tools for complex tasks."""
        response = ""
        tools_used = []

        user_message = UserMessage(
            session_id="test-session",
            content="Search for the current temperature in Paris, "
            "then convert it from Celsius to Fahrenheit",
        )
        async for message in agent_with_tools.stream_chat(user_message):
            if isinstance(message, ToolStartedMessage):
                tools_used.append(message.tool_name)
            elif isinstance(message, AgentMessage):
                response = message.content

        # Should use search tool (or would use weather tool if it knew)
        # Might use calculator for conversion
        assert len(tools_used) >= 1

        # Response should mention temperature/weather
        assert any(word in response.lower() for word in ["temperature", "weather", "degrees"])

    async def test_agent_handles_tool_not_available(self, agent_with_tools: MetaAgent) -> None:
        """Test agent handles requests for unavailable tools gracefully."""
        response = ""

        user_message = UserMessage(
            session_id="test-session", content="Send an email to john@example.com"
        )
        async for message in agent_with_tools.stream_chat(user_message):
            if isinstance(message, AgentMessage):
                response += message.content

        # Should explain it can't send emails
        assert any(
            phrase in response.lower()
            for phrase in ["can't send", "cannot send", "don't have", "not available", "unable"]
        )

    async def test_agent_uses_multiple_tools_appropriately(
        self, agent_with_tools: MetaAgent
    ) -> None:
        """Test agent uses different tools for different parts of request."""
        response = ""
        tools_used = []

        user_message = UserMessage(
            session_id="test-session",
            content="What's the weather in New York and what's 15% of 80?",
        )
        async for message in agent_with_tools.stream_chat(user_message):
            if isinstance(message, ToolStartedMessage):
                tools_used.append(message.tool_name)
            elif isinstance(message, AgentMessage):
                response += message.content

        # Should use weather tool and calculator
        assert "get_weather" in tools_used
        assert "calculator" in tools_used

        # Should have both results
        assert "new york" in response.lower()
        # Agent might express result as 12 or in other ways (e.g., "twelve", "15% of 80 is 12", etc)
        assert any(term in response.lower() for term in ["12", "twelve", "15% of 80"])

    async def test_agent_explains_tool_usage(self, agent_with_tools: MetaAgent) -> None:
        """Test agent explains what tools it's using."""
        response = ""
        has_thinking = False

        user_message = UserMessage(
            session_id="test-session", content="Calculate the sum of 1 through 10"
        )
        async for message in agent_with_tools.stream_chat(user_message):
            if isinstance(message, ThinkingMessage):
                has_thinking = True
            elif isinstance(message, AgentMessage):
                response += message.content

        # Agent should think about the task
        assert has_thinking

        # Should calculate the sum (55)
        assert "55" in response

    async def test_agent_tool_error_recovery(self, agent_with_tools: MetaAgent) -> None:
        """Test agent recovers from tool errors."""
        response = ""

        user_message = UserMessage(
            session_id="test-session", content="Calculate the result of 'invalid expression'"
        )
        async for message in agent_with_tools.stream_chat(user_message):
            if isinstance(message, AgentMessage):
                response += message.content

        # Should handle the error gracefully
        assert any(
            word in response.lower()
            for word in ["error", "invalid", "couldn't", "failed", "problem"]
        )

    async def test_agent_tool_selection_reasoning(self, agent_with_tools: MetaAgent) -> None:
        """Test agent reasons about tool selection."""
        response = ""
        tools_used = []

        user_message = UserMessage(
            session_id="test-session",
            content="I need to know about quantum physics. Should I search for it?",
        )
        async for message in agent_with_tools.stream_chat(user_message):
            if isinstance(message, ToolStartedMessage):
                tools_used.append(message.tool_name)
            elif isinstance(message, AgentMessage):
                response += message.content

        # Might use search tool or explain it would search
        if "web_search" in tools_used:
            assert "quantum physics" in response.lower()
        else:
            # Should at least discuss searching
            assert "search" in response.lower()
