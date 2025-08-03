"""TaskExecutionAgent - Intelligent agent for executing tasks with general capabilities."""

from typing import Any, Optional

from agents.base import BaseAgent
from common.messages import (
    AgentMessage,
    ErrorMessage,
    Message,
    SystemMessage,
    ToolCallMessage,
    ToolErrorMessage,
    UserMessage,
)
from common.models import TaskExecutionRequest
from common.types import ToolCallResult, ToolErrorType
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
        self.current_task_request: Optional[TaskExecutionRequest] = None
        self.execution_status = "idle"  # idle, executing, completed, failed

    def set_current_task(self, task_request: TaskExecutionRequest) -> None:
        """Set the current task for execution."""
        self.current_task_request = task_request
        self.execution_status = "executing"

    def clear_current_task(self) -> None:
        """Clear the current task after completion."""
        self.current_task_request = None
        self.execution_status = "idle"

    def get_current_task_id(self) -> Optional[str]:
        """Get current task ID if executing a task."""
        if self.current_task_request:
            return self.current_task_request.task_id
        return None

    def build_task_prompt(self, task_request: TaskExecutionRequest) -> str:
        """Build a prompt for task execution."""
        prompt = f"""Please execute the following task:

**Task ID:** {task_request.task_id}

**Task Parameters:**
"""

        input_values = task_request.execution_context.get("input_values", {})
        if input_values:
            for key, value in input_values.items():
                prompt += f"- {key}: {value}\n"
        else:
            prompt += "No specific parameters provided.\n"

        prompt += "\n**Instructions:**\n"
        prompt += "1. Look up the task definition using the task_id if needed\n"
        prompt += "2. Analyze what needs to be accomplished\n"
        prompt += "3. Use the provided parameters with available tools\n"
        prompt += "4. Execute the task step by step\n"
        prompt += "5. Return the final result in a structured format\n"
        prompt += "\nExecute this task now using the available tools."

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
        if self.current_task_request:
            context.append(
                SystemMessage(content=f"Current task ID: {self.current_task_request.task_id}")
            )

        # TODO: Add relevant conversation history from memory_manager if needed
        # For now, keep it minimal to focus on task execution

        return context

    async def execute_task_fully(self, task_request: TaskExecutionRequest) -> ToolCallResult:
        """
        Execute a task completely and return the final result as ToolCallResult.

        This method is used by the stream multiplexing architecture to execute
        tasks while allowing CLI to see intermediate progress via separate streams.

        Args:
            task_request: The task execution request

        Returns:
            ToolCallResult containing the task execution result
        """
        # ToolCallResult already imported at the top

        # Set current task
        self.set_current_task(task_request)

        try:
            # Build and execute task
            task_prompt = self.build_task_prompt(task_request)
            final_response = ""
            execution_metadata: dict[str, Any] = {"tool_calls": 0, "errors": 0, "stages": []}

            # Stream through task execution and capture final result
            async for message in self.stream_chat(UserMessage(content=task_prompt)):
                # Handle different message types
                if isinstance(message, AgentMessage):
                    stage = "response"
                    content = message.content
                elif isinstance(message, ToolCallMessage):
                    stage = "tool_call"
                    content = ""
                elif isinstance(message, (ToolErrorMessage, ErrorMessage)):
                    stage = "error"
                    content = getattr(message, "error", "")

                # Track execution metadata
                execution_metadata["stages"].append(stage)
                if stage == "tool_call":
                    execution_metadata["tool_calls"] += 1
                elif stage in ["tool_error", "error"]:
                    execution_metadata["errors"] += 1
                elif stage == "response":
                    # This is the final response from the agent
                    final_response = content

            # Mark as completed
            self.execution_status = "completed"

            # Determine success based on execution
            success = execution_metadata["errors"] == 0 and final_response.strip()

            if success:
                return ToolCallResult(
                    tool_name="execute_task",
                    tool_call_id=task_request.id,
                    content=f"Task executed successfully. Result: {final_response}",
                    is_error=False,
                    error=None,
                    error_type=None,
                    user_display=f"Task '{task_request.task_id}' completed successfully",
                    metadata={
                        "task_id": task_request.task_id,
                        "agent_id": self.agent_id,
                        "execution_stats": execution_metadata,
                        "result": final_response,
                    },
                )
            else:
                self.execution_status = "failed"
                return ToolCallResult(
                    tool_name="execute_task",
                    tool_call_id=task_request.id,
                    content="Task execution failed or produced no result",
                    is_error=True,
                    error="Task execution failed",
                    error_type=ToolErrorType.EXECUTION_ERROR,
                    user_display=f"Task '{task_request.task_id}' failed to complete",
                    metadata={
                        "task_id": task_request.task_id,
                        "agent_id": self.agent_id,
                        "execution_stats": execution_metadata,
                    },
                )

        except Exception as e:
            self.execution_status = "failed"
            return ToolCallResult(
                tool_name="execute_task",
                tool_call_id=task_request.id,
                content=f"Task execution error: {str(e)}",
                is_error=True,
                error=str(e),
                error_type=ToolErrorType.EXECUTION_ERROR,
                user_display=f"Error executing task '{task_request.task_id}': {str(e)}",
                metadata={
                    "task_id": task_request.task_id,
                    "agent_id": self.agent_id,
                    "error": str(e),
                },
            )

    def get_task_info(self) -> dict[str, Any]:
        """Get information about the current task being executed."""
        if not self.current_task_request:
            return {"status": "idle", "agent_id": self.agent_id, "current_task": None}

        input_values = self.current_task_request.execution_context.get("input_values", {})
        return {
            "status": self.execution_status,
            "agent_id": self.agent_id,
            "current_task": {
                "id": self.current_task_request.id,
                "task_id": self.current_task_request.task_id,
                "input_values": input_values,
                "requested_by": self.current_task_request.requested_by,
            },
        }
