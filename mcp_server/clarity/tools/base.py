"""
Base definitions for Clarity MCP tools.

Tools self-register at import time using register_tool().
"""

from dataclasses import dataclass
from typing import Callable, Awaitable, Any


@dataclass
class ToolDefinition:
    """
    Definition for an MCP tool.

    Contract:
    - Tool handlers receive raw `arguments` dict from ChatGPT
    - Handlers are responsible for validating arguments (e.g., via Pydantic)
    - Dispatcher does NOT validate against input_schema
    - input_schema is for ChatGPT/MCP discovery only

    Args:
        name: Tool name (e.g., "cluster_raw_thoughts")
        description: Tool description shown to ChatGPT
        input_schema: JSON Schema for ChatGPT/MCP discovery
        required_scopes: OAuth scopes required to call this tool
        widget_uri: Widget URI for tools that produce widgets, None otherwise
        handle: Async handler function (user_id, correlation_id, arguments) -> CallToolResult
    """
    name: str
    description: str
    input_schema: dict
    required_scopes: list[str]
    widget_uri: str | None  # None if tool doesn't produce widget
    handle: Callable[[str, str, dict], Awaitable[Any]]  # (user_id, correlation_id, arguments)
