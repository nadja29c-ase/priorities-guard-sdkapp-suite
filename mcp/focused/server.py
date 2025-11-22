#!/usr/bin/env python3
"""
Focused MCP Server - Thin wrapper around backend REST API (Increment 7D).

This MCP server forwards tool calls to the backend HTTP API with:
- JWT authentication (OAuth 2.1 Bearer tokens)
- Per-tool scope enforcement
- Correlation ID propagation
- User identity extraction from tokens

No business logic, database access, or Google API calls happen here.

Usage:
    python -m mcp.focused.server

Or:
    python mcp/focused/server.py
"""

import json
import logging
import uvicorn
import httpx
from typing import Optional, Dict, Any, Callable
from functools import wraps
from mcp.server.fastmcp import FastMCP

from mcp.focused.config import BACKEND_URL
from mcp.focused.mcp_auth import (
    authenticate_request,
    UnauthorizedError,
    InsufficientScopeError,
    build_unauthorized_error,
    build_forbidden_error,
)

logger = logging.getLogger(__name__)

# Create FastMCP instance
mcp = FastMCP("focused-mcp")

# Shared HTTP client for calling backend API
http_client: httpx.AsyncClient | None = None


def handle_mcp_errors(tool_name: str) -> Callable:
    """
    Decorator to handle common MCP tool errors (DRY).

    Handles:
    - UnauthorizedError (401)
    - InsufficientScopeError (403)
    - HTTPStatusError (backend errors)
    - Generic exceptions

    Args:
        tool_name: Name of the tool for logging

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> str:
            try:
                return await func(*args, **kwargs)

            except UnauthorizedError as e:
                # Token validation failed (401)
                error_response = build_unauthorized_error(e.error, e.description)
                return json.dumps(error_response)

            except InsufficientScopeError as e:
                # Missing required scopes (403)
                error_response = build_forbidden_error(e.required_scopes, e.actual_scopes)
                return json.dumps(error_response)

            except httpx.HTTPStatusError as e:
                # Backend returned an error status
                logger.error(
                    f"tool.{tool_name}.backend_error",
                    status_code=e.response.status_code,
                    error=e.response.text
                )

                try:
                    error_data = e.response.json()
                    return json.dumps(error_data)
                except Exception:
                    return json.dumps({
                        "success": False,
                        "error": {
                            "code": "BACKEND_ERROR",
                            "message": f"Backend API returned {e.response.status_code}"
                        }
                    })

            except Exception as e:
                # Unexpected error (network, etc.)
                logger.error(f"tool.{tool_name}.error", error=str(e))

                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "MCP_ERROR",
                        "message": "Failed to communicate with backend API"
                    }
                })

        return wrapper
    return decorator


async def backend_post(
    path: str,
    json_data: dict,
    user_id: str,
    correlation_id: str
) -> dict:
    """
    Send a POST request to the backend API with user identity headers.

    Args:
        path: API path (e.g., "/api/focused/check_calendar")
        json_data: Request payload
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID for tracing

    Returns:
        Response JSON from backend

    Raises:
        httpx.HTTPStatusError: If backend returns error status
    """
    url = f"{BACKEND_URL}{path}"

    # Add user identity headers (Increment 7D)
    headers = {
        "X-User-ID": user_id,
        "X-Correlation-ID": correlation_id,
    }

    logger.info(
        "backend.api.call",
        correlation_id=correlation_id,
        url=path,
        user_id=user_id
    )

    resp = await http_client.post(url, json=json_data, headers=headers)
    resp.raise_for_status()
    return resp.json()


@mcp.tool()
@handle_mcp_errors("check_calendar")
async def check_calendar(
    time_start: str | None = None,
    time_end: str | None = None,
    max_results: int = 20,
    _meta: Optional[Dict[str, Any]] = None
) -> str:
    """
    Identify focus blocks in Google Calendar.

    Requires OAuth scope: focused.read

    Keywords are determined by the backend from:
    - System default keywords (e.g., "focus", "deep work")
    - User's custom keywords stored in the database

    This is a thin MCP wrapper that forwards the request to the backend API.

    Args:
        time_start: Start time (ISO8601), defaults to now
        time_end: End time (ISO8601), defaults to now + 7 days
        max_results: Max events to scan (1-50), defaults to 20
        _meta: Request metadata (headers, correlation_id)

    Returns:
        JSON string with success status and data/error
    """
    tool_name = "check_calendar"

    # Authenticate request and extract user identity
    auth_context = await authenticate_request(tool_name, _meta)

    user_id = auth_context["user_id"]
    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.check_calendar.start",
        correlation_id=correlation_id,
        user_id=user_id,
        max_results=max_results
    )

    # Forward request to backend API with identity headers
    response = await backend_post(
        "/api/focused/check_calendar",
        {
            "time_start": time_start,
            "time_end": time_end,
            "max_results": max_results
        },
        user_id=user_id,
        correlation_id=correlation_id
    )

    # Backend already returns {success: bool, data/error: ...}
    return json.dumps(response)


@mcp.tool()
@handle_mcp_errors("watch_calendar")
async def watch_calendar(
    _meta: Optional[Dict[str, Any]] = None
) -> str:
    """
    Register webhook for Google Calendar push notifications.

    Requires OAuth scope: focused.write

    Registers a webhook channel with Google to receive real-time
    calendar event updates instead of polling.

    Args:
        _meta: Request metadata (headers, correlation_id)

    Returns:
        JSON string with success status and data/error
    """
    tool_name = "watch_calendar"

    # Authenticate request and extract user identity
    auth_context = await authenticate_request(tool_name, _meta)

    user_id = auth_context["user_id"]
    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.watch_calendar.start",
        correlation_id=correlation_id,
        user_id=user_id
    )

    # Forward request to backend API with identity headers
    response = await backend_post(
        "/api/focused/watch_calendar",
        {"user_id": user_id},  # Keep in payload for backward compat
        user_id=user_id,
        correlation_id=correlation_id
    )

    return json.dumps(response)


@mcp.tool()
@handle_mcp_errors("run_focus_mode")
async def run_focus_mode(
    _meta: Optional[Dict[str, Any]] = None
) -> str:
    """
    Activate Apple Focus Mode (stub for future implementation).

    Requires OAuth scope: focused.write

    Args:
        _meta: Request metadata (headers, correlation_id)

    Returns:
        JSON string with error indicating not implemented
    """
    tool_name = "run_focus_mode"

    # Authenticate request (enforces focused.write scope)
    auth_context = await authenticate_request(tool_name, _meta)

    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.run_focus_mode.not_implemented",
        correlation_id=correlation_id
    )

    return json.dumps({
        "success": False,
        "error": {
            "code": "NOT_IMPLEMENTED",
            "message": "run_focus_mode is not yet implemented"
        }
    })


@mcp.tool()
@handle_mcp_errors("notify_user")
async def notify_user(
    _meta: Optional[Dict[str, Any]] = None
) -> str:
    """
    Send notification to user (stub for future implementation).

    Requires OAuth scope: focused.notify

    Args:
        _meta: Request metadata (headers, correlation_id)

    Returns:
        JSON string with error indicating not implemented
    """
    tool_name = "notify_user"

    # Authenticate request (enforces focused.notify scope)
    auth_context = await authenticate_request(tool_name, _meta)

    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.notify_user.not_implemented",
        correlation_id=correlation_id
    )

    return json.dumps({
        "success": False,
        "error": {
            "code": "NOT_IMPLEMENTED",
            "message": "notify_user is not yet implemented"
        }
    })


if __name__ == "__main__":
    # Initialize HTTP client
    http_client = httpx.AsyncClient(timeout=30.0)

    logger.info("Starting Focused MCP server on http://0.0.0.0:8001/mcp")

    # Get FastMCP streamable HTTP app
    app = mcp.streamable_http_app()

    # Run with uvicorn on port 8001
    uvicorn.run(app, host="0.0.0.0", port=8001)
