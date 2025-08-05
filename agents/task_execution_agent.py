"""TaskExecutionAgent - Intelligent agent for executing tasks with general capabilities."""

from typing import Any, AsyncIterator, Optional

from agents.base import BaseAgent
from common.messages import (
    AgentMessage,
    ErrorMessage,
    Message,
    SystemMessage,
    ToolCallMessage,
    ToolErrorMessage,
    ToolResultMessage,
)
from common.types import TaskExecutionContext, ToolCallResult, ToolErrorType
from tools.base import Tool


class TaskExecutionAgent(BaseAgent):
    """
    Intelligent agent for executing tasks with general capabilities.

    This agent receives a TaskExecutionRequest and uses general intelligence
    to figure out how to execute it using available tools. It doesn't depend
    on specific task definitions but can interpret and execute any task.
    """

    def __init__(
        self,
        agent_id: str,
        memory_manager: Any = None,
        llm_config: Optional[dict[str, Any]] = None,
        mcp_servers: Optional[list[Any]] = None,
        available_tools: Optional[list[Tool]] = None,
        disabled_tools: Optional[set[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize TaskExecutionAgent with general task execution capabilities."""
        instructions = """You are a TaskExecutionAgent - THE agent responsible for executing tasks.

Your primary responsibilities:
1. You ARE the task executor - you don't delegate to other agents
2. When you receive a task, YOU must complete it using available tools
3. Break down complex tasks into manageable steps
4. Use tools like read_file, write_file, search_files to accomplish tasks
5. Provide clear progress updates and final results
6. Handle errors gracefully and provide helpful feedback

Key principles:
- You are the FINAL executor - do NOT call execute_task (that would create infinite recursion)
- You have direct access to file tools, search tools, and other utilities
- Complete the task yourself using these tools
- Always understand the task fully before starting execution
- Use tools systematically and purposefully
- Provide clear, structured output showing what you did
- Complete tasks thoroughly and verify results when possible

When you receive a TaskExecutionRequest, YOU execute it directly using your available tools."""

        super().__init__(
            agent_id=agent_id,
            instructions=instructions,
            memory_manager=memory_manager,
            llm_config=llm_config,
            mcp_servers=mcp_servers,
            available_tools=available_tools,
            disabled_tools=disabled_tools,
            **kwargs,
        )

        # Current task execution state
        self.current_task_context: Optional[TaskExecutionContext] = None

    def set_current_task(self, context: TaskExecutionContext) -> None:
        """Set the current task execution context."""
        self.current_task_context = context

    def clear_current_task(self) -> None:
        """Clear the current task after completion."""
        self.current_task_context = None

    def get_current_task_id(self) -> Optional[str]:
        """Get current task ID if executing a task."""
        if self.current_task_context:
            return self.current_task_context.task_id
        return None

    @property
    def is_executing(self) -> bool:
        """Check if agent is currently executing a task."""
        return self.current_task_context is not None

    def build_task_prompt(self, context: TaskExecutionContext) -> str:
        """Build a prompt for task execution."""
        prompt = f"""Task: {context.task_name}

Instructions:
{context.instructions}

Input values provided:
"""

        for key, param_value in context.input_values.items():
            prompt += f"- {key}: {param_value.to_string()}\n"

        prompt += "\nPlease execute this task now using available tools."
        return prompt

    async def build_context(self, query: str) -> list[Message]:
        """
        Build context for task execution.

        For TaskExecutionAgent, context is minimal since each task is self-contained.
        """
        context: list[Message] = []

        # Add system message about being a task execution agent
        context.append(
            SystemMessage(
                content=(
                    "You are a TaskExecutionAgent. Focus on executing the current task "
                    "efficiently using available tools."
                )
            )
        )

        # Add current task context if available
        if self.current_task_context:
            context.append(
                SystemMessage(content=f"Current task ID: {self.current_task_context.task_id}")
            )

        # TODO: Add relevant conversation history from memory_manager if needed
        # For now, keep it minimal to focus on task execution

        return context

    async def stream_chat(self, message: Message) -> AsyncIterator[Message]:
        """
        Override stream_chat to handle task execution and yield ToolResultMessage.
        
        This ensures that task execution results are properly communicated
        to the router for FIFO coordination.
        """
        # Track execution metadata
        final_response = ""
        execution_metadata: dict[str, Any] = {"tool_calls": 0, "errors": 0, "stages": []}
        
        # Use parent's stream_chat for the actual execution
        async for msg in super().stream_chat(message):
            # Track different message types
            if isinstance(msg, AgentMessage):
                execution_metadata["stages"].append("response")
                if msg.final:
                    final_response = msg.content
            elif isinstance(msg, ToolCallMessage):
                execution_metadata["stages"].append("tool_call")
                execution_metadata["tool_calls"] += 1
            elif isinstance(msg, (ToolErrorMessage, ErrorMessage)):
                execution_metadata["stages"].append("error")
                execution_metadata["errors"] += 1
            
            # Yield the message as-is
            yield msg
        
        # After all messages are done, yield a ToolResultMessage with the complete result
        if self.current_task_context:
            success = execution_metadata["errors"] == 0 and final_response.strip()
            
            if success:
                result = ToolCallResult(
                    tool_name="execute_task",
                    # Use original tool_call_id
                    tool_call_id=self.current_task_context.tool_call_id,
                    content=f"Task executed successfully. Result: {final_response}",
                    is_error=False,
                    error=None,
                    error_type=None,
                    user_display=(
                        f"Task '{self.current_task_context.task_name}' completed successfully"
                    ),
                    metadata={
                        "task_id": self.current_task_context.task_id,
                        "agent_id": self.agent_id,
                        "execution_stats": execution_metadata,
                        "result": final_response,
                    },
                )
            else:
                result = ToolCallResult(
                    tool_name="execute_task",
                    # Use original tool_call_id
                    tool_call_id=self.current_task_context.tool_call_id,
                    content="Task execution failed or produced no result",
                    is_error=True,
                    error="Task execution failed",
                    error_type=ToolErrorType.EXECUTION_ERROR,
                    user_display=f"Task '{self.current_task_context.task_name}' failed to complete",
                    metadata={
                        "task_id": self.current_task_context.task_id,
                        "agent_id": self.agent_id,
                        "execution_stats": execution_metadata,
                    },
                )
            
            # Yield the complete task result as a ToolResultMessage
            assert result.tool_call_id, "tool_call_id must not be None or empty"
            yield ToolResultMessage(
                agent_id=self.agent_id,  # Set agent_id properly
                tool_id=result.tool_call_id,
                tool_name=result.tool_name,
                result=result,  # Pass the complete ToolCallResult object
            )

    def get_task_info(self) -> dict[str, Any]:
        """Get information about the current task being executed."""
        if not self.current_task_context:
            return {"status": "idle", "agent_id": self.agent_id, "current_task": None}

        return {
            "status": "executing" if self.is_executing else "idle",
            "agent_id": self.agent_id,
            "current_task": {
                "task_id": self.current_task_context.task_id,
                "task_name": self.current_task_context.task_name,
                "input_values": self.current_task_context.input_values,
            },
        }
