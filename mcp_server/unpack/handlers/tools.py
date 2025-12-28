"""
Tool call dispatcher for Unpack MCP.

Routes tool calls to the appropriate handler in the registry.
No authentication required (Unpack uses noauth).
"""

import time
import uuid

import structlog
from mcp import types as mcp_types

from ..tools import get_tool
from ..tools.base import ToolUsageError

logger = structlog.get_logger(__name__)


async def call_tool_request(req: mcp_types.CallToolRequest) -> mcp_types.CallToolResult:
    """
    Handle tool calls and dispatch to registry.

    No authentication - Unpack uses noauth.
    Handlers receive empty user_id and generated correlation_id.

    Args:
        req: MCP CallToolRequest with tool name, arguments, and metadata

    Returns:
        CallToolResult from the tool handler or error response
    """
    start_total = time.perf_counter()

    name = req.params.name
    arguments = req.params.arguments or {}

    # Generate correlation ID for request tracing
    correlation_id = str(uuid.uuid4())

    logger.debug("tool.dispatch.received",
                tool_name=name,
                correlation_id=correlation_id,
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
    logger.debug("tool.dispatch.executing",
                tool_name=name,
                correlation_id=correlation_id)

    start_tool = time.perf_counter()
    try:
        # No auth - pass empty user_id
        result = await tool.handle("", correlation_id, arguments)

    except ToolUsageError as e:
        # Intentional rejection - surface message verbatim
        # Used for: input validation, guardrails, business rules
        logger.info("tool.dispatch.rejected",
                    tool_name=name,
                    correlation_id=correlation_id,
                    reason=e.message)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=e.message)],
            isError=True,
        )

    except Exception:
        # Unexpected error - log full stack trace, return generic message
        logger.exception("tool.dispatch.unexpected_error",
                        tool_name=name,
                        correlation_id=correlation_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Something went wrong. Please try again."
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
                total_ms=round(total_ms, 1),
                correlation_id=correlation_id)

    return result
