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
from typing import Any, Optional

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Standardized result from tool execution."""

    success: bool = Field(..., description="Whether the tool execution succeeded")
    # TODO: Rename llm_content to simply content for consistency
    llm_content: str = Field(..., description="Content formatted for LLM context")
    error: Optional[str] = Field(None, description="Error message if execution failed")
    user_display: str = Field(..., description="Human-readable display of the result")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata about the execution"
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

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute the tool with given parameters.

        Args:
            params: Tool parameters matching the function schema

        Returns:
            ToolResult with execution output
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

        return {"name": self.name, "description": self.description, "parameters": schema}

    async def execute(self, params: dict[str, Any]) -> ToolResult:
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
            return ToolResult(
                success=True,
                llm_content=output.model_dump_json(),
                error=None,
                user_display=self._format_display(output),
                metadata={"tool_name": self.name},
            )

        except Exception as e:
            # Return error as result
            error_msg = f"Error executing {self.name}: {str(e)}"
            return ToolResult(
                success=False,
                llm_content=error_msg,
                error=str(e),
                user_display=error_msg,
                metadata={"error": True, "error_type": type(e).__name__, "tool_name": self.name},
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
        from client.base_client import Message, Role

        messages = [
            Message(role=Role.SYSTEM, content=system_prompt),
            Message(role=Role.USER, content=prompt),
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
