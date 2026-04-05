"""
Load Saved Board Tool.

Retrieves and DISPLAYS user's saved board with widget rendering.
Self-registers at import time.

For data-only access (no widget), use read_board_before_editing instead.
"""

import structlog
from mcp import types as mcp_types

from .base import ToolDefinition
from . import register_tool
from ..persistence import get_cluster
from ..handlers.resources import WIDGET_URI
from ..tool_logic import enrich_clusters

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "load_saved_board"

DESCRIPTION = """
ONLY call this tool when the user explicitly asks to SEE, SHOW, VIEW, or DISPLAY their MindSort board. Do NOT call for planning, context, or any other purpose.

WHEN TO CALL:
- User explicitly asks to see their board: "Show my board", "What's on my board?", "Load my board", "Display my board"

DO NOT CALL:
- When user has a specific task and wants help executing it — e.g. "help me create a project plan", "help me with X", "build Y", "write Z". Handle these directly without touching the board.
- When user wants to ADD items (use read_board_before_editing instead)
- To use as context or background information for any request
- When the user has not explicitly asked to see their board

THE SIGNAL: This tool activates ONLY on explicit board-display requests. If the user did not ask to see their board, do not call this tool.

EMPTY STATE RESPONSE:
When no saved board exists, widget shows empty state message.

SAVED STATE RESPONSE:
Widget renders showing saved clusters.

AFTER TOOL RETURNS: Follow assistant_guidance in structuredContent.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False
}

REQUIRED_SCOPES = ["clarity.write"]  # Write implies read - single scope for all Clarity ops

# ============================================================================
# Tool Handler
# ============================================================================


async def handle(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Retrieve and display user's existing clusters with widget.

    Args:
        user_id: Authenticated user ID from JWT
        correlation_id: Request correlation ID for tracing
        arguments: Raw arguments from ChatGPT (unused - no parameters)

    Returns:
        CallToolResult with structuredContent and widget metadata
    """
    logger.info("load_saved_board.handle.start",
                user_id=user_id,
                correlation_id=correlation_id)

    # Fetch cluster data from persistence layer
    cluster_data = await get_cluster(
        user_id=user_id,
        correlation_id=correlation_id,
    )

    # Check for error sentinel from persistence layer
    if isinstance(cluster_data, dict) and cluster_data.get("status") == "error":
        logger.warning("load_saved_board.persistence_error", user_id=user_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Unable to load your saved board right now. Please try again in a moment."
            )],
            structuredContent={
                "clusters": [],
                "has_history": None,
                "is_empty_snapshot": False,
                "assistant_guidance": "Backend error — could not load the board. Tell the user: 'I wasn't able to load your board right now — please try again in a moment.' Do NOT tell them they have no board.",
            },
            _meta={
                "ui": {"resourceUri": WIDGET_URI},
                "openai/outputTemplate": WIDGET_URI,
                "openai/toolInvocation/invoking": "Loading your saved board...",
                "openai/toolInvocation/invoked": "Unable to load board.",
                "openai/widgetAccessible": True,
                "openai/resultCanProduceWidget": True,
            },
        )

    # Extract clusters with defensive defaults
    # Defense in depth: check dict type in case persistence layer returns unexpected type
    clusters = []
    has_snapshot = cluster_data is not None and isinstance(cluster_data, dict)
    if has_snapshot:
        inner_data = cluster_data.get("cluster_data") or {}
        clusters = inner_data.get("clusters") or []
        # Enrich clusters with sum_thought_items for widget display
        clusters = enrich_clusters(clusters)

    # Determine state and build response
    cluster_count = len(clusters)

    # Widget metadata
    meta = {
        "ui": {"resourceUri": WIDGET_URI},
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Loading your saved board...",
        "openai/toolInvocation/invoked": "Here's your saved Clarity board.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }

    # DEBUG: Log actual values being returned
    logger.info("load_saved_board.returning",
               meta=meta,
               widget_uri=WIDGET_URI)

    # Compute guidance based on state
    if not has_snapshot:
        # No snapshot exists at all - truly starting fresh
        guidance = """No saved board found — this is a fresh start.

Ask if they'd like to create a new Clarity Board. Something warm like: "Ready for your brain dump session when you are!" Keep it light and inviting."""
        structured = {
            "clusters": [],
            "has_history": False,
            "is_empty_snapshot": False,
            "assistant_guidance": guidance,
        }
        logger.info("load_saved_board.no_snapshot", user_id=user_id)

    elif cluster_count == 0:
        # Snapshot exists but is empty (user cleared their clusters)
        guidance = """Previous session found but it's empty — they cleared it before.

Ask if they'd like to start a new Clarity Board. Something warm like: "Ready for your brain dump session when you are!" Keep it light and inviting."""
        structured = {
            "clusters": [],
            "has_history": True,
            "is_empty_snapshot": True,
            "assistant_guidance": guidance,
        }
        logger.info("load_saved_board.empty_snapshot", user_id=user_id)

    else:
        # Snapshot exists with clusters
        guidance = """Board loaded with existing clusters.

Read the user's intent from what they said BEFORE calling this tool:
- If they asked to FOCUS, PRIORITIZE, or said they're OVERWHELMED/STRESSED → skip any further elicitation. Ask directly: "What matters most right now — progress toward a goal, removing a blocker, or getting some relief?" Then call start_prioritization_flow as soon as they answer.
- If they asked to ADD items → proceed with adding via organize_thoughts or edit_board.
- If they just asked to SEE the board → ask "How can I help?" and let them lead.

Do NOT call organize_thoughts if the board already exists and the user just wants to focus or prioritize."""
        structured = {
            "clusters": clusters,
            "has_history": True,
            "is_empty_snapshot": False,
            "collapsed_by_default": True,
            "assistant_guidance": guidance,
        }
        logger.info("load_saved_board.retrieved", user_id=user_id, cluster_count=cluster_count)

    return mcp_types.CallToolResult(
        content=[],
        structuredContent=structured,
        _meta=meta,
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,  # Always produces widget
    handle=handle,
    read_only_hint=True,
    destructive_hint=False,
    open_world_hint=False,
))
