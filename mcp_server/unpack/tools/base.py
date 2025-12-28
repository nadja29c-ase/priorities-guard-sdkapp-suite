"""
Base definitions for Unpack MCP tools.

Tools self-register at import time using register_tool().
"""

from dataclasses import dataclass
from typing import Callable, Awaitable, Any


class ToolUsageError(Exception):
    """
    Raised when a tool intentionally rejects a request.

    Use this for expected rejections that are part of the conversation flow:
    - Input validation failures (e.g., "minimum 3 questions required")
    - Guardrail rejections (e.g., "cannot go back after selection")
    - Business rule violations

    NOT for unexpected crashes or internal errors.

    The message will be surfaced to the assistant verbatim.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


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
        name: Tool name (e.g., "formulate_problem")
        description: Tool description shown to ChatGPT
        input_schema: JSON Schema for ChatGPT/MCP discovery
        widget_uri: Widget URI for tools that produce widgets, None otherwise
        handle: Async handler function (user_id, correlation_id, arguments) -> CallToolResult

    Note: Unpack uses noauth, so no required_scopes field.
    Handler still receives user_id/correlation_id for consistency, but they'll be empty.
    """
    name: str
    description: str
    input_schema: dict
    widget_uri: str | None  # None if tool doesn't produce widget
    handle: Callable[[str, str, dict], Awaitable[Any]]  # (user_id, correlation_id, arguments)
    # Tool annotations (compliance hints for OpenAI)
    read_only_hint: bool = True  # Default: read-only (no side effects)
    destructive_hint: bool = False  # True if tool may overwrite/delete data
    open_world_hint: bool = False  # True if tool interacts with external systems
