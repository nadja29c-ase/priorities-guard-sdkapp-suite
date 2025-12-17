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

DESCRIPTION =DESCRIPTION = """
Retrieve the user's historical clusters with thought items from the database when you can not rely on your own memory. Whenever you are uncertain, you can rehydrate from the database with the use of this tool.

WHEN TO CALL THIS TOOL:
- At the start of EACH NEW conversation INVOLVING need for clarity / unorganized thoughts and tasks
- User asks to MERGE new thought items with their prior clusters from previous conversations
- User asks to VIEW, SHOW, or REVIEW their existing clusters
- You CAN NOT reliably recall prior user thoughts, clusters, or tasks from memory

DO NOT CALL THIS TOOL:
- You already called it earlier in THIS conversation AND NO NEW conversation started

RESPONSE FIELDS:
- clusters: Array of cluster objects with user's thought items (empty if none)
- has_history: Whether any prior snapshot of clustered thought items exists in the database
- is_empty_snapshot: True if a snapshot exists but contains no clusters
  (e.g., user previously cleared their clusters). Only meaningful when has_history=true.
- last_updated: ISO timestamp of last snapshot update (only present when has_history=true)

RESPONSE HANDLING:
- If has_history=false: User is starting fresh, proceed to collect thoughts with cluster_raw_thoughts tool
- If has_history=true and is_empty_snapshot=true: User had a session but cleared it, proceed to collect thoughts with cluster_raw_thoughts tool
- If has_history=true and is_empty_snapshot=false: Proceed based on user intent (see flows below)

FLOW A — User wants to ADD new thoughts (single turn, no user response between):
1. Call get_my_clusters → receive historical clusters
2. Merge new user thoughts with historical clusters → NO USER OUTPUT YET 
3. Call cluster_raw_thoughts with the COMPLETE MERGED SET
4. THEN respond to user WITH THE WIDGET showing updated merged clusters

FLOW B — User wants to VIEW existing clusters only:
1. Call get_my_clusters → receive historical clusters
2. Summarize ALL clusters for user (names, item counts)
3. Ask what they'd like to do (add, reorganize, delete)
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
