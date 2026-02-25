"""
Middleware for Priority Guardian (Increment 7C).

Provides:
- Correlation ID propagation across requests
- Global security headers for all endpoints
"""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle correlation ID for request tracing.

    Accepts X-Correlation-ID from upstream (e.g., MCP server) or generates new UUID.
    Adds correlation_id to request.state and response headers.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Extract or generate correlation ID and attach to request.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            Response with X-Correlation-ID header
        """
        # Accept from upstream (MCP server) or generate new
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Store in request state for access in handlers
        request.state.correlation_id = correlation_id

        # Process request
        response = await call_next(request)

        # Add to response headers for client tracing
        response.headers["X-Correlation-ID"] = correlation_id

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add global security headers to all responses.

    Applies OWASP-recommended security headers:
    - X-Content-Type-Options: Prevent MIME sniffing
    - X-Frame-Options: Prevent clickjacking
    - X-XSS-Protection: Enable XSS filtering
    - Strict-Transport-Security: Enforce HTTPS
    - Cache-Control: Prevent caching of sensitive data
    - Pragma: Legacy cache control
    """

    async def dispatch(self, request: Request, call_next):
        """
        Add security headers to response.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            Response with security headers
        """
        response = await call_next(request)

        # Apply security headers to ALL endpoints
        response.headers.update({
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            # CSP: default-src 'self' restricts to same origin
            # base-uri 'self' prevents <base> tag injection
            # object-src 'none' blocks Flash/plugin-based XSS
            # script-src 'self' 'unsafe-inline' allows inline scripts (consent pages)
            # style-src 'self' 'unsafe-inline' allows inline styles
            # frame-ancestors 'none' reinforces X-Frame-Options DENY
            "Content-Security-Policy": (
                "default-src 'self'; "
                "base-uri 'self'; "
                "object-src 'none'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "frame-ancestors 'none'"
            ),
        })

        return response
