"""
Delete My Data Tool.

Permanently deletes the user's saved Clarity board (GDPR compliance).
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
Permanently deletes the user's saved Clarity board. This cannot be undone.
Use when user explicitly requests to delete their data.
Requires confirm=true to execute.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "confirm": {
            "type": "boolean",
            "description": "Must be true to confirm deletion. Required.",
        }
    },
    "required": ["confirm"]
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
    Delete user's saved Clarity board.

    Args:
        user_id: Authenticated user ID from JWT
        correlation_id: Request correlation ID for tracing
        arguments: { confirm: bool }

    Returns:
        CallToolResult with deletion status
    """
    logger.debug("delete_my_data.handle.start",
                user_id=user_id,
                correlation_id=correlation_id)

    # ============================================================
    # CONFIRMATION CHECK (defense against model regressions)
    # ============================================================
    confirm = arguments.get("confirm", False)

    if not confirm:
        logger.info("delete_my_data.rejected.no_confirm",
                   user_id=user_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Deletion requires explicit confirmation. Call again with confirm=true."
            )],
            structuredContent={
                "status": "rejected",
                "message": "Deletion requires explicit confirmation. Call again with confirm=true.",
                "assistant_guidance": "Deletion was not confirmed. Ask the user if they're sure they want to permanently delete their saved board.",
            },
            isError=False,  # Not an error, just rejected
        )

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
            content=[mcp_types.TextContent(
                type="text",
                text=message
            )],
            structuredContent={
                "status": "deleted",
                "message": message,
                "deleted": result.get("deleted"),
                "assistant_guidance": "The user's saved Clarity board has been permanently deleted. Acknowledge this briefly. If they ask about deleting their entire account, let them know this tool only deletes Clarity data — for full account deletion, they should contact clarity@priority-guard.com.",
            },
            _meta={
                "openai/toolInvocation/invoking": "Deleting your saved board...",
                "openai/toolInvocation/invoked": "Board deleted.",
            },
        )

    elif status == "no_data":
        logger.info("delete_my_data.no_data",
                   user_id=user_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=message
            )],
            structuredContent={
                "status": "no_data",
                "message": message,
                "assistant_guidance": "No saved board was found to delete. Let the user know their data is already clear.",
            },
            _meta={
                "openai/toolInvocation/invoking": "Checking for saved data...",
                "openai/toolInvocation/invoked": "No data found.",
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
# Self-register at import time
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
