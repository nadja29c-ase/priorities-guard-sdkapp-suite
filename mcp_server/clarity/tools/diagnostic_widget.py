"""
Diagnostic Widget Tool.

INTERNAL DIAGNOSTIC ONLY - for isolating widget render failures.

Side-effect-free tool that produces a tiny widget (<10KB) with identical
_meta structure to organize_thoughts. Used to determine if widget render
failures are size-driven vs. host-side vs. app-payload.

Self-registers at import time.
"""

import structlog
from mcp import types as mcp_types

from .base import ToolDefinition
from . import register_tool

logger = structlog.get_logger(__name__)

# ============================================================================
# Diagnostic Widget Configuration
# ============================================================================
# Must match the serving path in handlers/resources.py
DIAGNOSTIC_WIDGET_VERSION = "1"
DIAGNOSTIC_WIDGET_URI = f"ui://widget/diagnostic-tiny.html?v={DIAGNOSTIC_WIDGET_VERSION}"

# ============================================================================
# Tool Metadata
# ============================================================================

DESCRIPTION = """INTERNAL DIAGNOSTIC TOOL - DO NOT USE IN NORMAL CONVERSATION.

This tool is for diagnosing widget render failures. It produces a tiny (<10KB) widget
with identical _meta structure to organize_thoughts. If this widget renders but
organize_thoughts doesn't, the issue is bundle size. If neither renders, the issue
is host-side or app-payload.

Call this tool ONLY when explicitly instructed to run widget diagnostics.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "test_id": {
            "type": "string",
            "description": "Optional test identifier for correlation in logs",
        },
    },
    "additionalProperties": False,
}

# No scopes required - diagnostic tool, read-only
REQUIRED_SCOPES: list[str] = []


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Handle diagnostic_widget tool call.

    Side-effect-free: no DB writes, no external calls, no user data.
    Returns structuredContent + _meta identical in shape to organize_thoughts.

    Args:
        user_id: Authenticated user ID from JWT
        correlation_id: Request correlation ID for tracing
        arguments: Raw arguments from ChatGPT (only test_id optional)

    Returns:
        CallToolResult with diagnostic data and widget metadata
    """
    test_id = arguments.get("test_id", "default")

    logger.info(
        "diagnostic_widget.handle",
        user_id=user_id,
        correlation_id=correlation_id,
        test_id=test_id,
    )

    # ============================================================
    # BUILD RESPONSE
    # ============================================================
    # structuredContent mirrors organize_thoughts shape but with diagnostic data
    structured_content = {
        "success": True,
        "diagnostic": True,
        "test_id": test_id,
        "widget_uri": DIAGNOSTIC_WIDGET_URI,
        "message": "Diagnostic widget returned. Check if widget renders.",
    }

    # _meta structure MUST match organize_thoughts exactly
    # This is the structural clone requirement from inc_91
    meta = {
        "ui": {"resourceUri": DIAGNOSTIC_WIDGET_URI},
        "openai/outputTemplate": DIAGNOSTIC_WIDGET_URI,
        "openai/toolInvocation/invoking": "Running widget diagnostic...",
        "openai/toolInvocation/invoked": "Diagnostic complete.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }

    logger.info(
        "diagnostic_widget.complete",
        user_id=user_id,
        correlation_id=correlation_id,
        test_id=test_id,
        widget_uri=DIAGNOSTIC_WIDGET_URI,
    )

    return mcp_types.CallToolResult(
        content=[],
        structuredContent=structured_content,
        _meta=meta,
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="_diagnostic_tiny_widget",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=DIAGNOSTIC_WIDGET_URI,
    handle=handle,
    # OpenAI compliance annotations - DIAGNOSTIC TOOL
    read_only_hint=True,   # Side-effect-free
    destructive_hint=False,  # No data modification
    open_world_hint=False,  # No external systems
))
