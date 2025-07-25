"""Comprehensive tests for StructuredClient with structured output capabilities."""

from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from pydantic import BaseModel, Field

from client.base_client import GenerationResponse, Message, Role
from client.models import STRUCTURED_OUTPUT_MODELS, ModelID, get_structured_output_model
from client.structured_client import StructuredClient


# Test models for structured output
class SimpleResponse(BaseModel):
    """Simple response model for testing."""

    answer: str
    confidence: float = Field(ge=0.0, le=1.0)


class ComplexResponse(BaseModel):
    """Complex response model with nested structures."""

    title: str
    items: list[str]
    metadata: dict
    optional_field: Optional[str] = None


class ExtractedEntity(BaseModel):
    """Model for entity extraction testing."""

    name: str = Field(description="The name of the entity")
    entity_type: str = Field(
        description="The type of entity (e.g., 'landmark', 'person', 'structure')"
    )
    attributes: dict = Field(
        default_factory=dict, description="A dictionary of key attributes of the entity"
    )


class AnalysisResult(BaseModel):
    """Model for analysis results."""

    summary: str
    key_points: list[str]
    sentiment: str = Field(pattern="^(positive|negative|neutral)$")
    confidence_score: float = Field(ge=0.0, le=1.0)


@pytest.mark.unit
@pytest.mark.asyncio
class TestStructuredClientUnit:
    """Unit tests for StructuredClient with mocked dependencies."""

    @pytest_asyncio.fixture
    async def mock_llm_provider(self) -> AsyncMock:
        """Create a mock LLM provider."""
        mock_provider = AsyncMock()
        mock_provider.initialize = AsyncMock()
        mock_provider.generate = AsyncMock()
        mock_provider.generate_structured = AsyncMock()
        mock_provider.close = AsyncMock()
        mock_provider.api_key = "test-api-key"
        return mock_provider

    @pytest_asyncio.fixture
    async def structured_client(self, mock_llm_provider: AsyncMock) -> StructuredClient:
        """Create StructuredClient with mocked provider."""
        # Mock the _create_llm_client method to return our mock
        with patch.object(StructuredClient, "_create_llm_client", return_value=mock_llm_provider):
            # Use default model from STRUCTURED_OUTPUT_MODELS
            client = StructuredClient()
            await client.initialize()
            return client

    async def test_structured_generation(
        self, structured_client: StructuredClient, mock_llm_provider: AsyncMock
    ) -> None:
        """Test basic structured generation."""
        # Mock structured response
        mock_response = SimpleResponse(answer="Paris", confidence=0.95)
        mock_llm_provider.generate_structured.return_value = mock_response

        messages = [Message(role=Role.USER, content="What is the capital of France?")]

        result = await structured_client.generate_structured(
            messages=messages, response_model=SimpleResponse
        )

        assert isinstance(result, SimpleResponse)
        assert result.answer == "Paris"
        assert result.confidence == 0.95
        assert mock_llm_provider.generate_structured.called

    async def test_complex_structured_generation(
        self, structured_client: StructuredClient, mock_llm_provider: AsyncMock
    ) -> None:
        """Test generation with complex nested structures."""
        mock_response = ComplexResponse(
            title="Test Results",
            items=["item1", "item2", "item3"],
            metadata={"key": "value", "count": 3},
            optional_field="optional data",
        )
        mock_llm_provider.generate_structured.return_value = mock_response

        messages = [Message(role=Role.USER, content="Generate a complex response")]

        result = await structured_client.generate_structured(
            messages=messages, response_model=ComplexResponse
        )

        assert isinstance(result, ComplexResponse)
        assert result.title == "Test Results"
        assert len(result.items) == 3
        assert result.metadata["count"] == 3
        assert result.optional_field == "optional data"

    async def test_regular_generation_fallback(
        self, structured_client: StructuredClient, mock_llm_provider: AsyncMock
    ) -> None:
        """Test that regular generation delegates to provider."""
        mock_response = GenerationResponse(content="Regular response")
        mock_llm_provider.generate.return_value = mock_response

        messages = [Message(role=Role.USER, content="Generate regular text")]

        result = await structured_client.generate(messages)

        assert isinstance(result, GenerationResponse)
        assert result.content == "Regular response"
        assert mock_llm_provider.generate.called

    async def test_temperature_and_params(
        self, structured_client: StructuredClient, mock_llm_provider: AsyncMock
    ) -> None:
        """Test parameter passing to structured generation."""
        mock_response = SimpleResponse(answer="Test", confidence=0.8)
        mock_llm_provider.generate_structured.return_value = mock_response

        messages = [Message(role=Role.USER, content="Test with params")]

        await structured_client.generate_structured(
            messages=messages, response_model=SimpleResponse, temperature=0.3, max_tokens=100
        )

        # Check that parameters were passed
        call_args = mock_llm_provider.generate_structured.call_args
        assert call_args[1]["temperature"] == 0.3
        assert call_args[1]["max_tokens"] == 100

    async def test_validation_handling(
        self, structured_client: StructuredClient, mock_llm_provider: AsyncMock
    ) -> None:
        """Test handling of validation in structured models."""
        # This should be handled by the provider, but we test the interface
        mock_response = AnalysisResult(
            summary="Test summary",
            key_points=["point1", "point2"],
            sentiment="positive",
            confidence_score=0.85,
        )
        mock_llm_provider.generate_structured.return_value = mock_response

        messages = [Message(role=Role.USER, content="Analyze this text")]

        result = await structured_client.generate_structured(
            messages=messages, response_model=AnalysisResult
        )

        assert result.sentiment in ["positive", "negative", "neutral"]
        assert 0.0 <= result.confidence_score <= 1.0

    async def test_model_override(
        self, structured_client: StructuredClient, mock_llm_provider: AsyncMock
    ) -> None:
        """Test model override in generation."""
        mock_response = SimpleResponse(answer="Override", confidence=0.9)
        mock_llm_provider.generate_structured.return_value = mock_response

        messages = [Message(role=Role.USER, content="Test override")]

        await structured_client.generate_structured(
            messages=messages, response_model=SimpleResponse, model="custom-model"
        )

        # Check model was passed
        call_args = mock_llm_provider.generate_structured.call_args
        assert call_args[1]["model"] == "custom-model"


@pytest.mark.integration
@pytest.mark.llm
@pytest.mark.asyncio
class TestStructuredClientWithRealLLMs:
    """Integration tests with real LLM providers."""

    def _get_required_key_fixture(self, model_id: ModelID) -> Optional[str]:
        """Get the required fixture name for a given model."""
        if model_id in [ModelID.CLAUDE_OPUS_4, ModelID.CLAUDE_SONNET_4]:
            return "require_anthropic_key"
        elif model_id in [
            ModelID.O3_PRO,
            ModelID.O3,
            ModelID.O4_MINI,
            ModelID.GPT_4O,
            ModelID.GPT_4O_MINI,
        ]:
            return "require_openai_key"
        elif model_id in [ModelID.GEMINI_2_5_PRO, ModelID.GEMINI_2_5_FLASH]:
            return "require_gemini_key"
        else:
            return None

    @pytest.mark.parametrize("model_id", STRUCTURED_OUTPUT_MODELS)
    async def test_structured_extraction(
        self, request: pytest.FixtureRequest, model_id: ModelID
    ) -> None:
        """Test structured extraction with all structured output models."""
        fixture_name = self._get_required_key_fixture(model_id)
        if fixture_name:
            request.getfixturevalue(fixture_name)

        client = StructuredClient(model=model_id)
        await client.initialize()

        try:
            messages = [
                Message(
                    role=Role.USER,
                    content=(
                        "Extract information: The Eiffel Tower is a wrought-iron "
                        "lattice tower in Paris, France. It is 330 meters tall."
                    ),
                )
            ]

            result = await client.generate_structured(
                messages=messages, response_model=ExtractedEntity
            )

            assert isinstance(result, ExtractedEntity)
            assert "eiffel" in result.name.lower() or "tower" in result.name.lower()
            assert result.entity_type  # Should identify as landmark/structure
            assert isinstance(result.attributes, dict)
            # Attributes may be empty or contain extracted data - both are valid
        finally:
            await client.close()

    @pytest.mark.parametrize("model_id", STRUCTURED_OUTPUT_MODELS)
    async def test_analysis_with_constraints(
        self, request: pytest.FixtureRequest, model_id: ModelID
    ) -> None:
        """Test analysis with field constraints."""
        fixture_name = self._get_required_key_fixture(model_id)
        if fixture_name:
            request.getfixturevalue(fixture_name)

        client = StructuredClient(model=model_id)
        await client.initialize()

        try:
            messages = [
                Message(
                    role=Role.USER,
                    content=(
                        "Analyze this text: 'The product is excellent and "
                        "exceeded all my expectations. Highly recommend!'"
                    ),
                )
            ]

            result = await client.generate_structured(
                messages=messages, response_model=AnalysisResult
            )

            assert isinstance(result, AnalysisResult)
            assert result.sentiment in ["positive", "negative", "neutral"]
            assert result.sentiment == "positive"  # Should detect positive sentiment
            assert 0.0 <= result.confidence_score <= 1.0
            assert len(result.key_points) > 0
            assert len(result.summary) > 0
        finally:
            await client.close()

    @pytest.mark.parametrize("model_id", STRUCTURED_OUTPUT_MODELS[:2])  # Test first 2 to save time
    async def test_complex_nested_extraction(
        self, request: pytest.FixtureRequest, model_id: ModelID
    ) -> None:
        """Test extraction with complex nested structures."""
        fixture_name = self._get_required_key_fixture(model_id)
        if fixture_name:
            request.getfixturevalue(fixture_name)

        class ProductReview(BaseModel):
            product_name: str
            rating: float = Field(ge=1.0, le=5.0)
            pros: list[str]
            cons: list[str]
            recommendation: bool

        client = StructuredClient(model=model_id)
        await client.initialize()

        try:
            messages = [
                Message(
                    role=Role.USER,
                    content="""Review: The iPhone 15 Pro is amazing! 
                Pros: Great camera, fast processor, beautiful display
                Cons: Expensive, battery life could be better
                Overall: 4.5/5 stars, definitely recommend""",
                )
            ]

            result = await client.generate_structured(
                messages=messages, response_model=ProductReview
            )

            assert isinstance(result, ProductReview)
            assert "iphone" in result.product_name.lower()
            assert 1.0 <= result.rating <= 5.0
            assert len(result.pros) >= 2
            assert len(result.cons) >= 1
            assert result.recommendation is True
        finally:
            await client.close()

    async def test_cross_model_consistency(self, require_all_llm_keys: None) -> None:
        """Test consistency across different structured output models."""
        test_content = (
            "The meeting is scheduled for Monday, January 15, 2024 at 2:30 PM in Conference Room A"
        )

        class MeetingInfo(BaseModel):
            date: str
            time: str
            location: str

        results = []
        for model_id in STRUCTURED_OUTPUT_MODELS[:3]:  # Test first 3 models
            client = StructuredClient(model=model_id)
            await client.initialize()

            try:
                messages = [
                    Message(role=Role.USER, content=f"Extract meeting details: {test_content}")
                ]
                result = await client.generate_structured(
                    messages=messages, response_model=MeetingInfo
                )
                results.append((model_id.name, result))
            finally:
                await client.close()

        # All models should extract similar information
        for model_name, result in results:
            assert isinstance(result, MeetingInfo), f"{model_name} failed to return MeetingInfo"
            assert "january" in result.date.lower() or "15" in result.date
            assert "2:30" in result.time or "14:30" in result.time
            assert "conference" in result.location.lower() or "room a" in result.location.lower()

    async def test_list_extraction(self, require_anthropic_key: None) -> None:
        """Test extraction of lists with structured output."""

        class TaskList(BaseModel):
            tasks: list[str]
            priority_level: str
            estimated_hours: float

        client = StructuredClient(model=STRUCTURED_OUTPUT_MODELS[0])
        await client.initialize()

        try:
            messages = [
                Message(
                    role=Role.USER,
                    content="""Extract tasks from: "For the project we need to:
                1. Design the database schema
                2. Implement the API endpoints  
                3. Write unit tests
                4. Deploy to staging
                This is high priority and will take about 40 hours total.""",
                )
            ]

            result = await client.generate_structured(messages=messages, response_model=TaskList)

            assert isinstance(result, TaskList)
            assert len(result.tasks) >= 4
            assert "high" in result.priority_level.lower()
            assert result.estimated_hours > 0
        finally:
            await client.close()

    async def test_model_selection_helper(self) -> None:
        """Test model selection for structured output."""
        # Get best model for structured output with constraints
        model = get_structured_output_model(
            min_context_window=100000, require_json_mode=True, max_cost_per_1k_output=0.01
        )

        # Should return a valid model from STRUCTURED_OUTPUT_MODELS
        assert any(model.model_id == m.value for m in STRUCTURED_OUTPUT_MODELS)
        assert model.context_window >= 100000
        from client.models import ModelCapability

        assert ModelCapability.JSON_MODE in model.capabilities

    @pytest.mark.parametrize("model_id", STRUCTURED_OUTPUT_MODELS[:2])
    async def test_low_temperature_consistency(
        self, request: pytest.FixtureRequest, model_id: ModelID
    ) -> None:
        """Test that low temperature produces consistent structured outputs."""
        fixture_name = self._get_required_key_fixture(model_id)
        if fixture_name:
            request.getfixturevalue(fixture_name)

        client = StructuredClient(model=model_id)
        await client.initialize()

        try:
            messages = [
                Message(
                    role=Role.USER,
                    content="Is Python a programming language? Answer yes or no with confidence.",
                )
            ]

            # Run multiple times with low temperature
            results = []
            for _ in range(3):
                result = await client.generate_structured(
                    messages=messages,
                    response_model=SimpleResponse,
                    temperature=0.1,  # Low temperature for consistency
                )
                results.append(result)

            # All results should be similar
            answers = [r.answer.lower() for r in results]
            assert all("yes" in ans or "true" in ans for ans in answers)

            # Confidence should be high and consistent
            confidences = [r.confidence for r in results]
            assert all(c > 0.8 for c in confidences)
        finally:
            await client.close()
