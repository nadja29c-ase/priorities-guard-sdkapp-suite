"""
Middleware for Priority Guardian.

RequestIDMiddleware generates a unique ID for each request.
"""

import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to generate and attach a unique request ID to each request."""

    async def dispatch(self, request: Request, call_next):
        """Generate UUID4 and store in request.state."""
        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Store in request state
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Optionally add to response headers for tracing
        response.headers["X-Request-ID"] = request_id

        return response
