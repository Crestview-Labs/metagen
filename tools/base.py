"""Base classes for the two-tier tool architecture.

This module provides the foundation for all tools in the system:
- BaseTool: Abstract base for all tools
- BaseCoreTool: Base for in-process tools with Pydantic schemas
- BaseLLMTool: Base for LLM-powered tools with instructions

Tools are simple and focused. Context management (session tracking,
resource injection) is handled by the Meta-agent during tool execution.
"""

import json
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from common.types import ToolCallResult, ToolErrorType


class Tool(BaseModel):
    """Tool schema that gets passed to LLMs.

    This is the tool definition/interface that LLMs see when deciding
    which tools to use. It's generated from the BaseTool implementation.
    """

    # Basic info
    name: str = Field(..., description="Name of the tool")
    description: str = Field(..., description="What the tool does")

    # Parameter schema - standardized to input_schema
    input_schema: dict[str, Any] = Field(
        ..., description="JSON Schema describing the tool's input parameters"
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Tool":
        """Create a Tool instance from a dictionary.

        Useful for converting MCP tools and other dict-based tool definitions.
        """
        return cls(
            name=data["name"],
            description=data["description"],
            input_schema=data.get("input_schema", {}),
        )


class BaseTool(ABC):
    """Abstract base class for all tools.

    Tools should be stateless and receive all necessary
    resources through constructor injection (like Gemini CLI).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this tool does."""
        pass

    @abstractmethod
    def get_function_schema(self) -> dict[str, Any]:
        """Get JSON schema for function calling."""
        pass

    def get_tool_schema(self) -> Tool:
        """Get the Tool schema for passing to LLMs.

        This converts the tool's function schema into the standardized
        Tool format that LLMs expect.
        """
        function_schema = self.get_function_schema()

        return Tool(name=self.name, description=self.description, input_schema=function_schema)

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolCallResult:
        """Execute the tool with given parameters.

        Args:
            params: Tool parameters matching the function schema

        Returns:
            ToolCallResult with execution output
        """
        pass


class BaseCoreTool(BaseTool):
    """Base class for in-process tools with Pydantic schemas.

    Resources like memory_manager, llm_client, etc. are injected
    through the constructor by the Meta-agent or tool factory.
    """

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: type[BaseModel],
        output_schema: type[BaseModel],
    ):
        self._name = name
        self._description = description
        self.input_schema = input_schema
        self.output_schema = output_schema

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def get_function_schema(self) -> dict[str, Any]:
        """Generate function schema from input schema."""
        schema = self.input_schema.model_json_schema()

        # Remove title if present (not needed for function calling)
        schema.pop("title", None)

        return schema

    async def execute(self, params: dict[str, Any]) -> ToolCallResult:
        """Execute tool with validation and error handling."""
        try:
            # Validate and parse input
            validated_input = self.input_schema(**params)

            # Execute tool-specific logic
            output = await self._execute_impl(validated_input)

            # Validate output matches schema
            if not isinstance(output, self.output_schema):
                output = self.output_schema.model_validate(output)

            # Format result
            return ToolCallResult(
                tool_name=self.name,
                tool_call_id=None,  # Will be set by executor
                content=output.model_dump_json(),
                is_error=False,
                error=None,
                error_type=None,
                user_display=self._format_display(output),
                metadata={},
            )

        except Exception as e:
            # Return error as result
            error_msg = f"Error executing {self.name}: {str(e)}"
            return ToolCallResult(
                tool_name=self.name,
                tool_call_id=None,  # Will be set by executor
                content=error_msg,
                is_error=True,
                error=str(e),
                error_type=ToolErrorType.EXECUTION_ERROR,
                user_display=error_msg,
                metadata={"error_class": type(e).__name__},
            )

    @abstractmethod
    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """Tool-specific implementation.

        Args:
            input_data: Validated input matching input_schema

        Returns:
            Output matching output_schema
        """
        pass

    def _format_display(self, output: BaseModel) -> str:
        """Format output for user display.

        Override this method for custom formatting.
        """
        # Default: pretty-printed JSON
        return json.dumps(output.model_dump(), indent=2)


class BaseLLMTool(BaseCoreTool):
    """Base class for LLM-powered tools with instructions.

    LLM client is injected through constructor, not passed in execute().
    """

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: type[BaseModel],
        output_schema: type[BaseModel],
        instructions: str,
        llm_client: Any,  # Injected by Meta-agent
        task_type: str = "general",
    ):
        super().__init__(name, description, input_schema, output_schema)
        self.instructions = instructions
        self.llm_client = llm_client
        self.task_type = task_type

    async def _execute_impl(self, input_data: BaseModel) -> BaseModel:
        """Execute using LLM with structured output."""
        # Build prompt from instructions and input
        prompt = self._build_prompt(input_data)

        # Get system prompt
        system_prompt = self._get_system_prompt()

        # Create messages
        from client.types import LLMMessage, LLMMessageRole

        messages = [
            LLMMessage(role=LLMMessageRole.SYSTEM, content=system_prompt),
            LLMMessage(role=LLMMessageRole.USER, content=prompt),
        ]

        # Execute with structured output
        output = await self.llm_client.generate_structured(
            messages=messages,
            response_model=self.output_schema,
            temperature=0.7,
            model=None,  # Will use task-appropriate default
        )

        return output  # type: ignore[no-any-return]

    def _get_system_prompt(self) -> str:
        """Get the system prompt for the tool."""
        return f"You are an expert assistant executing the '{self.name}' tool. {self.description}"

    def _build_prompt(self, input_data: BaseModel) -> str:
        """Build prompt from instructions and input data."""
        prompt = self.instructions
        input_dict = input_data.model_dump()

        # Handle {{INPUT}} placeholder
        if "{{INPUT}}" in prompt:
            prompt = prompt.replace("{{INPUT}}", json.dumps(input_dict, indent=2))

        # Handle field-specific substitutions (e.g., {{FIELD_NAME}})
        for key, value in input_dict.items():
            placeholder = f"{{{{{key.upper()}}}}}"
            if placeholder in prompt:
                if isinstance(value, (dict, list)):
                    prompt = prompt.replace(placeholder, json.dumps(value, indent=2))
                else:
                    prompt = prompt.replace(placeholder, str(value))

        return prompt
