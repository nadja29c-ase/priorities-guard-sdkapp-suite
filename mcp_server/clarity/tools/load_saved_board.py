"""
Load Saved Board Tool.

Retrieves and DISPLAYS user's saved board with widget rendering.
Self-registers at import time.

For data-only access (no widget), use read_saved_board instead.
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
Load and DISPLAY user's saved Clarity board with widget.

WHEN TO CALL:
- User asks to SEE/SHOW/VIEW/DISPLAY their saved board
- Example: "Show my board", "What's on my board?"

DO NOT CALL:
- When user wants to ADD items (use read_saved_board instead)

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

    # Fetch with exception handling - never crash on backend failures
    try:
        cluster_data = await get_cluster(
            user_id=user_id,
            correlation_id=correlation_id,
        )
    except Exception as e:
        logger.warning("load_saved_board.persistence_error",
                      user_id=user_id,
                      error=str(e))
        cluster_data = None

    # Extract clusters with defensive defaults
    # Defense in depth: check dict type in case persistence layer returns unexpected type
    clusters = []
    has_snapshot = cluster_data is not None and isinstance(cluster_data, dict)
    if has_snapshot:
        inner_data = cluster_data.get("cluster_data") or {}
        clusters = inner_data.get("clusters") or []
        # Enrich clusters with sum_thought_items for widget display
        clusters = enrich_clusters(clusters)

    # Always include widget metadata
    meta = {
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

    # Determine state and build response
    cluster_count = len(clusters)
    saved_board_hash = cluster_data.get("content_hash") if has_snapshot else None

    # Compute guidance based on state
    if not has_snapshot:
        # No snapshot exists at all - truly starting fresh
        message = "No previous brain dump found. Starting fresh."
        guidance = """No saved board found — this is a fresh start.

Ask if they'd like to create a new Clarity Board. Something warm like: "Ready for your brain dump session when you are!" Keep it light and inviting."""
        structured = {
            "clusters": [],
            "has_history": False,
            "is_empty_snapshot": False,
            "saved_board_hash": None,
            "assistant_guidance": guidance,
        }
        logger.info("load_saved_board.no_snapshot", user_id=user_id)

    elif cluster_count == 0:
        # Snapshot exists but is empty (user cleared their clusters)
        message = "Found your previous session, but clusters were cleared."
        guidance = """Previous session found but it's empty — they cleared it before.

Ask if they'd like to start a new Clarity Board. Something warm like: "Ready for your brain dump session when you are!" Keep it light and inviting."""
        structured = {
            "clusters": [],
            "has_history": True,
            "is_empty_snapshot": True,
            "last_updated": cluster_data.get("created_at"),
            "saved_board_hash": saved_board_hash,
            "assistant_guidance": guidance,
        }
        logger.info("load_saved_board.empty_snapshot", user_id=user_id)

    else:
        # Snapshot exists with clusters
        message = f"Found {cluster_count} cluster{'s' if cluster_count != 1 else ''} from your previous session."
        guidance = """Board loaded with existing clusters.

Ask how you can help: "Now that you see your board, how would you like me to assist you?" Let them lead — they might want to add, edit, prioritize, or just reflect."""
        structured = {
            "clusters": clusters,
            "has_history": True,
            "is_empty_snapshot": False,
            "last_updated": cluster_data.get("created_at"),
            "saved_board_hash": saved_board_hash,
            "assistant_guidance": guidance,
        }
        logger.info("load_saved_board.retrieved", user_id=user_id, cluster_count=cluster_count)

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=message
        )],
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
))
