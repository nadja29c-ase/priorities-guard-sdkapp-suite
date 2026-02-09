"""
Priority Guardian MCP Tool Registry.

Explicit registry pattern - no import side effects, no register_tool() calls.
The registry is a single inspectable, testable data structure.
"""

from copy import deepcopy
from typing import List

import structlog
from mcp import types as mcp_types

from .base import ToolDefinition
from .connect_google_calendar import CONNECT_GOOGLE_CALENDAR
from .disconnect_google_calendar import DISCONNECT_GOOGLE_CALENDAR
from .create_priority import CREATE_PRIORITY

logger = structlog.get_logger(__name__)

# Explicit tool registry
TOOL_REGISTRY: dict[str, ToolDefinition] = {
    CONNECT_GOOGLE_CALENDAR.name: CONNECT_GOOGLE_CALENDAR,
    DISCONNECT_GOOGLE_CALENDAR.name: DISCONNECT_GOOGLE_CALENDAR,
    CREATE_PRIORITY.name: CREATE_PRIORITY,
}


def get_tool(name: str) -> ToolDefinition | None:
    """Get a tool by name, or None if not found."""
    return TOOL_REGISTRY.get(name)


async def list_tools() -> List[mcp_types.Tool]:
    """
    Build MCP Tool list from registry.

    Each tool gets _meta with:
    - annotations (readOnlyHint, destructiveHint, openWorldHint)
    - securitySchemes (oauth2 with scopes)
    - openai/outputTemplate if widget_uri is set

    Sorted by name for deterministic output.
    """
    tools = []

    # Sort by name for deterministic output
    for tool_def in sorted(TOOL_REGISTRY.values(), key=lambda t: t.name):
        # Build annotations from tool definition
        annotations = {
            "readOnlyHint": tool_def.read_only_hint,
            "destructiveHint": tool_def.destructive_hint,
            "openWorldHint": tool_def.open_world_hint,
        }

        # Build securitySchemes based on required_scopes
        if tool_def.required_scopes:
            security_schemes = [{"type": "oauth2", "scopes": tool_def.required_scopes}]
        else:
            security_schemes = [{"type": "noauth"}]

        # Build _meta based on tool capabilities
        if tool_def.widget_uri:
            # Widget-producing tools get full metadata
            meta = {
                "openai/outputTemplate": tool_def.widget_uri,
                "openai/toolInvocation/invoking": "Processing...",
                "openai/toolInvocation/invoked": "Done.",
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
                "annotations": annotations,
                "securitySchemes": security_schemes,
            }
        elif tool_def.widget_accessible:
            # Widget-callable tools need widgetAccessible
            meta = {
                "openai/widgetAccessible": True,
                "annotations": annotations,
                "securitySchemes": security_schemes,
            }
        else:
            # Data-only tools still need annotations
            meta = {
                "annotations": annotations,
                "securitySchemes": security_schemes,
            }

        tool = mcp_types.Tool(
            name=tool_def.name,
            description=tool_def.description,
            inputSchema=deepcopy(tool_def.input_schema),
            _meta=meta,
        )

        # Future-proof: mirror annotations at top level if SDK supports it
        if hasattr(tool, "annotations"):
            tool.annotations = annotations

        tools.append(tool)

    logger.debug("tools.list.returning", tool_count=len(tools))
    return tools
