"""
Clarity MCP Tool Registry.

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

    Follows OpenAI pattern for widget integration - tools with widget_uri
    get appropriate _meta for ChatGPT widget rendering.
    """
    tools = []

    for tool_def in TOOL_REGISTRY.values():
        # Build _meta for widget-producing tools
        meta = None
        if tool_def.widget_uri:
            meta = {
                "openai/outputTemplate": tool_def.widget_uri,
                "openai/toolInvocation/invoking": "Processing...",
                "openai/toolInvocation/invoked": "Done.",
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
                "annotations": {
                    "destructiveHint": False,
                    "openWorldHint": False,
                    "readOnlyHint": True,
                }
            }

        tool = mcp_types.Tool(
            name=tool_def.name,
            description=tool_def.description,
            inputSchema=deepcopy(tool_def.input_schema),
            _meta=meta,
        )
        tools.append(tool)

    logger.debug("tools.list.returning", tool_count=len(tools))
    return tools


# ============================================================================
# Import all tools here for registration
# ============================================================================
# WARNING: Tools self-register at import time.
# If you add a new tool, import it here or it won't be in the registry.

from . import cluster_raw_thoughts  # noqa: F401, E402
from . import get_my_clusters  # noqa: F401, E402
# from . import identify_relevant  # noqa: F401  (future)
# from . import specify_next_steps  # noqa: F401  (future)
