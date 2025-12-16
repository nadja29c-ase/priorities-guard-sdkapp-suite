"""
Get My Clusters Tool.

Read-only tool to retrieve user's existing cluster snapshot from the database.
Self-registers at import time.
"""

import structlog
from mcp import types as mcp_types

from .base import ToolDefinition
from . import register_tool
from ..persistence import get_cluster

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "get_my_clusters"

DESCRIPTION = """
Retrieve the user's current persisted brain dump clusters from the database.

PURPOSE:
The database is the source of truth. Your conversation context is a cache.
Use this tool to rehydrate state whenever you're uncertain about the current state.

CALL THIS TOOL WHEN:
- This is the start of a new conversation involving brain dump / clarity / thoughts
- You are unsure whether you have the user's full previous brain dump
- The conversation may have been long enough that context could be truncated
- The user asks to see, continue, add to, or review their existing brain dump
- The user says "what do I have?", "show my clusters", "where were we?"

DO NOT CALL THIS TOOL IF:
- You already retrieved clusters earlier in the same conversation
- You just persisted clusters via cluster_raw_thoughts (you know the current state)
- You are certain the full state is present in your context

RESPONSE FIELDS:
- clusters: Array of cluster objects (empty if none)
- has_history: Whether any prior snapshot exists in the database
- is_empty_snapshot: True if a snapshot exists but contains no clusters
  (e.g., user previously cleared their brain dump). Only meaningful when has_history=true.
- last_updated: ISO timestamp of last snapshot update (only present when has_history=true)

RESPONSE HANDLING:
- If has_history=false: User is starting fresh, proceed to collect thoughts
- If has_history=true and is_empty_snapshot=true: User had a session but cleared it
- If has_history=true and is_empty_snapshot=false: Show user summary of clusters, ask what to add/change

═══════════════════════════════════════════════════════════════════════════════
CRITICAL: TWO-TOOL CHAINING WORKFLOW
═══════════════════════════════════════════════════════════════════════════════

If user provided new thoughts to organize, you MUST complete BOTH tool calls in ONE turn.
Do NOT respond to the user between get_my_clusters and cluster_raw_thoughts.

CORRECT FLOW (single turn, no user response between):
1. Call get_my_clusters → receive historical clusters
2. Merge new user thoughts with historical clusters
3. Call cluster_raw_thoughts with the COMPLETE merged set
4. THEN respond to user with the widget

WRONG FLOW (breaks the experience):
1. Call get_my_clusters → receive historical clusters
2. Respond to user with text ← WRONG: user sees no widget, state is confused
3. Wait for user input ← WRONG: user has to prompt again

MERGE LOGIC (when has_history=true AND user has new thoughts):
- You have: historical clusters (from this tool) + new thoughts (from user)
- Merge new thoughts INTO existing clusters if they fit thematically
- Create NEW clusters for thoughts that don't fit existing ones
- Send ALL clusters (historical + new) to cluster_raw_thoughts
- NEVER drop historical clusters unless user explicitly asks

EXAMPLE:
- get_my_clusters returns 4 clusters
- User gave 7 new thoughts
- You merge: some thoughts go into existing clusters, others form new clusters
- You call cluster_raw_thoughts with 6 total clusters (merged result)
- User sees widget with 6 clusters

If has_history=false AND user has new thoughts:
1. Cluster the new thoughts into logical groups
2. Call cluster_raw_thoughts immediately (same turn)
3. THEN respond to user with the widget

═══════════════════════════════════════════════════════════════════════════════

The guarantee: Whenever you are uncertain, you can rehydrate from the database.
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
    arguments: dict,  # Intentionally unused - read-only tool with no parameters
) -> mcp_types.CallToolResult:
    """
    Retrieve user's existing clusters.

    Args:
        user_id: Authenticated user ID from JWT
        correlation_id: Request correlation ID for tracing
        arguments: Raw arguments from ChatGPT (unused - this tool takes no input)

    Returns:
        CallToolResult with structuredContent containing:
        - clusters: List of cluster objects (empty if none)
        - has_history: Whether any prior snapshot exists
        - is_empty_snapshot: True if snapshot exists but has no clusters
        - last_updated: ISO timestamp of last update (if has_history=true)
    """
    logger.debug("get_my_clusters.handle.start",
                user_id=user_id,
                correlation_id=correlation_id)

    # Fetch with exception handling - never crash on backend failures
    try:
        cluster_data = await get_cluster(
            user_id=user_id,
            correlation_id=correlation_id,
        )
    except Exception as e:
        logger.warning("get_my_clusters.persistence_error",
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

    # No snapshot exists at all - truly starting fresh
    if not has_snapshot:
        logger.info("get_my_clusters.no_snapshot",
                   user_id=user_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="No previous brain dump found. Starting fresh."
            )],
            structuredContent={
                "clusters": [],
                "has_history": False,
                "is_empty_snapshot": False  # No snapshot at all
            }
        )

    cluster_count = len(clusters)

    # Snapshot exists but is empty (user cleared their clusters)
    if cluster_count == 0:
        logger.info("get_my_clusters.empty_snapshot",
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
                "last_updated": cluster_data.get("created_at")
            }
        )

    # Snapshot exists with clusters
    logger.info("get_my_clusters.retrieved",
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
            "last_updated": cluster_data.get("created_at")
        }
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,  # No widget - data retrieval only
    handle=handle,
))
