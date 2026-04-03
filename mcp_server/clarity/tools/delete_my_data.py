"""
Delete My Data Tool.

Permanently deletes the user's saved MindSort AI board (GDPR compliance).
Self-registers at import time.

OpenAI Requirement (Compliance Master C38):
    "Respect deletion requests promptly" - Data-deletion mechanism required
    for SDK app submission.
"""

import structlog
from mcp import types as mcp_types

from .base import ToolDefinition
from . import register_tool
from ..persistence import delete_cluster

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "delete_my_data"

DESCRIPTION = """
Permanently deletes the user's saved MindSort AI board. This cannot be undone.

BEFORE CALLING: Confirm with the user what will be deleted — their saved board with all clusters, thought items, tags, and priorities. Only call after they confirm.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
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
    Delete user's saved MindSort AI board.

    Args:
        user_id: Authenticated user ID from JWT
        correlation_id: Request correlation ID for tracing
        arguments: { confirm: bool }

    Returns:
        CallToolResult with deletion status
    """
    logger.info("delete_my_data.handle.start",
                user_id=user_id,
                correlation_id=correlation_id)

    # ============================================================
    # CALL BACKEND TO DELETE
    # ============================================================
    result = await delete_cluster(user_id=user_id, correlation_id=correlation_id)

    status = result.get("status", "error")
    message = result.get("message", "Unknown error occurred.")

    # ============================================================
    # BUILD RESPONSE BASED ON STATUS
    # ============================================================
    if status == "deleted":
        logger.info("delete_my_data.success",
                   user_id=user_id,
                   deleted=result.get("deleted"))
        return mcp_types.CallToolResult(
            content=[],
            structuredContent={
                "status": "deleted",
                "success": True,
                "deleted": result.get("deleted"),
                "assistant_guidance": "DELETION SUCCESSFUL. The user's saved MindSort AI board has been permanently deleted. Tell them: 'Your board has been deleted.' Do NOT call delete_my_data again. If they ask about deleting their entire account, let them know this tool only deletes MindSort AI data — for full account deletion, they should contact mindsort@priority-guard.com.",
            },
            _meta={
                "openai/toolInvocation/invoking": "Deleting your saved board...",
                "openai/toolInvocation/invoked": "Board deleted successfully.",
            },
        )

    elif status == "no_data":
        # Treat as success - user either had no data, or LLM called twice after deletion
        # Either way, user's MindSort AI data is now clear
        logger.info("delete_my_data.no_data",
                   user_id=user_id)
        return mcp_types.CallToolResult(
            content=[],
            structuredContent={
                "status": "deleted",
                "success": True,
                "assistant_guidance": "DELETION COMPLETE. The user's MindSort AI Board data is now clear. Tell them: 'Your MindSort AI Board data has been deleted.' Do NOT call delete_my_data again. If they ask about deleting their entire account, let them know this tool only deletes the MindSort AI Board data — for full account deletion, they should contact mindsort@priority-guard.com.",
            },
            _meta={
                "openai/toolInvocation/invoking": "Deleting your saved board...",
                "openai/toolInvocation/invoked": "Data deleted.",
            },
        )

    else:  # error or unknown status
        logger.error("delete_my_data.error",
                    user_id=user_id,
                    status=status,
                    message=message)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=message
            )],
            structuredContent={
                "status": "error",
                "message": message,
                "assistant_guidance": "Deletion failed. Apologize briefly and suggest the user try again later.",
            },
            isError=True,
        )


# ============================================================================
# Self-register at import time. Annotations.
# ============================================================================

register_tool(ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,  # No widget output
    handle=handle,
    widget_accessible=False,  # Not callable from widget
    # OpenAI compliance annotations
    read_only_hint=False,  # Mutates state (deletes data)
    destructive_hint=True,  # Permanently deletes user data
    open_world_hint=False,  # Only mutates own backend, not external systems
))
