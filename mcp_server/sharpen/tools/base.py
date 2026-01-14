"""
Base definitions for Sharpen MCP tools.

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
        name: Tool name (e.g., "export_checklist")
        description: Tool description shown to ChatGPT
        input_schema: JSON Schema for ChatGPT/MCP discovery
        handle: Async handler function (arguments) -> CallToolResult
    """
    name: str
    description: str
    input_schema: dict
    handle: Callable[[dict], Awaitable[Any]]  # (arguments) -> CallToolResult
    # Tool annotations (compliance hints for OpenAI)
    read_only_hint: bool = False  # Export tools produce artifacts
    destructive_hint: bool = False  # Doesn't modify/delete existing data
    open_world_hint: bool = False  # No external API calls
