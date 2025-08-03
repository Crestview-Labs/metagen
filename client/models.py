"""LLM Model Registry - Latest models as of June 2025."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ModelProvider(str, Enum):
    """Supported LLM providers."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"


class ModelID(str, Enum):
    """Model identifiers without version dates."""

    # Anthropic
    CLAUDE_OPUS_4 = "claude-opus-4-20250514"
    CLAUDE_SONNET_4 = "claude-sonnet-4-20250514"

    # OpenAI
    O3_PRO = "o3-pro"
    O3 = "o3"
    O4_MINI = "o4-mini"
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"

    # Google
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"


class ModelCapability(str, Enum):
    """Model capabilities."""

    # Core capabilities
    REASONING = "reasoning"  # Advanced reasoning and problem-solving
    EXTENDED_THINKING = "extended_thinking"  # Can show thinking process
    TOOL_USE = "tool_use"  # Function calling / tool use
    PARALLEL_TOOLS = "parallel_tools"  # Can execute multiple tools in parallel
    STRUCTURED_OUTPUT = "structured_output"  # Structured data extraction
    JSON_MODE = "json_mode"  # Supports JSON response format
    VISION = "vision"  # Image understanding
    AUDIO_INPUT = "audio_input"  # Audio understanding
    AUDIO_OUTPUT = "audio_output"  # Audio generation
    IMAGE_GENERATION = "image_generation"  # Can create images
    REAL_TIME = "real_time"  # Live/streaming interactions
    LONG_CONTEXT = "long_context"  # 100k+ tokens


@dataclass
class ModelInfo:
    """Information about an LLM model."""

    provider: ModelProvider
    model_id: str
    display_name: str
    description: str
    context_window: int
    max_output_tokens: Optional[int] = None
    cost_per_1k_input: Optional[float] = None  # USD
    cost_per_1k_output: Optional[float] = None  # USD
    supports_tools: bool = True
    supports_vision: bool = False
    supports_streaming: bool = True
    knowledge_cutoff: Optional[str] = None
    capabilities: list[ModelCapability] = field(default_factory=list)
    recommended_use_cases: list[str] = field(default_factory=list)

    @property
    def full_id(self) -> str:
        """Get the full model identifier including provider."""
        return f"{self.provider.value}/{self.model_id}"


# Model Registry - Latest models only (June 2025)
MODELS = {
    # Anthropic Claude 4 Models
    ModelID.CLAUDE_OPUS_4.value: ModelInfo(
        provider=ModelProvider.ANTHROPIC,
        model_id=ModelID.CLAUDE_OPUS_4.value,
        display_name="Claude Opus 4",
        description="Most powerful Claude model for complex tasks, best for coding",
        context_window=200000,
        max_output_tokens=8192,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.075,
        supports_vision=True,
        knowledge_cutoff="2024-11",
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.EXTENDED_THINKING,
            ModelCapability.TOOL_USE,
            ModelCapability.PARALLEL_TOOLS,
            ModelCapability.VISION,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.JSON_MODE,
            ModelCapability.LONG_CONTEXT,
        ],
        recommended_use_cases=["complex_reasoning", "code_generation", "agent_workflows"],
    ),
    ModelID.CLAUDE_SONNET_4.value: ModelInfo(
        provider=ModelProvider.ANTHROPIC,
        model_id=ModelID.CLAUDE_SONNET_4.value,
        display_name="Claude Sonnet 4",
        description="Balanced Claude 4 model for most tasks",
        context_window=200000,
        max_output_tokens=64000,  # Supports up to 64K output tokens
        cost_per_1k_input=0.003,
        cost_per_1k_output=0.015,
        supports_vision=True,
        knowledge_cutoff="2024-11",
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.EXTENDED_THINKING,
            ModelCapability.TOOL_USE,
            ModelCapability.PARALLEL_TOOLS,
            ModelCapability.VISION,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.JSON_MODE,
            ModelCapability.LONG_CONTEXT,
        ],
        recommended_use_cases=["general_tasks", "code_review", "structured_extraction"],
    ),
    # OpenAI O-series Models
    ModelID.O3_PRO.value: ModelInfo(
        provider=ModelProvider.OPENAI,
        model_id=ModelID.O3_PRO.value,
        display_name="O3 Pro",
        description="Most capable OpenAI reasoning model, designed for reliability",
        context_window=200000,
        max_output_tokens=100000,
        cost_per_1k_input=0.150,
        cost_per_1k_output=0.600,
        supports_tools=True,  # Corrected: O3 supports tools
        supports_streaming=True,  # Corrected: O3 supports streaming
        knowledge_cutoff="2024-10",
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.EXTENDED_THINKING,
            ModelCapability.TOOL_USE,
            ModelCapability.PARALLEL_TOOLS,
            ModelCapability.VISION,
            ModelCapability.IMAGE_GENERATION,
            ModelCapability.JSON_MODE,
            ModelCapability.LONG_CONTEXT,
        ],
        recommended_use_cases=["complex_reasoning", "multi_step_problems", "reliability_critical"],
    ),
    ModelID.O3.value: ModelInfo(
        provider=ModelProvider.OPENAI,
        model_id=ModelID.O3.value,
        display_name="O3",
        description="Advanced reasoning model with tool use",
        context_window=200000,
        max_output_tokens=100000,
        cost_per_1k_input=0.015,
        cost_per_1k_output=0.060,
        supports_tools=True,  # Corrected: O3 supports tools
        supports_streaming=True,  # Corrected: O3 supports streaming
        knowledge_cutoff="2024-10",
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.EXTENDED_THINKING,
            ModelCapability.TOOL_USE,
            ModelCapability.PARALLEL_TOOLS,
            ModelCapability.VISION,
            ModelCapability.IMAGE_GENERATION,
            ModelCapability.JSON_MODE,
            ModelCapability.LONG_CONTEXT,
        ],
        recommended_use_cases=["reasoning", "analysis", "tool_orchestration"],
    ),
    ModelID.O4_MINI.value: ModelInfo(
        provider=ModelProvider.OPENAI,
        model_id=ModelID.O4_MINI.value,
        display_name="O4 Mini",
        description="Fast reasoning model for STEM tasks, high-volume applications",
        context_window=128000,
        max_output_tokens=65536,
        cost_per_1k_input=0.00055,
        cost_per_1k_output=0.0044,
        supports_tools=True,  # Corrected: O4-mini supports tools
        supports_streaming=True,  # Corrected: O4-mini supports streaming
        knowledge_cutoff="2024-10",
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.TOOL_USE,
            ModelCapability.PARALLEL_TOOLS,
            ModelCapability.VISION,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.JSON_MODE,
        ],
        recommended_use_cases=["math", "coding", "high_volume_tasks"],
    ),
    # OpenAI GPT Models
    ModelID.GPT_4O.value: ModelInfo(
        provider=ModelProvider.OPENAI,
        model_id=ModelID.GPT_4O.value,
        display_name="GPT-4o",
        description="Multimodal GPT-4 Omni model",
        context_window=128000,
        max_output_tokens=16384,
        cost_per_1k_input=0.0025,
        cost_per_1k_output=0.01,
        supports_vision=True,
        knowledge_cutoff="2024-10",
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.TOOL_USE,
            ModelCapability.PARALLEL_TOOLS,
            ModelCapability.VISION,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.JSON_MODE,
            ModelCapability.AUDIO_INPUT,
            ModelCapability.AUDIO_OUTPUT,
        ],
        recommended_use_cases=["multimodal_tasks", "structured_extraction", "general_purpose"],
    ),
    ModelID.GPT_4O_MINI.value: ModelInfo(
        provider=ModelProvider.OPENAI,
        model_id=ModelID.GPT_4O_MINI.value,
        display_name="GPT-4o Mini",
        description="Small, affordable multimodal model",
        context_window=128000,
        max_output_tokens=16384,
        cost_per_1k_input=0.00015,
        cost_per_1k_output=0.0006,
        supports_vision=True,
        knowledge_cutoff="2024-10",
        capabilities=[
            ModelCapability.TOOL_USE,
            ModelCapability.PARALLEL_TOOLS,
            ModelCapability.VISION,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.JSON_MODE,
        ],
        recommended_use_cases=["high_volume", "cost_sensitive", "simple_extraction"],
    ),
    # Google Gemini 2.5 Models (Latest)
    ModelID.GEMINI_2_5_PRO.value: ModelInfo(
        provider=ModelProvider.GOOGLE,
        model_id=ModelID.GEMINI_2_5_PRO.value,
        display_name="Gemini 2.5 Pro",
        description="Advanced thinking model with reasoning capabilities",
        context_window=2097152,  # 2M tokens
        max_output_tokens=8192,
        cost_per_1k_input=0.00125,
        cost_per_1k_output=0.005,
        supports_vision=True,
        knowledge_cutoff="2024-10",
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.EXTENDED_THINKING,
            ModelCapability.TOOL_USE,
            ModelCapability.PARALLEL_TOOLS,
            ModelCapability.VISION,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.JSON_MODE,
            ModelCapability.LONG_CONTEXT,
        ],
        recommended_use_cases=["long_context", "reasoning", "multimodal_analysis"],
    ),
    ModelID.GEMINI_2_5_FLASH.value: ModelInfo(
        provider=ModelProvider.GOOGLE,
        model_id=ModelID.GEMINI_2_5_FLASH.value,
        display_name="Gemini 2.5 Flash",
        description="Fastest Gemini model for speed and efficiency with thinking capabilities",
        context_window=1048576,  # 1M tokens
        max_output_tokens=8192,
        cost_per_1k_input=0.000075,
        cost_per_1k_output=0.0003,
        supports_vision=True,
        knowledge_cutoff="2024-10",
        capabilities=[
            ModelCapability.REASONING,
            ModelCapability.EXTENDED_THINKING,
            ModelCapability.TOOL_USE,
            ModelCapability.PARALLEL_TOOLS,
            ModelCapability.VISION,
            ModelCapability.STRUCTURED_OUTPUT,
            ModelCapability.JSON_MODE,
            ModelCapability.LONG_CONTEXT,
            ModelCapability.REAL_TIME,  # Live API support
        ],
        recommended_use_cases=["high_volume", "latency_sensitive", "cost_efficient"],
    ),
}


# Capability-based model groupings
# Models with reasoning + tool calling for LLMClient
REASONING_MODELS = [
    ModelID.CLAUDE_OPUS_4,  # Default
    ModelID.O3_PRO,
    ModelID.O3,
    ModelID.GEMINI_2_5_PRO,
]

# Models optimized for structured data extraction
STRUCTURED_OUTPUT_MODELS = [
    ModelID.GPT_4O,  # Default
    ModelID.GPT_4O_MINI,
    ModelID.CLAUDE_SONNET_4,
    # TODO: Add Gemini models once instructor issues are resolved
    # Currently getting "Instructor does not support multiple function calls" error
    # ModelID.GEMINI_2_5_PRO,
    # ModelID.GEMINI_2_5_FLASH,
]


# Default model configuration for clients and tools
# TODO: Make the model config structure richer later - add constraints, preferences, etc.
# TODO: Update this configuration to work with LLMClient instead of AgenticClient/StructuredClient
# The capability-based grouping (REASONING_MODELS vs STRUCTURED_OUTPUT_MODELS) needs to be
# preserved but mapped differently now that we have a unified LLMClient
DEFAULT_MODEL_CONFIG = {
    "AgenticClient": {"default_model": ModelID.CLAUDE_OPUS_4, "supported_models": REASONING_MODELS},
    "StructuredClient": {
        "default_model": ModelID.GPT_4O,
        "supported_models": STRUCTURED_OUTPUT_MODELS,
    },
    # Tools can be added here as needed
    # e.g., "file_read": {
    #     "default_model": ModelID.CLAUDE_SONNET_4,
    #     "supported_models": REASONING_MODELS
    # }
}


# Model aliases for convenience
MODEL_ALIASES = {
    # Anthropic aliases
    "claude": ModelID.CLAUDE_SONNET_4.value,  # Default to Claude 4 Sonnet
    "claude-opus": ModelID.CLAUDE_OPUS_4.value,
    "claude-sonnet": ModelID.CLAUDE_SONNET_4.value,
    # OpenAI aliases
    "o3": ModelID.O3.value,
    "o4-mini": ModelID.O4_MINI.value,
    "gpt": ModelID.GPT_4O_MINI.value,  # Default to GPT-4o Mini
    "gpt-fast": ModelID.GPT_4O_MINI.value,
    # Google aliases
    "gemini": ModelID.GEMINI_2_5_FLASH.value,  # Default to latest fast Gemini
    "gemini-flash": ModelID.GEMINI_2_5_FLASH.value,
    "gemini-pro": ModelID.GEMINI_2_5_PRO.value,
}


def get_model(model_id: str) -> ModelInfo:
    """Get model info by ID or alias."""
    # Check if it's an alias
    if model_id in MODEL_ALIASES:
        model_id = MODEL_ALIASES[model_id]

    # Check if model exists
    if model_id not in MODELS:
        raise ValueError(f"Unknown model: {model_id}")

    return MODELS[model_id]


def get_models_by_provider(provider: ModelProvider) -> list[ModelInfo]:
    """Get all models for a specific provider."""
    return [model for model in MODELS.values() if model.provider == provider]


def get_cheapest_model(provider: Optional[ModelProvider] = None) -> ModelInfo:
    """Get the cheapest model, optionally filtered by provider."""
    models = list(MODELS.values()) if provider is None else get_models_by_provider(provider)
    models_with_cost = [m for m in models if m.cost_per_1k_input is not None]

    if not models_with_cost:
        raise ValueError("No models with cost information available")

    return min(models_with_cost, key=lambda m: m.cost_per_1k_input or float("inf"))


def _filter_and_select_model(
    candidates: list[ModelInfo],
    min_context_window: int = 100000,
    max_cost_per_1k_input: Optional[float] = None,
    max_cost_per_1k_output: Optional[float] = None,
    min_output_tokens: Optional[int] = None,
    require_capabilities: Optional[list[ModelCapability]] = None,
    require_json_mode: bool = False,
    require_extended_thinking: bool = False,
    prefer_provider: Optional[ModelProvider] = None,
    exclude_models: Optional[list[ModelID]] = None,
) -> ModelInfo:
    """Common filtering logic for model selection."""
    # Filter by exclusions
    if exclude_models:
        exclude_ids = [m.value for m in exclude_models]
        candidates = [m for m in candidates if m.model_id not in exclude_ids]

    # Filter by requirements
    if min_context_window:
        candidates = [m for m in candidates if m.context_window >= min_context_window]

    if max_cost_per_1k_input is not None:
        candidates = [
            m
            for m in candidates
            if m.cost_per_1k_input and m.cost_per_1k_input <= max_cost_per_1k_input
        ]

    if max_cost_per_1k_output is not None:
        candidates = [
            m
            for m in candidates
            if m.cost_per_1k_output and m.cost_per_1k_output <= max_cost_per_1k_output
        ]

    if min_output_tokens:
        candidates = [
            m
            for m in candidates
            if m.max_output_tokens and m.max_output_tokens >= min_output_tokens
        ]

    if require_capabilities:
        for cap in require_capabilities:
            candidates = [m for m in candidates if cap in m.capabilities]

    if require_json_mode:
        candidates = [m for m in candidates if ModelCapability.JSON_MODE in m.capabilities]

    if require_extended_thinking:
        candidates = [m for m in candidates if ModelCapability.EXTENDED_THINKING in m.capabilities]

    if not candidates:
        raise ValueError("No models match the specified requirements")

    # Prefer specific provider if requested
    if prefer_provider:
        provider_models = [m for m in candidates if m.provider == prefer_provider]
        if provider_models:
            candidates = provider_models

    # Return first candidate (already in preference order)
    return candidates[0]


def get_reasoning_model(
    min_context_window: int = 100000,
    max_cost_per_1k_input: Optional[float] = None,
    require_extended_thinking: bool = False,
    prefer_provider: Optional[ModelProvider] = None,
    exclude_models: Optional[list[ModelID]] = None,
) -> ModelInfo:
    """Get best reasoning model with tool support from REASONING_MODELS."""
    candidates = [get_model(m.value) for m in REASONING_MODELS]
    return _filter_and_select_model(
        candidates,
        min_context_window=min_context_window,
        max_cost_per_1k_input=max_cost_per_1k_input,
        require_capabilities=[ModelCapability.REASONING, ModelCapability.TOOL_USE],
        require_extended_thinking=require_extended_thinking,
        prefer_provider=prefer_provider,
        exclude_models=exclude_models,
    )


def get_structured_output_model(
    min_context_window: int = 100000,
    require_json_mode: bool = False,
    min_output_tokens: Optional[int] = None,
    max_cost_per_1k_output: Optional[float] = None,
    prefer_provider: Optional[ModelProvider] = None,
    exclude_models: Optional[list[ModelID]] = None,
) -> ModelInfo:
    """Get best model for structured data extraction from STRUCTURED_OUTPUT_MODELS."""
    candidates = [get_model(m.value) for m in STRUCTURED_OUTPUT_MODELS]
    return _filter_and_select_model(
        candidates,
        min_context_window=min_context_window,
        max_cost_per_1k_output=max_cost_per_1k_output,
        require_capabilities=[ModelCapability.STRUCTURED_OUTPUT],
        require_json_mode=require_json_mode,
        min_output_tokens=min_output_tokens,
        prefer_provider=prefer_provider,
        exclude_models=exclude_models,
    )


def get_model_for_client(
    client_name: str, min_context_window: int = 100000, user_config: Optional[dict] = None
) -> ModelInfo:
    """Get model for a specific client based on config."""
    # Get user config or default
    config = user_config or DEFAULT_MODEL_CONFIG.get(client_name)
    if not config:
        raise ValueError(f"Unknown client: {client_name}")

    # Try default model first
    default_model_id = config.get("default_model")
    if default_model_id:
        try:
            # If it's already a ModelID enum, use its value
            if isinstance(default_model_id, ModelID):
                model = get_model(default_model_id.value)
            elif isinstance(default_model_id, str):
                # Otherwise assume it's a string
                model = get_model(default_model_id)
            else:
                # Skip if it's neither ModelID nor string
                raise ValueError("Invalid model ID type")
            if model.context_window >= min_context_window:
                return model
        except ValueError:
            pass

    # Try other supported models
    supported_models = config.get("supported_models", [])
    for model_id in supported_models:
        if model_id == default_model_id:  # Skip already tried default
            continue
        try:
            # If it's already a ModelID enum, use its value
            if isinstance(model_id, ModelID):
                model = get_model(model_id.value)
            elif isinstance(model_id, str):
                # Otherwise assume it's a string
                model = get_model(model_id)
            else:
                # Skip if it's neither ModelID nor string
                continue
            if model.context_window >= min_context_window:
                return model
        except ValueError:
            continue

    # Fall back to capability-based selection
    if client_name == "AgenticClient":
        return get_reasoning_model(min_context_window=min_context_window)
    elif client_name == "StructuredClient":
        return get_structured_output_model(min_context_window=min_context_window)
    else:
        raise ValueError(f"No suitable model found for client: {client_name}")


def get_model_for_tool(
    tool_name: str, min_context_window: int = 100000, user_config: Optional[dict] = None
) -> ModelInfo:
    """Get model for a specific tool based on config."""
    # Get user config or default
    config = user_config or DEFAULT_MODEL_CONFIG.get(tool_name)

    if config:
        # Tool has specific configuration
        default_model_id = config.get("default_model")
        if default_model_id:
            try:
                # If it's already a ModelID enum, use its value
                if isinstance(default_model_id, ModelID):
                    model = get_model(default_model_id.value)
                elif isinstance(default_model_id, str):
                    # Otherwise assume it's a string
                    model = get_model(default_model_id)
                else:
                    # Skip if it's neither ModelID nor string
                    raise ValueError("Invalid model ID type")
                if model.context_window >= min_context_window:
                    return model
            except ValueError:
                pass

        # Try other supported models
        supported_models = config.get("supported_models", [])
        for model_id in supported_models:
            if model_id == default_model_id:  # Skip already tried default
                continue
            try:
                # If it's already a ModelID enum, use its value
                if isinstance(model_id, ModelID):
                    model = get_model(model_id.value)
                else:
                    # Otherwise assume it's a string
                    model = get_model(model_id)
                if model.context_window >= min_context_window:
                    return model
            except ValueError:
                continue

    # Default to reasoning model for unknown tools
    return get_reasoning_model(min_context_window=min_context_window)
