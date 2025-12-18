"""
Load Saved Board Tool.

Retrieves user's explicitly saved board from the database with widget rendering.
Self-registers at import time.

NOTE: As of Increment 12, this is separate from organize_thoughts.
      organize_thoughts is ephemeral (no DB). This tool loads saved state.
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
Load/Read user's previously saved Clarity board from the database.

WHEN TO CALL:
- User asks to see/show/load/retrieve their saved (clarity) board -> dispay saved board with widget
- Start of new conversation when user wants to continue from saved state and add to the saved board
f.e. User says at the beginning of a new conversation "Add this..to my board" -> read saved board, merge new thoughts, re-cluster, show updated board with widget

EMPTY STATE RESPONSE:
When no saved board exists:
{
  "clusters": [],
  "saved_board_hash": null
}

Example FLows:
FLOW A — User wants to ADD new thoughts to saved board:
1. Call load_saved_board(render_widget=false) → receive historical clusters (NO WIDGET)
2. Merge new user thoughts with historical clusters
3. Call organize_thoughts with the COMPLETE MERGED SET → widget renders
4. Respond to user with the organized board

FLOW B — User wants to VIEW existing saved clusters only:
1. Call load_saved_board → load saved clusters with Widget
2. Ask what they'd like to do (add, reorganize, delete)

SAVED STATE RESPONSE:
When saved board exists:
{
  "clusters": [...],
  "saved_board_hash": "abc123..."
}
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "render_widget": {
            "type": "boolean",
            "description": "Required. True to render widget, false for text-only response."
        }
    },
    "required": ["render_widget"],
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
    Retrieve user's existing clusters.

    Args:
        user_id: Authenticated user ID from JWT
        correlation_id: Request correlation ID for tracing
        arguments: Raw arguments from ChatGPT
            - render_widget (bool, required): True to render widget, false for text-only

    Returns:
        CallToolResult with structuredContent containing:
        - clusters: List of cluster objects (empty if none)
        - has_history: Whether any prior snapshot exists
        - is_empty_snapshot: True if snapshot exists but has no clusters
        - last_updated: ISO timestamp of last update (if has_history=true)
    """
    render_widget = arguments.get("render_widget", False)  # Fallback for safety

    logger.debug("load_saved_board.handle.start",
                user_id=user_id,
                correlation_id=correlation_id,
                render_widget=render_widget)

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

    # Build widget metadata only if render_widget is True
    meta = None
    if render_widget:
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
    widget_uri=WIDGET_URI,  # Widget controlled by required render_widget parameter
    handle=handle,
))
