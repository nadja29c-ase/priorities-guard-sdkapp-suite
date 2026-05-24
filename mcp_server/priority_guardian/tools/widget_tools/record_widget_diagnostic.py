"""
record_widget_diagnostic tool for Priority Guardian MCP.

Private widget-only tool that receives diagnostic events from the widget
and logs them via structlog. Used by the Inc 89 fullscreen flash-revert
diagnostic instrumentation.

This tool exists because browser CSP blocks direct widget->backend HTTP
calls (Issue #85, still open as of May 2026). Routing through the MCP
bridge bypasses iframe CSP entirely.

Visibility: private (widget-only, hidden from LLM).
"""

import json

import structlog
from mcp import types as mcp_types

from ..base import ToolDefinition, ToolUsageError

logger = structlog.get_logger(__name__)

# Same byte limit as the (now-broken) HTTP endpoint enforced.
# Reject oversized payloads loudly so we know if the widget is shipping
# diagnostic data larger than expected.
MAX_DATA_BYTES = 2048

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "record_widget_diagnostic"

DESCRIPTION = (
    "Record a diagnostic event from the widget. Private widget-only tool — "
    "the model never sees or calls this. Used for production debugging of "
    "widget runtime behavior."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "event": {
            "type": "string",
            "minLength": 1,
            "maxLength": 100,
            "description": "Event name, e.g. 'mount', 'displayMode.change', 'set_globals'",
        },
        "data": {
            "type": "object",
            "description": "Event-specific structured data. Serialized form must not exceed 2048 bytes.",
            "additionalProperties": True,
        },
        "ts": {
            "type": "integer",
            "description": "Client-side timestamp (ms since epoch)",
        },
        "ua": {
            "type": "string",
            "maxLength": 500,
            "description": "User agent string",
        },
    },
    "required": ["event"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Record a widget diagnostic event.

    Validates the payload size and logs structurally via structlog at INFO
    level under event name `widget.diagnostic`. The log entry is shipped to
    Better Stack by the existing logging pipeline.

    Returns a minimal success response. The widget reporter does not parse
    the response — this is fire-and-forget from the widget's perspective.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (event, data, ts, ua)

    Returns:
        CallToolResult with minimal success indicator (no LLM-visible narration —
        this is a private widget-only tool; verbose text content is unnecessary
        surface area).
    """
    event_name = arguments.get("event")
    if not isinstance(event_name, str) or not event_name.strip():
        raise ToolUsageError("event field is required and must be a non-empty string")

    # Server-side length enforcement. Per ToolDefinition contract: the dispatcher
    # does NOT validate against input_schema, so schema maxLength is advisory only.
    # Handlers must enforce limits themselves.
    if len(event_name) > 100:
        raise ToolUsageError("event field exceeds 100 characters")

    data = arguments.get("data") or {}
    if not isinstance(data, dict):
        raise ToolUsageError("data field must be an object")

    # Enforce serialized size limit. Same threshold the HTTP endpoint used.
    serialized = json.dumps(data, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > MAX_DATA_BYTES:
        raise ToolUsageError(
            f"diagnostic data exceeds {MAX_DATA_BYTES} bytes — reduce payload size"
        )

    ts = arguments.get("ts")

    ua = arguments.get("ua")
    if ua is not None and not isinstance(ua, str):
        raise ToolUsageError("ua field must be a string when provided")
    # Truncate ua at 500 chars even if the schema bounds it — defense in depth.
    ua_truncated = ua[:500] if isinstance(ua, str) else None

    # PII minimization: log only the first 8 chars of user_id. Enough for cross-
    # session grouping during diagnostic analysis (e.g., "is this the same user
    # who reported the bug?") without putting the full identifier in logs.
    # If broader attribution is needed for abuse investigation, the correlation_id
    # is the join key — full user_id can be retrieved via auth audit trail.
    user_id_prefix = user_id[:8] if isinstance(user_id, str) else None

    # Log at INFO so it ships to Better Stack alongside other widget.diagnostic events.
    # Event name matches the original HTTP endpoint's structlog event so downstream
    # filters/dashboards keep working unchanged.
    logger.info(
        "widget.diagnostic",
        service="priority-guardian",
        user_id_prefix=user_id_prefix,
        correlation_id=correlation_id,
        diagnostic_event=event_name,
        data=data,
        client_ts=ts,
        user_agent=ua_truncated,
    )

    # Minimal response — no LLM-visible narration. Private tool; the widget
    # reporter does not read the response. structuredContent kept terse.
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="")],
        structuredContent={"ok": True},
    )


# ============================================================================
# Tool Definition
# ============================================================================

RECORD_WIDGET_DIAGNOSTIC = ToolDefinition(
    name=NAME,
    title="Record Widget Diagnostic",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,            # Does not produce widget output
    handle=handle,
    # Annotation rationale:
    # - read_only_hint=False: the tool writes a log entry. Even though the log
    #   is an append-only operational record (no user-visible state mutation),
    #   we mark it as not read-only to be honest about the side effect.
    # - destructive_hint=False: per project policy, destructiveHint applies only
    #   to permanent removal (deletes), not appends. Logging is not destructive.
    # - open_world_hint=False: no external system interaction; structlog ships
    #   to Better Stack via the existing logging pipeline (internal infrastructure).
    read_only_hint=False,
    destructive_hint=False,
    open_world_hint=False,
    widget_accessible=True,     # Widget calls this via callTool
    visibility="private",       # LLM cannot see or call
)
