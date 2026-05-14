"""
Base definitions for Priority Guardian MCP tools.

Contains ToolDefinition dataclass and ToolUsageError exception.
"""

from dataclasses import dataclass
from typing import Callable, Awaitable

from mcp import types as mcp_types


@dataclass
class ToolDefinition:
    """
    Definition for an MCP tool.

    Contract:
    - Tool handlers receive (user_id, correlation_id, arguments)
    - Handlers are responsible for validating arguments
    - Dispatcher does NOT validate against input_schema
    - input_schema is for ChatGPT/MCP discovery only

    Args:
        name: Tool name (e.g., "create_priority")
        title: Human-readable tool name for UI display (required by Anthropic §5E)
        description: Tool description shown to ChatGPT
        input_schema: JSON Schema for ChatGPT/MCP discovery
        required_scopes: OAuth scopes required to call this tool (e.g., ["pg.access"])
        widget_uri: Widget URI for tools that produce widgets, None otherwise
        handle: Async handler function (user_id, correlation_id, arguments) -> CallToolResult
        read_only_hint: If True, tool has no side effects
        destructive_hint: If True, tool may overwrite/delete data
        open_world_hint: If True, tool interacts with external systems
        widget_accessible: If True, widget can call this tool via callTool
        visibility: Tool visibility - "public" (LLM can see/call), "private" (widget-only)
    """
    name: str
    title: str  # Human-readable tool name for UI display (required by Anthropic §5E)
    description: str
    input_schema: dict
    required_scopes: list[str]
    widget_uri: str | None
    handle: Callable[[str, str, dict], Awaitable[mcp_types.CallToolResult]]  # (user_id, correlation_id, arguments)
    read_only_hint: bool = False
    destructive_hint: bool = False
    open_world_hint: bool = False
    widget_accessible: bool = False
    visibility: str = "public"  # "public" or "private"


class ToolUsageError(Exception):
    """
    Intentional rejection of a tool call.

    Raised for:
    - Input validation failures (before any HTTP call)
    - Business rule violations
    - Guardrail rejections

    Message surfaces to LLM verbatim. Logged at info level.
    Distinct from unexpected Exception (which returns generic error).
    """
    pass
