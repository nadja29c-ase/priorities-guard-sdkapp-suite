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
    logger.debug("load_saved_board.handle.start",
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

    # Always include widget metadata
    meta = {
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Loading your saved board...",
        "openai/toolInvocation/invoked": "Here's your saved Clarity board.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }

    # No snapshot exists at all - truly starting fresh
    if not has_snapshot:
        logger.info("load_saved_board.no_snapshot",
                   user_id=user_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="No previous brain dump found. Starting fresh."
            )],
            structuredContent={
                "clusters": [],
                "has_history": False,
                "is_empty_snapshot": False,  # No snapshot at all
                "saved_board_hash": None
            },
            _meta=meta,
        )

    cluster_count = len(clusters)

    # Extract content_hash for saved state detection
    saved_board_hash = cluster_data.get("content_hash")

    # Snapshot exists but is empty (user cleared their clusters)
    if cluster_count == 0:
        logger.info("load_saved_board.empty_snapshot",
                   user_id=user_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Found your previous session, but clusters were cleared."
            )],
            structuredContent={
                "clusters": [],
                "has_history": True,
                "is_empty_snapshot": True,
                "last_updated": cluster_data.get("created_at"),
                "saved_board_hash": saved_board_hash
            },
            _meta=meta,
        )

    # Snapshot exists with clusters
    logger.info("load_saved_board.retrieved",
               user_id=user_id,
               cluster_count=cluster_count)

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Found {cluster_count} cluster{'s' if cluster_count != 1 else ''} from your previous session."
        )],
        structuredContent={
            "clusters": clusters,
            "has_history": True,
            "is_empty_snapshot": False,
            "last_updated": cluster_data.get("created_at"),
            "saved_board_hash": saved_board_hash
        },
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
