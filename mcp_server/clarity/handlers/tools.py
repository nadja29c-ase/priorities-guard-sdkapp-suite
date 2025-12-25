"""
Tool call dispatcher for Clarity MCP.

Routes tool calls to the appropriate handler in the registry.
"""

import time

import structlog
from mcp import types as mcp_types

from ..tools import get_tool
from ..mcp_auth import (
    authenticate_request,
    UnauthorizedError,
    InsufficientScopeError,
    build_unauthorized_error,
    build_forbidden_error,
)

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
            _meta=build_unauthorized_error(),
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
            _meta=build_forbidden_error(required_scopes=e.required_scopes),
            isError=True,
        )
    auth_ms = (time.perf_counter() - start_auth) * 1000

    # ============================================================
    # DISPATCH TO TOOL HANDLER (with timing)
    # ============================================================
    logger.debug("tool.dispatch.executing",
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
