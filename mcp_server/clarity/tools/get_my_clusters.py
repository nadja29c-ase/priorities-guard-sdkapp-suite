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

RESPONSE HANDLING:
- If has_history=true: Show user summary of their clusters, ask what to add/change
- If has_history=false: Tell user they're starting fresh, proceed to collect thoughts

The guarantee: Whenever you are uncertain, you can rehydrate from the database.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False
}

REQUIRED_SCOPES = ["clarity.write"]

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
        arguments: Raw arguments from ChatGPT (empty for this tool)

    Returns:
        CallToolResult with:
        - clusters: List of cluster objects (empty if none)
        - has_history: Boolean indicating if user has existing data
        - last_updated: ISO timestamp of last update (if has_history)
    """
    logger.debug("get_my_clusters.handle.start",
                user_id=user_id,
                correlation_id=correlation_id)

    cluster_data = await get_cluster(user_id)

    if cluster_data is None:
        logger.info("get_my_clusters.no_history",
                   user_id=user_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="No existing clusters found. User is starting fresh."
            )],
            structuredContent={
                "clusters": [],
                "has_history": False
            }
        )

    clusters = cluster_data.get("cluster_data", {}).get("clusters", [])
    cluster_count = len(clusters)

    logger.info("get_my_clusters.retrieved",
               user_id=user_id,
               cluster_count=cluster_count)

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Retrieved {cluster_count} existing clusters."
        )],
        structuredContent={
            "clusters": clusters,
            "has_history": True,
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
