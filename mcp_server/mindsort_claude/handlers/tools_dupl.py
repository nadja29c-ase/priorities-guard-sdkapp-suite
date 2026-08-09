# (duplicate) — exists because it imports platform-specific mcp_auth.
#
# !! ITS CONTENTS ARE NOT A COPY. Verified 2026-08-09 by symbol-level sweep: this
# file has diverged STRUCTURALLY from the source named below, and not every
# divergence is documented. Do not assume a symbol here behaves as its namesake
# does there — and note that a symbol may be ABSENT here entirely. That is exactly
# how A22 happened: BearerAuthMiddleware dropped JWT validation, scope enforcement
# and the 413 guard while this header claimed a config-only difference.
# See doc/DUPL_DIVERGENCE_SWEEP_2026-08-09.md.
# Mirrors mcp_server/clarity/handlers/tools.py. Maintain alongside; consolidate only on demonstrated churn.
"""
Tool call dispatcher for MindSort Claude MCP.

Routes tool calls to the appropriate handler in the registry.
"""

import time

import structlog
from mcp import types as mcp_types

from mcp_server.clarity.tools import get_tool
from mcp_server.mindsort_claude.mcp_auth_dupl import (
    authenticate_request,
    UnauthorizedError,
    InsufficientScopeError,
    build_unauthorized_meta,
    build_forbidden_meta,
)
from mcp_server.mindsort_claude.response_adapter_dupl import adapt_tool_result
# Widget-0b: inject Claude widget URI for widget-producing tool results
from mcp_server.mindsort_claude.tools_list_dupl import _WIDGET_PRODUCING_TOOLS
from mcp_server.mindsort_claude.handlers.resources_dupl import WIDGET_URI

logger = structlog.get_logger(__name__)


async def call_tool_request(req: mcp_types.CallToolRequest) -> mcp_types.CallToolResult:
    """
    Handle tool calls with authentication and dispatch to registry.

    Args:
        req: MCP CallToolRequest with tool name, arguments, and metadata

    Returns:
        CallToolResult from the tool handler or error response
    """
    start_total = time.perf_counter()

    name = req.params.name
    arguments = req.params.arguments or {}
    meta = getattr(req.params, '_meta', None) or {}

    logger.debug("tool.dispatch.received",
                tool_name=name,
                argument_keys=list(arguments.keys()))

    # ============================================================
    # LOOKUP TOOL IN REGISTRY
    # ============================================================
    tool = get_tool(name)
    if tool is None:
        logger.warning("tool.dispatch.unknown", tool_name=name)
        return mcp_types.CallToolResult(
            content=[
                mcp_types.TextContent(
                    type="text",
                    text=f"Unknown tool: {name}",
                )
            ],
            isError=True,
        )

    # ============================================================
    # AUTHENTICATION (with timing)
    # ============================================================
    start_auth = time.perf_counter()
    try:
        auth_context = await authenticate_request(name, meta)
        user_id = auth_context["user_id"]
        correlation_id = auth_context["correlation_id"]

    except UnauthorizedError:
        auth_ms = (time.perf_counter() - start_auth) * 1000
        logger.warning("tool.dispatch.unauthorized",
                      tool_name=name,
                      auth_ms=round(auth_ms, 1))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Authentication required. Please connect your account."
            )],
            _meta=build_unauthorized_meta(),
            isError=True,
        )
    except InsufficientScopeError as e:
        auth_ms = (time.perf_counter() - start_auth) * 1000
        logger.warning("tool.dispatch.forbidden",
                      tool_name=name,
                      required_scopes=e.required_scopes,
                      auth_ms=round(auth_ms, 1))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Insufficient permissions. Please reconnect your account."
            )],
            _meta=build_forbidden_meta(),
            isError=True,
        )
    auth_ms = (time.perf_counter() - start_auth) * 1000

    # ============================================================
    # DISPATCH TO TOOL HANDLER (with timing)
    # ============================================================
    logger.info("tool.dispatch.executing",
                tool_name=name,
                user_id=user_id,
                correlation_id=correlation_id)

    start_tool = time.perf_counter()
    try:
        result = await tool.handle(user_id, correlation_id, arguments)
    except Exception:
        logger.exception("tool.dispatch.unexpected_error",
                        tool_name=name,
                        user_id=user_id,
                        correlation_id=correlation_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Something went wrong. Please try again later."
            )],
            isError=True,
        )
    tool_ms = (time.perf_counter() - start_tool) * 1000

    # Runtime type guard: ensure handler returned CallToolResult
    if not isinstance(result, mcp_types.CallToolResult):
        logger.error("tool.dispatch.invalid_return_type",
                    tool_name=name,
                    user_id=user_id,
                    correlation_id=correlation_id,
                    actual_type=type(result).__name__)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Internal error: tool returned invalid response type."
            )],
            isError=True,
        )

    # ============================================================
    # ADAPT RESPONSE FOR CLAUDE (Widget-0b: inject-by-intent)
    # ============================================================
    # Capture whether the result had a widget URI BEFORE the adapter strips it.
    # Inject-by-intent: only inject Claude URI if the result HAD a widget on entry.
    # This preserves each handler path's existing widget intent exactly.
    had_widget_on_entry = (
        result.meta is not None
        and isinstance(result.meta.get("ui"), dict)
        and "resourceUri" in result.meta["ui"]
    )

    result = adapt_tool_result(result, tool_name=name)

    # Widget-0b: inject Claude widget URI for widget-producing tools
    # that had a widget URI on entry (pure translation, no behavior change).
    if name in _WIDGET_PRODUCING_TOOLS and had_widget_on_entry:
        # Build new _meta with Claude widget URI injected
        if result.meta is None:
            new_meta = {"ui": {"resourceUri": WIDGET_URI}}
        else:
            new_meta = dict(result.meta)
            if "ui" not in new_meta:
                new_meta["ui"] = {}
            else:
                new_meta["ui"] = dict(new_meta["ui"])
            new_meta["ui"]["resourceUri"] = WIDGET_URI

        result = mcp_types.CallToolResult(
            content=result.content,
            structuredContent=result.structuredContent,
            isError=result.isError,
            _meta=new_meta,
        )

    # ============================================================
    # LOG TIMING BREAKDOWN
    # ============================================================
    total_ms = (time.perf_counter() - start_total) * 1000

    logger.info("tool.timing",
                tool_name=name,
                auth_ms=round(auth_ms, 1),
                tool_ms=round(tool_ms, 1),
                total_ms=round(total_ms, 1),
                user_id=user_id)

    return result
