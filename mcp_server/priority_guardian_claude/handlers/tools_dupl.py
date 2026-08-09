# (duplicate) — exists because it imports platform-specific mcp_auth.#
# !! ITS CONTENTS ARE NOT A COPY. Verified 2026-08-09 by symbol-level sweep: this
# file has diverged STRUCTURALLY from the source named below, and not every
# divergence is documented. Do not assume a symbol here behaves as its namesake
# does there — and note that a symbol may be ABSENT here entirely. That is exactly
# how A22 happened: BearerAuthMiddleware dropped JWT validation, scope enforcement
# and the 413 guard while this header claimed a config-only difference.
# See doc/DUPL_DIVERGENCE_SWEEP_2026-08-09.md.
# Dispatcher logic lives in mcp_server/priority_guardian/handlers/tools.py.
# Post-OpenAI-approval refactor: move shared logic to mcp_server/shared/
# with config injection and delete this file.

"""
Tool call dispatcher for Priority Guardian Claude MCP.

Routes tool calls to the appropriate handler in the registry.
Handles authentication, error handling, and timing.
"""

import time

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.tools import get_tool
from mcp_server.priority_guardian.tools.base import ToolUsageError
from mcp_server.priority_guardian_claude.mcp_auth_dupl import (
    authenticate_request,
    UnauthorizedError,
    InsufficientScopeError,
    build_unauthorized_meta,
    build_forbidden_meta,
)
from mcp_server.priority_guardian_claude.response_adapter_dupl import (
    adapt_tool_result,
    adapt_widget_tool_meta,
)

# Tools that render the widget (need _meta.ui in tool result)
_WIDGET_TOOL_NAMES = {"get_priorities", "render_weekly_report", "create_priority"}

logger = structlog.get_logger(__name__)


async def call_tool_request(req: mcp_types.CallToolRequest) -> mcp_types.CallToolResult:
    """
    Handle tool calls with authentication and dispatch to registry.

    Dispatcher sequence (fixed order):
    1. Extract tool name, arguments, _meta from request
    2. Look up tool in TOOL_REGISTRY → unknown tool returns isError=True
    3. Authenticate: call authenticate_request → extracts user_id from JWT sub claim
    4. Catch UnauthorizedError → return isError=True with _meta containing www_authenticate
    5. Catch InsufficientScopeError → return isError=True with _meta containing www_authenticate
    6. Call tool.handle(user_id, correlation_id, arguments)
    7. Catch ToolUsageError → return isError=True with verbatim message
    8. Catch Exception → log full trace, return generic error
    9. Log timing
    10. Return CallToolResult

    Args:
        req: MCP CallToolRequest with tool name, arguments, and metadata

    Returns:
        CallToolResult from the tool handler or error response
    """
    start_total = time.perf_counter()

    # Step 1: Extract tool name, arguments, and metadata
    name = req.params.name
    arguments = req.params.arguments or {}
    meta = getattr(req.params, '_meta', None) or {}

    logger.debug("tool.dispatch.received",
                tool_name=name,
                argument_keys=list(arguments.keys()))

    # Step 2: Look up tool in registry
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

    # Step 3: Authenticate (with timing)
    start_auth = time.perf_counter()
    try:
        auth_context = await authenticate_request(name, meta)
        user_id = auth_context["user_id"]
        correlation_id = auth_context["correlation_id"]

    except UnauthorizedError:
        # Step 4: Handle 401 Unauthorized
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
        # Step 5: Handle 403 Forbidden
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

    # Step 6: Dispatch to tool handler (with timing)
    logger.info("tool.dispatch.executing",
                tool_name=name,
                user_id=user_id,
                correlation_id=correlation_id)

    start_tool = time.perf_counter()
    try:
        result = await tool.handle(user_id, correlation_id, arguments)

        # Runtime type guard: ensure handler returned CallToolResult
        if not isinstance(result, mcp_types.CallToolResult):
            logger.error(
                "tool.dispatch.invalid_return",
                tool_name=name,
                correlation_id=correlation_id,
                returned_type=type(result).__name__,
            )
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text="Something went wrong. Please try again.",
                )],
                isError=True,
            )

        # Adapt result for Claude (move assistant_guidance to content)
        result = adapt_tool_result(result)

        # Add widget link for widget tools (triggers Claude to display dashboard widget)
        if name in _WIDGET_TOOL_NAMES:
            result = adapt_widget_tool_meta(result)
            logger.debug(
                "tool.widget_attached",
                tool_name=name,
                has_structured=result.structuredContent is not None,
            )

    except ToolUsageError as e:
        # Step 7: Handle intentional rejection
        tool_ms = (time.perf_counter() - start_tool) * 1000
        total_ms = (time.perf_counter() - start_total) * 1000

        logger.info("tool.dispatch.rejected",
                   tool_name=name,
                   correlation_id=correlation_id,
                   reason=str(e))

        logger.info("tool.timing",
                   tool_name=name,
                   correlation_id=correlation_id,
                   auth_ms=round(auth_ms, 1),
                   tool_ms=round(tool_ms, 1),
                   total_ms=round(total_ms, 1),
                   user_id=user_id)

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=str(e),
            )],
            isError=True,
        )

    except Exception:
        # Step 8: Handle unexpected errors
        tool_ms = (time.perf_counter() - start_tool) * 1000
        total_ms = (time.perf_counter() - start_total) * 1000

        logger.exception("tool.dispatch.unexpected_error",
                        tool_name=name,
                        user_id=user_id,
                        correlation_id=correlation_id)

        logger.info("tool.timing",
                   tool_name=name,
                   correlation_id=correlation_id,
                   auth_ms=round(auth_ms, 1),
                   tool_ms=round(tool_ms, 1),
                   total_ms=round(total_ms, 1),
                   user_id=user_id)

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Something went wrong. Please try again."
            )],
            isError=True,
        )

    tool_ms = (time.perf_counter() - start_tool) * 1000

    # Step 9: Log timing
    total_ms = (time.perf_counter() - start_total) * 1000

    logger.info("tool.timing",
                tool_name=name,
                correlation_id=correlation_id,
                auth_ms=round(auth_ms, 1),
                tool_ms=round(tool_ms, 1),
                total_ms=round(total_ms, 1),
                user_id=user_id)

    # Step 10: Return result
    return result
