"""
update_deliverable tool for Priority Guardian MCP.

Private widget-only tool for updating deliverables (toggle done, rename).
"""

import asyncio

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_put
from ..base import ToolDefinition, ToolUsageError
from ..get_priorities import _normalize_priority
from .constants import WIDGET_URI

logger = structlog.get_logger(__name__)

# Timeout for backend calls (seconds) — must be under ChatGPT's ~10s window
TIMEOUT_S = 8.0


async def _call_with_timeout(coro, op_name: str, correlation_id: str):
    """Wrap a coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning(
            "tool.update_deliverable.timeout",
            correlation_id=correlation_id,
            op_name=op_name,
            timeout=TIMEOUT_S,
        )
        raise ToolUsageError(f"{op_name} timed out. Please try again.")

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "update_deliverable"

DESCRIPTION = "Update a deliverable (toggle done or rename, widget-only)."

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "deliverable_id": {
            "type": "string",
            "description": "Deliverable ID (UUID)",
        },
        "name": {
            "type": "string",
            "description": "New deliverable name (max 200 chars)",
            "maxLength": 200,
        },
        "done": {
            "type": "boolean",
            "description": "New completion status",
        },
    },
    "required": ["deliverable_id"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Update a deliverable.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (deliverable_id, optional name/done)

    Returns:
        CallToolResult with fresh priority list
    """
    logger.info(
        "tool.update_deliverable.start",
        correlation_id=correlation_id,
        user_id=user_id,
    )

    # Validate required fields
    deliverable_id = arguments.get("deliverable_id")
    if not deliverable_id:
        raise ToolUsageError("deliverable_id is required")

    # Build update payload
    payload = {}
    if "name" in arguments and arguments["name"] is not None:
        payload["name"] = arguments["name"]
    if "done" in arguments and arguments["done"] is not None:
        payload["done"] = arguments["done"]

    if not payload:
        raise ToolUsageError("No fields provided to update.")

    # Call backend with timeout - mutation endpoints return full priority list
    import httpx
    try:
        response = await _call_with_timeout(
            backend_put(
                f"/api/priority-guardian/deliverables/{deliverable_id}",
                payload,
                user_id,
                correlation_id
            ),
            "Update deliverable",
            correlation_id,
        )
    except ToolUsageError:
        raise  # Re-raise timeout errors
    except Exception as e:
        logger.error(
            "tool.update_deliverable.backend_error",
            correlation_id=correlation_id,
            error=str(e),
        )
        if isinstance(e, httpx.HTTPStatusError):
            if e.response.status_code == 404:
                raise ToolUsageError("Deliverable not found.")
        raise ToolUsageError("Failed to update deliverable. Please try again.")

    # Use response directly - backend returns full priority list
    data = response.get("data", {})
    raw_priorities = data.get("priorities", [])
    google_connection = data.get("google_connection", {"connected": False})
    available_keywords = data.get("available_keywords", [])

    priorities = [_normalize_priority(p) for p in raw_priorities]

    logger.info(
        "tool.update_deliverable.success",
        correlation_id=correlation_id,
        user_id=user_id,
        deliverable_id=deliverable_id,
    )

    structured_content = {
        "success": True,
        "data": {
            "google_connected": google_connection.get("connected", False),
            "priorities": priorities,
            "available_keywords": available_keywords,
        },
        "_meta": {
            "openai/outputTemplate": WIDGET_URI,
        },
        "assistant_guidance": "Deliverable updated. The dashboard reflects the changes.",
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Deliverable updated."
        )],
        structuredContent=structured_content,
    )


# ============================================================================
# Tool Definition
# ============================================================================

UPDATE_DELIVERABLE = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,
    handle=handle,
    read_only_hint=False,
    destructive_hint=False,
    open_world_hint=False,
    widget_accessible=True,
    visibility="private",
)
