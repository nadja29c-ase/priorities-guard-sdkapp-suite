"""
Structured logging with correlation ID and sensitive data scrubbing (Increment 7C).

Uses structlog for JSON-formatted logs with automatic scrubbing of tokens, secrets, and credentials.
"""

import logging
import sys
from typing import Any

import structlog

from backend.core.config import settings


def scrub_sensitive_data(logger: Any, method_name: str, event_dict: dict) -> dict:
    """
    Scrub sensitive data from log events.

    Redacts tokens, secrets, credentials, and other sensitive fields
    to prevent leakage in logs.

    Args:
        logger: Logger instance (unused, required by structlog)
        method_name: Method name (unused, required by structlog)
        event_dict: Log event dictionary

    Returns:
        Event dictionary with sensitive fields redacted
    """
    REDACT_KEYS = [
        # OAuth tokens
        "access_token",
        "refresh_token",
        "authorization_code",
        "authorization",
        "token",

        # PKCE
        "code_verifier",
        "code_challenge",

        # Secrets
        "client_secret",
        "password",
        "secret",

        # Google tokens
        "encrypted_access_token",
        "encrypted_refresh_token",
    ]

    for key in REDACT_KEYS:
        if key in event_dict:
            event_dict[key] = "[REDACTED]"

    return event_dict


def add_correlation_id(logger: Any, method_name: str, event_dict: dict) -> dict:
    """
    Add correlation_id to log events from context.

    Extracts correlation_id from structlog context and adds to event.
    Falls back to "system" for non-HTTP logs (startup, Celery jobs).

    Args:
        logger: Logger instance (unused, required by structlog)
        method_name: Method name (unused, required by structlog)
        event_dict: Log event dictionary

    Returns:
        Event dictionary with correlation_id field
    """
    # correlation_id should be bound to logger via bind() in middleware
    # If not present, use "system" for background jobs
    if "correlation_id" not in event_dict:
        event_dict["correlation_id"] = "system"

    return event_dict


def configure_logging(environment: str = None) -> None:
    """
    Configure structlog for JSON-formatted logging.

    Sets up processors for:
    - Timestamp (ISO format)
    - Log level
    - Correlation ID injection
    - Sensitive data scrubbing
    - Exception formatting
    - JSON rendering

    Args:
        environment: Environment name (default: from settings.ENV)
    """
    if environment is None:
        environment = settings.ENV

    # Determine log level by environment
    if environment == "production":
        log_level = logging.INFO
    elif environment == "staging":
        log_level = logging.INFO
    else:  # dev
        log_level = logging.DEBUG

    # Configure structlog processors
    structlog.configure(
        processors=[
            # Add log level
            structlog.stdlib.add_log_level,

            # Add timestamp (ISO 8601)
            structlog.processors.TimeStamper(fmt="iso"),

            # Add correlation ID from context
            add_correlation_id,

            # Scrub sensitive data
            scrub_sensitive_data,

            # Add stack info on exceptions
            structlog.processors.StackInfoRenderer(),

            # Format exceptions
            structlog.processors.format_exc_info,

            # Render as JSON
            structlog.processors.JSONRenderer()
        ],
        # Wrapper class for logger
        wrapper_class=structlog.stdlib.BoundLogger,

        # Logger factory
        logger_factory=structlog.stdlib.LoggerFactory(),

        # Cache logger instances
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        stream=sys.stdout,
    )

    # Suppress uvicorn access logs (too noisy)
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.access").propagate = False

    # Log configuration complete
    logger = structlog.get_logger()
    logger.info(
        "logging.configured",
        environment=environment,
        log_level=logging.getLevelName(log_level)
    )


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structlog logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger
    """
    return structlog.get_logger(name)


def mask_client_id(client_id: str | None) -> str:
    """
    Mask client_id for safe logging (GDPR/privacy compliance).

    Shows first 4 and last 4 characters with **** in between.
    For short client_ids (< 10 chars), shows first 2 and last 2.

    Args:
        client_id: The OAuth client identifier

    Returns:
        Masked string like "focu****ent1" or "[none]" if None

    Example:
        >>> mask_client_id("focused-client-abc123")
        'focu****c123'
        >>> mask_client_id("short")
        'sh****rt'
        >>> mask_client_id(None)
        '[none]'
    """
    if not client_id:
        return "[none]"

    if len(client_id) < 5:
        return "****"

    if len(client_id) < 10:
        return f"{client_id[:2]}****{client_id[-2:]}"

    return f"{client_id[:4]}****{client_id[-4:]}"
