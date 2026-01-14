"""
Tool call dispatcher for Sharpen MCP.

Routes tool calls to the appropriate handler in the registry.
No authentication required - Sharpen is stateless.
"""

import time

import structlog
from mcp import types as mcp_types

from ..tools import get_tool

logger = structlog.get_logger(__name__)


async def call_tool_request(req: mcp_types.CallToolRequest) -> mcp_types.CallToolResult:
    """
    Handle tool calls and dispatch to registry.

    No authentication - Sharpen is stateless with noauth security scheme.

    Args:
        req: MCP CallToolRequest with tool name and arguments

    Returns:
        CallToolResult from the tool handler or error response
    """
    start_total = time.perf_counter()

    name = req.params.name
    arguments = req.params.arguments or {}

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
    # DISPATCH TO TOOL HANDLER (with timing)
    # ============================================================
    logger.debug("tool.dispatch.executing", tool_name=name)

    start_tool = time.perf_counter()
    try:
        result = await tool.handle(arguments)
    except Exception:
        logger.exception("tool.dispatch.unexpected_error", tool_name=name)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Something went wrong. Please try again later."
            )],
            isError=True,
        )
    tool_ms = (time.perf_counter() - start_tool) * 1000

    # ============================================================
    # LOG TIMING
    # ============================================================
    total_ms = (time.perf_counter() - start_total) * 1000

    logger.info("tool.timing",
                tool_name=name,
                tool_ms=round(tool_ms, 1),
                total_ms=round(total_ms, 1))

    return result
