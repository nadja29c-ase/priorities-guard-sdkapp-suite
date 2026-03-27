"""
Read Saved Board Tool.

Retrieves user's saved board data from the database WITHOUT widget rendering.
Self-registers at import time.

Use this tool when the LLM needs to read existing data to merge with new input.
For displaying the board to users, use load_saved_board instead.
"""

import structlog
from mcp import types as mcp_types

from .base import ToolDefinition
from . import register_tool
from ..persistence import get_cluster
from ..tool_logic import enrich_clusters

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "read_saved_board"

DESCRIPTION = """
Read user's saved Clarity board data from database.

WHEN TO CALL:
- ONCE AT THE BEGINNING OF EACH NEW CONVERSATION WITH THE USER involving Clarity and SAVED BOARD
- User wants to ADD/MODIFY their SAVED board at the beginning 
- User asks to MERGE new thought items with their prior SAVED BOARD from previous conversations
- Example: "Add X to my board" -> call read_saved_board -> merge -> call organize_thoughts
- You CAN NOT reliably recall what the saved board contained

DO NOT CALL:
- When user wants to VIEW/SHOW their board (use load_saved_board instead)
- You already called it earlier in THIS conversation AND NO NEW conversation started

FLOW:
1. Call read_saved_board -> receive clusters (no UI)
2. LLM merges new thoughts into returned clusters (no DB writes)
3. Call organize_thoughts with merged set -> widget renders

EMPTY STATE RESPONSE:
When no saved board exists:
{
  "clusters": []
}

SAVED STATE RESPONSE:
When saved board exists:
{
  "clusters": [...]
}
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
    Retrieve user's existing clusters (data only, no widget).

    Args:
        user_id: Authenticated user ID from JWT
        correlation_id: Request correlation ID for tracing
        arguments: Raw arguments from ChatGPT (unused - no parameters)

    Returns:
        CallToolResult with structuredContent containing:
        - clusters: List of cluster objects (empty if none)
        - has_history: Whether any prior snapshot exists
        - is_empty_snapshot: True if snapshot exists but has no clusters
    """
    logger.debug("read_saved_board.handle.start",
                user_id=user_id,
                correlation_id=correlation_id)

    # Fetch with exception handling - never crash on backend failures
    try:
        cluster_data = await get_cluster(
            user_id=user_id,
            correlation_id=correlation_id,
        )
    except Exception as e:
        logger.warning("read_saved_board.persistence_error",
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
        # Enrich clusters with sum_thought_items for LLM/widget use
        clusters = enrich_clusters(clusters)

    # No snapshot exists at all - truly starting fresh
    if not has_snapshot:
        logger.info("read_saved_board.no_snapshot",
                   user_id=user_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="No saved board found. Starting fresh."
            )],
            structuredContent={
                "clusters": [],
                "has_history": False,
                "is_empty_snapshot": False,
                "assistant_guidance": "No saved board exists. Tell the user briefly, then proceed with their request (e.g., 'Starting fresh — let me help you organize...').",
            },
            _meta={
                "saved_board_hash": None,
            },
        )

    cluster_count = len(clusters)

    # Extract content_hash for saved state detection
    saved_board_hash = cluster_data.get("content_hash")

    # Snapshot exists but is empty (user cleared their clusters)
    if cluster_count == 0:
        logger.info("read_saved_board.empty_snapshot",
                   user_id=user_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Found previous session, but clusters were cleared."
            )],
            structuredContent={
                "clusters": [],
                "has_history": True,
                "is_empty_snapshot": True,
                "assistant_guidance": "Board was cleared previously. Tell the user briefly, then proceed with their request (e.g., 'Your board is empty — let me help you organize...').",
            },
            _meta={
                "saved_board_hash": saved_board_hash,
            },
        )

    # Snapshot exists with clusters
    logger.info("read_saved_board.retrieved",
               user_id=user_id,
               cluster_count=cluster_count)

    # Extract cluster names for acknowledgment
    cluster_names = [c.get("cluster_name", "") for c in clusters if c.get("cluster_name")]

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Read {cluster_count} cluster{'s' if cluster_count != 1 else ''} from saved board."
        )],
        structuredContent={
            "clusters": clusters,
            "cluster_names": cluster_names,
            "has_history": True,
            "is_empty_snapshot": False,
            "assistant_guidance": f"""IMPORTANT: Acknowledge the board briefly BEFORE making changes. This gives the user feedback that you understood.

Examples:
- "Found your board — {cluster_count} clusters. Making the change now..."
- "Got your board with {', '.join(cluster_names[:3])}{'...' if len(cluster_names) > 3 else ''}. Let me [action]..."

Keep it to ONE short sentence, then proceed with the user's request.

IF MERGING NEW THOUGHTS AND RECLUSTERING: After reclustering, the board will have no priorities — this is correct and expected. Tell the user their board has been reorganized and they can set priorities again when ready.""",
        },
        _meta={
            "saved_board_hash": saved_board_hash,
            "openai/toolInvocation/invoking": "Loading your board...",
            "openai/toolInvocation/invoked": "Board loaded.",
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,  # Never produces widget
    handle=handle,
    read_only_hint=True,
    destructive_hint=False,
    open_world_hint=False,
))
