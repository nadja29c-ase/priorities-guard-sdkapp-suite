"""
log_client_error tool for Priority Guardian MCP.

TEMPORARY DIAGNOSTIC TOOL — REMOVE BEFORE STORE SUBMISSION.

Internal widget tool to capture client-side crash telemetry on iOS
via callTool. Logs all received fields to MCP server logs for debugging.
"""

import structlog
from mcp import types as mcp_types

from ..base import ToolDefinition

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "log_client_error"

DESCRIPTION = "Internal diagnostic tool used by the widget to log client-side crash telemetry during debugging."

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "error_name": {"type": "string"},
        "error_message": {"type": "string"},
        "stack": {"type": "string"},
        "component_stack": {"type": "string"},
        "ua": {"type": "string"},
        "phase": {"type": "string"},
    },
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Log client-side error telemetry from widget.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (error fields)

    Returns:
        CallToolResult with simple "logged" response
    """
    logger.error(
        "widget.client_error",
        correlation_id=correlation_id,
        user_id=user_id,
        error_name=arguments.get("error_name") or "(none)",
        error_message=arguments.get("error_message") or "(none)",
        stack=arguments.get("stack") or "(none)",
        component_stack=arguments.get("component_stack") or "(none)",
        ua=arguments.get("ua") or "(none)",
        phase=arguments.get("phase") or "(none)",
    )

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="logged"
        )],
        isError=False,
    )


# ============================================================================
# Tool Definition
# ============================================================================

LOG_CLIENT_ERROR = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,
    handle=handle,
    read_only_hint=True,
    destructive_hint=False,
    open_world_hint=False,
    widget_accessible=True,
    visibility="private",
)
