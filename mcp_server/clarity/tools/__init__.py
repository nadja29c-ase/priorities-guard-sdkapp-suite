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

    Follows OpenAI pattern for widget integration:
    - Tools with widget_uri get full widget metadata
    - Tools with widget_accessible=True can be called from widgets via window.openai.callTool()
    - All tools get annotations for compliance
    - Tools are returned sorted by name for deterministic output
    """
    tools = []

    # Sort by name for deterministic output
    for tool_def in sorted(TOOL_REGISTRY.values(), key=lambda t: t.name):
        # Build typed ToolAnnotations object (not raw dict)
        # Per MCP SDK: annotations is a typed field on Tool, not embedded in _meta
        # Clarity's ToolDefinition has no title field, so we omit it
        tool_annotations = mcp_types.ToolAnnotations(
            readOnlyHint=tool_def.read_only_hint,
            destructiveHint=tool_def.destructive_hint,
            openWorldHint=tool_def.open_world_hint,
        )

        # Build securitySchemes based on required_scopes
        # SECURITY: Empty scopes means "auth required, no specific scope" (any authenticated user)
        # NOT "no auth required" - runtime always requires valid JWT via authenticate_request()
        # Using oauth2 with empty scopes array to match runtime behavior
        if tool_def.required_scopes is None:
            # Explicitly None = no auth (not used by any current tool, kept for future)
            security_schemes = [{"type": "noauth"}]
        else:
            # List (including empty []) = oauth2 with those scopes
            # Empty [] means "any authenticated user, no specific scope"
            security_schemes = [{"type": "oauth2", "scopes": tool_def.required_scopes}]

        # Build _meta based on tool capabilities
        # Use new ui.* keys per OpenAI Apps SDK (March 2026)
        if tool_def.widget_uri and tool_def.widget_accessible:
            # Widget-producing AND widget-callable tools
            # visibility: ["model", "app"] - both model and widget can call
            meta = {
                "ui": {
                    "resourceUri": tool_def.widget_uri,
                    "visibility": ["model", "app"],
                },
                "openai/outputTemplate": tool_def.widget_uri,  # compat alias
                "openai/toolInvocation/invoking": "Processing...",
                "openai/toolInvocation/invoked": "Done.",
                "securitySchemes": security_schemes,
            }
        elif tool_def.widget_uri:
            # Widget-producing but NOT widget-callable
            # visibility: ["model"] - only model can call
            meta = {
                "ui": {
                    "resourceUri": tool_def.widget_uri,
                    "visibility": ["model"],
                },
                "openai/outputTemplate": tool_def.widget_uri,  # compat alias
                "openai/toolInvocation/invoking": "Processing...",
                "openai/toolInvocation/invoked": "Done.",
                "securitySchemes": security_schemes,
            }
        elif tool_def.widget_accessible:
            # Widget-callable tools without widget output
            # visibility: ["model", "app"]
            meta = {
                "ui": {
                    "visibility": ["model", "app"],
                },
                "openai/toolInvocation/invoking": "Processing...",
                "openai/toolInvocation/invoked": "Done.",
                "securitySchemes": security_schemes,
            }
        else:
            # Model-only tools without widget
            # visibility: ["model"]
            meta = {
                "ui": {
                    "visibility": ["model"],
                },
                "openai/toolInvocation/invoking": "Processing...",
                "openai/toolInvocation/invoked": "Done.",
                "securitySchemes": security_schemes,
            }

        tool = mcp_types.Tool(
            name=tool_def.name,
            description=tool_def.description,
            inputSchema=deepcopy(tool_def.input_schema),
            _meta=meta,
        )

        # Set typed ToolAnnotations on the tool object
        # This is the correct location per MCP SDK - not in _meta
        tool.annotations = tool_annotations

        tools.append(tool)

    logger.debug("tools.list.returning", tool_count=len(tools))
    return tools


# ============================================================================
# Import all tools here for registration
# ============================================================================
# WARNING: Tools self-register at import time.
# If you add a new tool, import it here or it won't be in the registry.

from . import organize_thoughts  # noqa: F401, E402
from . import load_saved_board  # noqa: F401, E402
from . import read_board_before_editing  # noqa: F401, E402
from . import start_prioritization_flow  # noqa: F401, E402
from . import edit_board  # noqa: F401, E402
from . import delete_my_data  # noqa: F401, E402
from . import diagnostic_widget  # noqa: F401, E402 - inc_91 diagnostic
