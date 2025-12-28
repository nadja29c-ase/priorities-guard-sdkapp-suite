"""
Unpack MCP Tool Registry.

Tools self-register at import time using register_tool().

WARNING: Tools self-register at import time.
If you add a new tool, import it here or it won't be in the registry.
"""

from copy import deepcopy
from typing import List

import structlog
from mcp import types as mcp_types

from .base import ToolDefinition

logger = structlog.get_logger(__name__)

# Tool registry - populated by imports below
TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def register_tool(tool: ToolDefinition) -> None:
    """Register a tool in the registry."""
    if tool.name in TOOL_REGISTRY:
        logger.warning("tool.registry.duplicate", tool_name=tool.name)
    TOOL_REGISTRY[tool.name] = tool
    logger.debug("tool.registry.registered", tool_name=tool.name)


def get_tool(name: str) -> ToolDefinition | None:
    """Get a tool by name, or None if not found."""
    return TOOL_REGISTRY.get(name)


async def list_tools() -> List[mcp_types.Tool]:
    """
    Build MCP Tool list from registry.

    Unpack uses noauth - no OAuth security schemes.
    All tools get annotations for compliance.
    Tools are returned sorted by name for deterministic output.
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

        # Unpack uses noauth - no OAuth
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
        else:
            # Data-only tools (like formulate_problem) - no widget
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


# ============================================================================
# Import all tools here for registration
# ============================================================================
# WARNING: Tools self-register at import time.
# If you add a new tool, import it here or it won't be in the registry.

from . import formulate_problem  # noqa: F401, E402
