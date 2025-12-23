"""
Tool call dispatcher for Clarity MCP.

Routes tool calls to the appropriate handler in the registry.
"""

import json

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
    # AUTHENTICATION
    # ============================================================
    try:
        auth_context = await authenticate_request(name, meta)
        user_id = auth_context["user_id"]
        correlation_id = auth_context["correlation_id"]

        logger.info("tool.dispatch.authenticated",
                    user_id=user_id,
                    correlation_id=correlation_id,
                    tool_name=name)

    except UnauthorizedError:
        logger.warning("tool.dispatch.unauthorized", tool_name=name)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=json.dumps(build_unauthorized_error())
            )],
            isError=True,
        )
    except InsufficientScopeError as e:
        logger.warning("tool.dispatch.forbidden",
                      tool_name=name,
                      required_scopes=e.required_scopes)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=json.dumps(build_forbidden_error(
                    required_scopes=e.required_scopes,
                    actual_scopes=e.actual_scopes
                ))
            )],
            isError=True,
        )

    # ============================================================
    # DISPATCH TO TOOL HANDLER
    # ============================================================
    logger.debug("tool.dispatch.executing",
                tool_name=name,
                user_id=user_id,
                correlation_id=correlation_id)

    try:
        return await tool.handle(user_id, correlation_id, arguments)
    except Exception as e:
        logger.error("tool.dispatch.unexpected_error",
                    tool_name=name,
                    user_id=user_id,
                    correlation_id=correlation_id,
                    error=str(e))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Something went wrong. Please try again."
            )],
            isError=True,
        )
