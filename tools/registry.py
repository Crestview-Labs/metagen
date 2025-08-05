"""Unified tool registry and executor for both core tools and MCP tools."""

import importlib
import inspect
import logging
import os
from typing import Any, Awaitable, Callable, Optional

from client.mcp_server import MCPServer
from common.types import ToolCall, ToolCallResult, ToolErrorType
from tools.base import BaseCoreTool, BaseLLMTool

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Unified tool executor that handles both core tools and MCP tools with interception
    support."""

    def __init__(self) -> None:
        self.core_tools: dict[str, BaseCoreTool] = {}
        self.mcp_servers: list[MCPServer] = []
        # Tool interceptors: tool_name -> interceptor function
        self.interceptors: dict[
            str, Callable[[str, str, dict[str, Any]], Awaitable[Optional[ToolCallResult]]]
        ] = {}

    def register_core_tool(self, tool: BaseCoreTool) -> None:
        """Register a core tool instance."""
        self.core_tools[tool.name] = tool
        logger.debug(f"Registered core tool: {tool.name}")

    def register_mcp_servers(self, servers: list[MCPServer]) -> None:
        """Register MCP servers for external tools."""
        self.mcp_servers = servers
        logger.debug(f"Registered {len(servers)} MCP servers")

    def register_interceptor(
        self,
        tool_name: str,
        interceptor: Callable[[str, str, dict[str, Any]], Awaitable[Optional[ToolCallResult]]],
    ) -> None:
        """
        Register an interceptor for a specific tool.

        Args:
            tool_name: Name of the tool to intercept
            interceptor: Async function that takes (tool_call_id, tool_name, parameters) and
                        returns:
                        - ToolCallResult if the call should be intercepted and handled
                        - None if the call should proceed normally
        """
        self.interceptors[tool_name] = interceptor
        logger.info(f"Registered interceptor for tool: {tool_name}")

    def remove_interceptor(self, tool_name: str) -> None:
        """Remove an interceptor for a tool."""
        if tool_name in self.interceptors:
            del self.interceptors[tool_name]
            logger.info(f"Removed interceptor for tool: {tool_name}")

    async def execute(self, tool_call: ToolCall) -> ToolCallResult:
        """Execute a tool by name, checking interceptors first."""
        tool_name = tool_call.name
        tool_args = tool_call.arguments

        # Check if we have an interceptor for this tool
        if tool_name in self.interceptors:
            logger.info(f"Intercepting tool call: {tool_name}")
            interceptor = self.interceptors[tool_name]

            try:
                # Call the interceptor with tool_call_id
                result = await interceptor(tool_call.id, tool_name, tool_args)

                # If interceptor handled the call, return its result
                if result is not None:
                    logger.info(f"Tool call {tool_name} handled by interceptor")
                    # Ensure tool_call_id is set
                    if result.tool_call_id is None:
                        result.tool_call_id = tool_call.id
                    return result

                # Otherwise, proceed with normal execution
                logger.info(
                    f"Tool call {tool_name} not handled by interceptor, proceeding normally"
                )

            except Exception as e:
                logger.error(f"Interceptor for {tool_name} failed: {e}", exc_info=True)
                # If interceptor fails, proceed with normal execution

        # No interceptor or interceptor returned None - execute normally
        # Check if it's a core tool first
        if tool_name in self.core_tools:
            return await self._execute_core_tool(tool_call)

        # Otherwise, try MCP servers
        return await self._execute_mcp_tool(tool_call)

    async def _execute_core_tool(self, tool_call: ToolCall) -> ToolCallResult:
        """Execute a core tool in-process."""
        tool = self.core_tools[tool_call.name]
        logger.info(f"Executing core tool: {tool_call.name}")

        try:
            result = await tool.execute(tool_call.arguments)
            # Core tools already return ToolCallResult, ensure tool_call_id is set
            if result.tool_call_id is None:
                result.tool_call_id = tool_call.id
            return result
        except Exception as e:
            logger.error(f"Core tool {tool_call.name} failed: {e}")
            return ToolCallResult(
                tool_name=tool_call.name,
                tool_call_id=tool_call.id,
                content=f"Tool execution failed: {str(e)}",
                is_error=True,
                error=str(e),
                error_type=ToolErrorType.EXECUTION_ERROR,
                user_display=f"Error: {str(e)}",
                metadata={},
            )

    async def _execute_mcp_tool(self, tool_call: ToolCall) -> ToolCallResult:
        """Execute an MCP tool via server call."""
        logger.info(f"Executing MCP tool: {tool_call.name}")

        # Find the server that has this tool
        for server in self.mcp_servers:
            if server.is_running and server.has_tool(tool_call.name):
                try:
                    result = await server.call_tool(tool_call.name, tool_call.arguments)
                    # Convert MCP CallToolCallResult to our ToolCallResult format
                    content_text = str(result.content[0].text) if result.content else ""
                    return ToolCallResult(
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                        content=content_text,
                        is_error=result.isError,
                        error=content_text if result.isError else None,
                        error_type=ToolErrorType.EXECUTION_ERROR if result.isError else None,
                        user_display=content_text,
                        metadata={"mcp_server": True},
                    )
                except Exception as e:
                    logger.error(f"MCP tool {tool_call.name} failed: {e}")
                    return ToolCallResult(
                        tool_name=tool_call.name,
                        tool_call_id=tool_call.id,
                        content=f"MCP tool execution failed: {str(e)}",
                        is_error=True,
                        error=str(e),
                        error_type=ToolErrorType.EXECUTION_ERROR,
                        user_display=f"Error: {str(e)}",
                        metadata={},
                    )

        # Tool not found
        error_msg = f"Tool '{tool_call.name}' not found in any registered core tools or MCP servers"
        logger.error(error_msg)
        return ToolCallResult(
            tool_name=tool_call.name,
            tool_call_id=tool_call.id,
            content=error_msg,
            is_error=True,
            error=error_msg,
            error_type=ToolErrorType.INVALID_ARGS,  # Tool not found is like invalid args
            user_display=error_msg,
            metadata={"not_found": True},
        )


class ToolRegistry:
    """Unified tool registry that discovers and manages both core tools and MCP tools."""

    def __init__(
        self, executor: ToolExecutor, dependencies: Optional[dict[str, Any]] = None
    ) -> None:
        self.executor = executor
        self.disabled_tools: set[str] = set()
        self.dependencies = dependencies or {}

    def set_disabled_tools(self, disabled_tools: set[str]) -> None:
        """Set which tools should be disabled/filtered out."""
        self.disabled_tools = disabled_tools
        logger.info(f"Disabled tools: {disabled_tools}")

    async def discover_and_register_tools(
        self, core_tools_dir: str = "tools/core", mcp_servers: Optional[list[MCPServer]] = None
    ) -> None:
        """Discover and register all available tools."""

        # Discover and register core tools
        await self._discover_core_tools(core_tools_dir)

        # Register MCP servers
        if mcp_servers:
            self.executor.register_mcp_servers(mcp_servers)

    async def _discover_core_tools(self, core_tools_dir: str) -> None:
        """Auto-discover core tools from the specified directory."""
        logger.info(f"Discovering core tools in: {core_tools_dir}")

        # Convert relative path to absolute
        if not os.path.isabs(core_tools_dir):
            core_tools_dir = os.path.join(os.getcwd(), core_tools_dir)

        if not os.path.exists(core_tools_dir):
            logger.warning(f"Core tools directory not found: {core_tools_dir}")
            return

        # Find all Python files in the core tools directory
        for filename in os.listdir(core_tools_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = filename[:-3]  # Remove .py extension
                await self._load_tools_from_module(core_tools_dir, module_name)

    async def _load_tools_from_module(self, tools_dir: str, module_name: str) -> None:
        """Load tool classes from a Python module."""
        try:
            # Import the module dynamically
            module_path = f"tools.core.{module_name}"
            module = importlib.import_module(module_path)

            # Find all tool classes in the module
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseCoreTool) and obj != BaseCoreTool and obj != BaseLLMTool:
                    await self._instantiate_and_register_tool(obj, module_name)

        except Exception as e:
            logger.error(f"Failed to load tools from {module_name}: {e}")

    async def _instantiate_and_register_tool(
        self, tool_class: type[BaseCoreTool], module_name: str
    ) -> None:
        """Instantiate and register a tool class."""
        try:
            # Check if tool requires special initialization
            tool_instance = None

            if hasattr(tool_class, "__init__"):
                # Inspect constructor to see what dependencies it needs
                sig = inspect.signature(tool_class.__init__)
                params = sig.parameters

                # Build kwargs from available dependencies
                kwargs = {}
                missing_deps = []

                for param_name, param in params.items():
                    if param_name == "self":
                        continue

                    # Check if we have this dependency
                    if param_name in self.dependencies:
                        kwargs[param_name] = self.dependencies[param_name]
                    elif param.default == inspect.Parameter.empty:
                        # No default and no dependency provided
                        missing_deps.append(param_name)

                if missing_deps:
                    logger.warning(
                        f"Tool {tool_class.__name__} missing dependencies: "
                        f"{missing_deps}. Skipping."
                    )
                    return

                # All dependencies satisfied (or have defaults)
                tool_instance = tool_class(**kwargs)
            else:
                # This should never happen for BaseCoreTool subclasses
                logger.error(f"Tool class {tool_class.__name__} has no __init__ method")
                return

            if tool_instance:
                self.executor.register_core_tool(tool_instance)
                logger.info(f"Registered core tool: {tool_instance.name} from {module_name}")

        except Exception as e:
            logger.error(f"Failed to instantiate tool {tool_class.__name__}: {e}")

    def get_all_tools(self) -> list[dict[str, Any]]:
        """Get all available tools formatted for LLM consumption."""
        tools = []

        # Add core tools
        for tool_name, tool in self.executor.core_tools.items():
            if tool_name not in self.disabled_tools:
                tools.append(
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema.model_json_schema(),
                    }
                )

        # Add MCP tools
        for server in self.executor.mcp_servers:
            if server.is_running:
                for mcp_tool in server.get_tools():
                    if mcp_tool["name"] not in self.disabled_tools:
                        tools.append(mcp_tool)

        logger.debug(f"Returning {len(tools)} available tools")
        return tools

    def has_tool(self, tool_name: str) -> bool:
        """Check if a tool is available."""
        # Check core tools
        if tool_name in self.executor.core_tools:
            return tool_name not in self.disabled_tools

        # Check MCP servers
        for server in self.executor.mcp_servers:
            if server.is_running and server.has_tool(tool_name):
                return tool_name not in self.disabled_tools

        return False


# Global instances
tool_executor = ToolExecutor()
tool_registry = ToolRegistry(tool_executor)


def get_tool_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    return tool_registry


def get_tool_executor() -> ToolExecutor:
    """Get the global tool executor instance."""
    return tool_executor


def configure_tool_dependencies(dependencies: dict[str, Any]) -> None:
    """Configure dependencies for tools that need them."""
    tool_registry.dependencies.update(dependencies)
