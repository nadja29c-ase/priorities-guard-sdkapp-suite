#!/usr/bin/env python3
"""
Priority Guardian MCP Server - Thin wrapper around backend REST API (Increment 01).
"""

import os

"""

This MCP server forwards tool calls to the backend HTTP API with:
- JWT authentication (OAuth 2.1 Bearer tokens)
- Per-tool scope enforcement with security metadata
- OAuth Protected Resource discovery endpoint
- Correlation ID propagation
- User identity extraction from tokens

No business logic, database access, or Google API calls happen here.

Usage:
    python -m mcp_server.priority_guardian.server

Or:
    python mcp_server/priority_guardian/server.py
"""

import json
import uvicorn
import httpx
import structlog
from typing import Optional, Dict, Any, Callable
from functools import wraps
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_server.priority_guardian.discovery import (
    openid_configuration,
    oauth_authorization_server,
    oauth_protected_resource,
)


# ============================================================================
# MCPContentTypeFixMiddleware - Fix ChatGPT octet-stream Content-Type
# ============================================================================

class LifespanMiddleware:
    """
    ASGI middleware to handle cleanup on server shutdown.

    Intercepts ASGI lifespan events to run cleanup when the server shuts down.
    This ensures the HTTP client is closed properly to prevent connection leaks.
    """

    def __init__(self, app, cleanup_func):
        self.app = app
        self.cleanup_func = cleanup_func

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            # Intercept lifespan protocol to add cleanup
            async def receive_wrapper():
                message = await receive()
                return message

            async def send_wrapper(message):
                if message["type"] == "lifespan.shutdown.complete":
                    # Run cleanup before signaling shutdown complete
                    await self.cleanup_func()
                await send(message)

            await self.app(scope, receive_wrapper, send_wrapper)
        else:
            await self.app(scope, receive, send)


class MCPContentTypeAndAcceptFixMiddleware:
    """
    Fix ChatGPT → FastMCP header mismatch:
    - ChatGPT sends Content-Type: application/octet-stream
    - ChatGPT sends Accept: */*
    FastMCP requires:
    - Content-Type: application/json
    - Accept: text/event-stream (for SSE handshake)
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            if scope.get("path") == "/mcp":  # exact match

                new_headers = []
                modified = False

                for name, value in scope["headers"]:
                    # Fix Content-Type (ChatGPT sends octet-stream)
                    if name == b"content-type" and b"application/octet-stream" in value:
                        value = b"application/json"
                        modified = True

                    # Fix Accept: allow SSE for handshake + JSON for tool results
                    if name == b"accept":
                        value = b"text/event-stream, application/json"
                        modified = True

                    new_headers.append((name, value))

                if modified:
                    scope = dict(scope)
                    scope["headers"] = new_headers

        await self.app(scope, receive, send)

from mcp_server.priority_guardian.config import (
    BACKEND_URL,
    MCP_SERVER_URL,
    OAUTH_ISSUER_URL,
)
from mcp_server.priority_guardian.mcp_auth import (
    authenticate_request,
    UnauthorizedError,
    InsufficientScopeError,
    build_unauthorized_error,
    build_forbidden_error,
    _jwks_cache,
)
from mcp_server.shared.google_tools import (
    CONNECT_GOOGLE_CALENDAR_DESCRIPTION,
    DISCONNECT_GOOGLE_CALENDAR_DESCRIPTION,
)

logger = structlog.get_logger(__name__)

# Create FastMCP instance with SSE streaming (required for ChatGPT)
# ChatGPT expects Server-Sent Events for MCP handshake
mcp = FastMCP("priority-guardian-mcp", streamable_http_path="/mcp")

# Shared HTTP client for calling backend API (lazily initialized)
http_client: httpx.AsyncClient | None = None


async def cleanup_http_client() -> None:
    """Close the HTTP client on shutdown to prevent connection leaks."""
    global http_client
    if http_client is not None:
        await http_client.aclose()
        http_client = None
        logger.info("mcp.http_client.closed")


# ============================================================================
# Startup Configuration Validation
# ============================================================================

# Log resolved config at startup (helps debug Railway env var issues)
logger.info(
    "mcp.server.startup",
    version="INC_01_V1",
    server_file=os.path.abspath(__file__),
    BACKEND_URL=BACKEND_URL,
    OAUTH_ISSUER_URL=OAUTH_ISSUER_URL,
    MCP_SERVER_URL=MCP_SERVER_URL,
    PORT=os.getenv("PORT"),
)

# Warn if localhost URLs are used (will break ChatGPT OAuth in production)
if "localhost" in OAUTH_ISSUER_URL:
    logger.error(
        "oauth.config.localhost_detected",
        message="OAUTH_ISSUER_URL contains localhost - ChatGPT OAuth will fail!",
        OAUTH_ISSUER_URL=OAUTH_ISSUER_URL,
    )

if "localhost" in MCP_SERVER_URL:
    logger.error(
        "oauth.config.localhost_detected",
        message="MCP_SERVER_URL contains localhost - ChatGPT OAuth will fail!",
        MCP_SERVER_URL=MCP_SERVER_URL,
    )


# ============================================================================
# OAuth Discovery Endpoints
# Starlette wrappers for discovery.py functions
# ============================================================================

async def wellknown_openid_configuration(request):  # noqa: ARG001
    """Starlette wrapper for discovery.openid_configuration."""
    return JSONResponse(await openid_configuration())


async def wellknown_oauth_authorization_server(request):  # noqa: ARG001
    """Starlette wrapper for discovery.oauth_authorization_server."""
    return JSONResponse(await oauth_authorization_server())


async def wellknown_oauth_protected_resource(request):  # noqa: ARG001
    """Starlette wrapper for discovery.oauth_protected_resource."""
    logger.info("oauth.discovery.request")
    return JSONResponse(await oauth_protected_resource())


async def mcp_options(request):  # noqa: ARG001
    """Handle OPTIONS preflight for /mcp endpoint."""
    return JSONResponse({}, status_code=200)


def handle_mcp_errors(tool_name: str) -> Callable:
    """
    Decorator to handle common MCP tool errors (DRY).

    Handles:
    - UnauthorizedError (401)
    - InsufficientScopeError (403)
    - HTTPStatusError (backend HTTP errors)
    - RequestError (connection failures, DNS, timeouts)
    - Generic exceptions

    Args:
        tool_name: Name of the tool for logging

    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> str:
            # Extract correlation_id from meta for error logging
            meta = kwargs.get("meta") or {}
            correlation_id = meta.get("correlation_id", "unknown")

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
                # Backend returned an error status (4xx, 5xx)
                logger.error(
                    f"tool.{tool_name}.backend_error",
                    correlation_id=correlation_id,
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

            except httpx.RequestError as e:
                # Connection failure (DNS, timeout, refused, etc.)
                logger.error(
                    f"tool.{tool_name}.connection_error",
                    correlation_id=correlation_id,
                    error_type=type(e).__name__,
                    url=str(e.request.url) if e.request else None,
                    error=str(e)
                )

                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "BACKEND_UNAVAILABLE",
                        "message": "Backend API is unavailable"
                    }
                })

            except Exception as e:
                # Unexpected error
                logger.error(
                    f"tool.{tool_name}.unexpected_error",
                    correlation_id=correlation_id,
                    error_type=type(e).__name__,
                    error=str(e)
                )

                return json.dumps({
                    "success": False,
                    "error": {
                        "code": "MCP_ERROR",
                        "message": "An unexpected error occurred"
                    }
                })

        return wrapper
    return decorator


async def backend_get(
    path: str,
    user_id: str,
    correlation_id: str
) -> dict:
    """
    Send a GET request to the backend API with user identity headers.

    Args:
        path: API path (e.g., "/api/priority-guardian/google/connection-status")
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID for tracing

    Returns:
        Response JSON from backend

    Raises:
        httpx.HTTPStatusError: If backend returns error status
    """
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)

    url = f"{BACKEND_URL}{path}"

    headers = {
        "X-User-ID": user_id,
        "X-Correlation-ID": correlation_id,
    }

    logger.info(
        "backend.api.get",
        correlation_id=correlation_id,
        url=path,
        user_id=user_id
    )

    resp = await http_client.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


async def backend_post(
    path: str,
    json_data: dict,
    user_id: str,
    correlation_id: str
) -> dict:
    """
    Send a POST request to the backend API with user identity headers.

    Args:
        path: API path (e.g., "/api/priority-guardian/disconnect")
        json_data: Request payload
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID for tracing

    Returns:
        Response JSON from backend

    Raises:
        httpx.HTTPStatusError: If backend returns error status
    """
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)

    url = f"{BACKEND_URL}{path}"

    # Add user identity headers
    headers = {
        "X-User-ID": user_id,
        "X-Correlation-ID": correlation_id,
    }

    logger.info(
        "backend.api.post",
        correlation_id=correlation_id,
        url=path,
        user_id=user_id
    )

    resp = await http_client.post(url, json=json_data, headers=headers)
    resp.raise_for_status()
    return resp.json()


# ============================================================================
# MCP Tools - Google Calendar Connection
# ============================================================================

@mcp.tool(
    name="connect_google_calendar",
    description=CONNECT_GOOGLE_CALENDAR_DESCRIPTION,
    annotations={
        "readOnlyHint": False,   # Initiates OAuth flow, modifies connection state
        "destructiveHint": False,
        "openWorldHint": True,   # Initiates external Google OAuth flow
    }
)
@handle_mcp_errors("connect_google_calendar")
async def connect_google_calendar(
    meta: Optional[Dict[str, Any]] = None
) -> str:
    """
    Check Google Calendar connection status and provide connect URL if needed.

    Requires OAuth scope: pg.access

    PG-specific implementation using PG backend paths.
    """
    tool_name = "connect_google_calendar"

    # Authenticate request and extract user identity
    auth_context = await authenticate_request(tool_name, meta)

    user_id = auth_context["user_id"]
    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.connect_google_calendar.start",
        correlation_id=correlation_id,
        user_id=user_id
    )

    # Check current connection status (PG backend path)
    status_response = await backend_get(
        "/api/priority-guardian/google/connection-status",
        user_id,
        correlation_id
    )

    if status_response.get("connected"):
        logger.info(
            "tool.connect_google_calendar.already_connected",
            correlation_id=correlation_id,
            user_id=user_id
        )
        return json.dumps({
            "success": True,
            "data": {
                "status": "connected",
                "connected_at": status_response.get("connected_at"),
                "message": "Google Calendar is already connected."
            }
        })

    # Not connected - get connection URL (PG backend path)
    initiate_response = await backend_post(
        "/api/priority-guardian/google/initiate-connection",
        {},
        user_id,
        correlation_id
    )

    # Extract token prefix for logging (handle missing or non-string tokens safely)
    token = initiate_response.get("token")
    token_prefix = token[:8] if isinstance(token, str) and token else None

    logger.info(
        "tool.connect_google_calendar.url_generated",
        correlation_id=correlation_id,
        user_id=user_id,
        token_prefix=token_prefix,
    )

    return json.dumps({
        "success": True,
        "data": {
            "status": "not_connected",
            "connect_url": initiate_response["connect_url"],
            "expires_in": initiate_response["expires_in"],
            "message": "Click the link to connect your Google Calendar. The link expires in 10 minutes."
        }
    })


@mcp.tool(
    name="disconnect_google_calendar",
    description=DISCONNECT_GOOGLE_CALENDAR_DESCRIPTION,
    annotations={
        "readOnlyHint": False,   # Revokes tokens, modifies state
        "destructiveHint": True,  # Irreversible - revokes access
        "openWorldHint": True,    # Revokes external Google OAuth tokens
    }
)
@handle_mcp_errors("disconnect_google_calendar")
async def disconnect_google_calendar(
    confirm: bool = False,
    meta: Optional[Dict[str, Any]] = None
) -> str:
    """
    Disconnect Google Calendar and revoke tokens.

    Requires OAuth scope: pg.access

    PG-specific implementation using PG backend paths.
    """
    tool_name = "disconnect_google_calendar"

    # Authenticate request and extract user identity
    auth_context = await authenticate_request(tool_name, meta)

    user_id = auth_context["user_id"]
    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.disconnect_google_calendar.start",
        correlation_id=correlation_id,
        user_id=user_id,
        confirm=confirm
    )

    # Require explicit confirmation
    if not confirm:
        logger.info(
            "tool.disconnect_google_calendar.confirmation_required",
            correlation_id=correlation_id,
            user_id=user_id
        )
        return json.dumps({
            "success": False,
            "error": {
                "code": "CONFIRMATION_REQUIRED",
                "message": "Please confirm disconnection by setting confirm=true. This will revoke Google Calendar access. No user data is deleted."
            }
        })

    # Check if connected first (PG backend path)
    status_response = await backend_get(
        "/api/priority-guardian/google/connection-status",
        user_id,
        correlation_id
    )

    if not status_response.get("connected"):
        logger.info(
            "tool.disconnect_google_calendar.not_connected",
            correlation_id=correlation_id,
            user_id=user_id
        )
        return json.dumps({
            "success": True,
            "data": {
                "status": "not_connected",
                "message": "Google Calendar is not connected."
            }
        })

    # Call disconnect endpoint (PG backend path)
    await backend_post(
        "/api/priority-guardian/disconnect",
        {},
        user_id,
        correlation_id
    )

    logger.info(
        "tool.disconnect_google_calendar.success",
        correlation_id=correlation_id,
        user_id=user_id
    )

    return json.dumps({
        "success": True,
        "data": {
            "status": "disconnected",
            "message": "Google Calendar has been disconnected. You can reconnect anytime."
        }
    })


# ============================================================================
# MCP Tools - Priority Management (Increment 02)
# ============================================================================

# Tool description with call preconditions (controls WHEN LLM calls)
CREATE_PRIORITY_DESCRIPTION = """Records a user's declared priority so Priority Guardian can track their time investment against it. The backend assigns a calendar keyword (P1, P2, or P3) — the user tags their Google Calendar events with this keyword so PG knows which hours count toward which priority.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- User has clearly stated a priority name (their exact words — NEVER rephrase or embellish)
- You have confirmed the type (deadline or flexible) based on user's description
- You have gathered ALL required fields for that type (see schema)
- User has confirmed the details are correct

If ANY required field is missing or vague → ask the user. NEVER invent defaults.

ONBOARDING CONTEXT: User is setting up 1–3 priorities. Call this tool once per priority after gathering all fields. After the tool returns, tell the user their assigned calendar keyword and remind them to tag calendar events with it (e.g., "Tag your calendar events with P1 to track time — like 'P1: Design review'").

KEYWORD ASSIGNMENT: The backend assigns the next available keyword automatically. Do not ask the user to choose a keyword. Just communicate the assigned keyword from the response."""


@mcp.tool(
    name="create_priority",
    description=CREATE_PRIORITY_DESCRIPTION,
    annotations={
        "readOnlyHint": False,   # Creates data in database
        "destructiveHint": False,
        "openWorldHint": False,  # No external system interaction
    }
)
@handle_mcp_errors("create_priority")
async def create_priority(
    name: str,
    type: str,
    deadline: Optional[str] = None,
    weekly_hour_target: Optional[float] = None,
    checkpoint_date: Optional[str] = None,
    desired_result: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create a priority for time tracking.

    Trust Boundary: This tool validates the JWT token and extracts user_id from
    the 'sub' claim. The user_id is then passed to the backend via X-User-ID header.
    The MCP server sets X-User-ID from the validated JWT — never from client input.

    Requires OAuth scope: pg.access

    Args:
        name: Priority name exactly as stated by user (max 100 chars)
        type: "deadline" or "flexible"
        deadline: ISO date (YYYY-MM-DD) - required when type=deadline
        weekly_hour_target: Hours per week - required when type=flexible
        checkpoint_date: ISO date (YYYY-MM-DD) - required when type=flexible
        desired_result: Concrete outcome (max 200 chars) - required when type=flexible
        meta: MCP request metadata (contains headers, correlation_id)

    Returns:
        JSON string with structuredContent containing priority data and assistant_guidance
    """
    tool_name = "create_priority"

    # Authenticate request and extract user identity
    auth_context = await authenticate_request(tool_name, meta)

    user_id = auth_context["user_id"]
    correlation_id = auth_context["correlation_id"]

    logger.info(
        "tool.create_priority.start",
        correlation_id=correlation_id,
        user_id=user_id,
        priority_name=name,
        priority_type=type,
    )

    # Build request payload (forward as-is, backend validates)
    payload = {
        "name": name,
        "type": type,
    }

    # Add optional fields only if provided
    if deadline is not None:
        payload["deadline"] = deadline
    if weekly_hour_target is not None:
        payload["weekly_hour_target"] = weekly_hour_target
    if checkpoint_date is not None:
        payload["checkpoint_date"] = checkpoint_date
    if desired_result is not None:
        payload["desired_result"] = desired_result

    # Call backend to create priority
    # NOTE: Inner try/except for HTTPStatusError provides tool-specific assistant_guidance.
    # The @handle_mcp_errors decorator also catches HTTPStatusError, but this inner handler
    # runs first and produces better error responses with contextual guidance. The decorator's
    # HTTPStatusError branch is effectively dead code for this tool — that's intentional.
    try:
        response = await backend_post(
            "/api/priority-guardian/priorities",
            payload,
            user_id,
            correlation_id
        )

        # Backend returns success response
        priority = response["data"]["priority"]
        active_count = response["data"]["active_priority_count"]
        available_keywords = response["data"]["available_keywords"]

        logger.info(
            "tool.create_priority.success",
            correlation_id=correlation_id,
            user_id=user_id,
            priority_id=priority["id"],
            keyword=priority["calendar_keyword"],
        )

        # Build assistant_guidance based on active_priority_count
        keyword = priority["calendar_keyword"]
        priority_name = priority["name"]

        if active_count < 3:
            remaining = 3 - active_count
            guidance = (
                f'Priority created. Tell the user: "{priority_name} is now tracked as {keyword}."\n'
                f'Remind them: "Tag your calendar events with {keyword} to track time — '
                f"for example, '{keyword}: Meeting name'.\"\n\n"
                f'Ask: "Do you have another priority you\'d like to track? '
                f'You can have up to {remaining} more."'
            )
        else:
            guidance = (
                f'Priority created. Tell the user: "{priority_name} is now tracked as {keyword}."\n'
                f'Remind them: "Tag your calendar events with {keyword} to track time — '
                f"for example, '{keyword}: Meeting name'.\"\n\n"
                'Say: "You\'ve set up all 3 priorities. Let me show you your dashboard." '
                'Then call get_priorities to render the widget.'
            )

        return json.dumps({
            "structuredContent": {
                "priority": priority,
                "active_priority_count": active_count,
                "available_keywords": available_keywords,
                "assistant_guidance": guidance,
            },
            "content": [
                {
                    "type": "text",
                    "text": f"Created priority: {priority_name} (assigned {keyword})"
                }
            ]
        })

    except httpx.HTTPStatusError as e:
        # Handle specific backend error responses
        status_code = e.response.status_code

        try:
            error_data = e.response.json()
            error_code = error_data.get("error", {}).get("code", "UNKNOWN")
            error_message = error_data.get("error", {}).get("message", "Unknown error")
        except Exception:
            error_code = "BACKEND_ERROR"
            error_message = f"Backend returned {status_code}"

        logger.warning(
            "tool.create_priority.backend_error",
            correlation_id=correlation_id,
            user_id=user_id,
            status_code=status_code,
            error_code=error_code,
        )

        # Build error-specific assistant_guidance
        if error_code == "MAX_PRIORITIES_REACHED":
            guidance = (
                "User already has 3 active priorities. Tell the user they've reached the maximum. "
                "If they want to add a new one, they'll need to retire or delete an existing priority first "
                "(available in their dashboard)."
            )
        elif error_code == "KEYWORD_CONFLICT":
            guidance = (
                "A race condition occurred assigning the keyword. Retry the request — "
                "the backend will assign the next available keyword."
            )
        elif error_code == "VALIDATION_ERROR":
            guidance = (
                f"Tell the user what's missing or invalid based on this error: {error_message}. "
                "Ask them to provide the correct information. Do not guess or fill in defaults."
            )
        elif error_code == "UNAUTHORIZED":
            guidance = "Authentication failed. The user may need to reconnect."
        else:
            guidance = f"An error occurred: {error_message}. Please try again."

        return json.dumps({
            "structuredContent": {
                "error": {
                    "code": error_code,
                    "message": error_message,
                },
                "assistant_guidance": guidance,
            },
            "content": [
                {
                    "type": "text",
                    "text": f"Error: {error_message}"
                }
            ]
        })


# ============================================================================
# Application Factory
# ============================================================================

def create_app():
    """
    FastMCP is the root app - Starlette discovery routes mounted into it.
    This ensures FastMCP's lifespan runs and task group initializes properly.
    """
    # FastMCP is the root app - its lifespan will run properly
    fastmcp_app = mcp.streamable_http_app()

    # Discovery routes as a separate Starlette app
    # Include both root and /mcp suffixed versions (ChatGPT checks both)
    discovery_routes = [
        # Root discovery endpoints
        Route("/openid-configuration", wellknown_openid_configuration, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-authorization-server", wellknown_oauth_authorization_server, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-protected-resource", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
        # ChatGPT also checks /mcp suffixed versions
        Route("/openid-configuration/mcp", wellknown_openid_configuration, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-authorization-server/mcp", wellknown_oauth_authorization_server, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-protected-resource/mcp", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
    ]
    discovery_app = Starlette(routes=discovery_routes)

    # Mount discovery routes onto FastMCP app
    fastmcp_app.mount("/.well-known", discovery_app)

    # Log FastMCP configuration
    logger.info(
        "mcp.app.created",
        fastmcp_name=mcp.name,
        mcp_endpoint="/mcp",
        discovery_mount="/.well-known",
    )

    # Wrap with middlewares:
    # 1. LifespanMiddleware (outermost) - handles cleanup on shutdown
    # 2. MCPContentTypeAndAcceptFixMiddleware - fixes ChatGPT header issues
    wrapped_app = MCPContentTypeAndAcceptFixMiddleware(fastmcp_app)
    return LifespanMiddleware(wrapped_app, cleanup_http_client)


# --------------------------------------------------------------------
# ASGI entrypoint for uvicorn (Railway imports this)
# --------------------------------------------------------------------
app = create_app()


if __name__ == "__main__":
    # Use PORT env var (Railway sets this) or default to 8003 for local dev
    port = int(os.getenv("PORT", "8003"))

    logger.info(
        "Starting Priority Guardian MCP server",
        host="0.0.0.0",
        port=port,
        mcp_server_url=MCP_SERVER_URL,
        oauth_issuer_url=OAUTH_ISSUER_URL
    )

    # Run with uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)
