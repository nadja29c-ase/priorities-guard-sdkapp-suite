"""
User ID extraction helper for MCP tool endpoints.

Handles Increment 7D user identity extraction with fallback logic.
"""

from fastapi import Request
from backend.core.logging import get_logger

logger = get_logger(__name__)


def extract_user_id(
    request: Request,
    payload_user_id: str | None,
    endpoint: str
) -> str:
    """
    Extract user_id from request with fallback chain.

    Increment 7D Identity Extraction:
    1. Primary: X-User-ID header (from MCP after JWT validation)
    2. Fallback: payload.user_id (backward compatibility)
    3. Ultra-fallback: "test_user" (legacy)

    Args:
        request: FastAPI request object
        payload_user_id: User ID from request payload (if present)
        endpoint: Endpoint name for logging (e.g., "check_calendar")

    Returns:
        Validated user_id string

    Logs:
        - Warning if header and payload mismatch
        - Warning when using fallback (not header)
    """
    # Get correlation_id from request state (set by middleware)
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    request_logger = logger.bind(correlation_id=correlation_id)

    # Primary source: X-User-ID header (Increment 7D)
    user_id_header = request.headers.get("x-user-id")

    if user_id_header:
        # Check for mismatch between header and payload
        if payload_user_id and payload_user_id != user_id_header:
            request_logger.warning(
                f"{endpoint}.user_id_mismatch",
                header_value=user_id_header,
                payload_value=payload_user_id,
                endpoint=endpoint
            )
        return user_id_header

    # Fallback 1: payload.user_id (backward compatibility)
    if payload_user_id:
        request_logger.warning(
            f"{endpoint}.user_id_fallback",
            source="payload",
            endpoint=endpoint
        )
        return payload_user_id

    # Fallback 2: Ultra-legacy hardcoded test_user
    request_logger.warning(
        f"{endpoint}.user_id_fallback",
        source="hardcoded",
        endpoint=endpoint
    )
    return "test_user"
