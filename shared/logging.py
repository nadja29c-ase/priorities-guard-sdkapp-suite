"""
Structured logging with correlation ID, sensitive data scrubbing, and Better Stack shipping.

Uses structlog for JSON-formatted logs with automatic scrubbing of tokens, secrets, and credentials.
Optionally ships logs to Better Stack via logtail-python when BETTER_STACK_SOURCE_TOKEN is set.

This module is shared between backend and MCP services. It MUST NOT import from backend/*.
"""

import logging
import os
import sys
from typing import Any

import structlog


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
        "id_token",  # defensive (not in current use, but free protection)

        # PKCE
        "code_verifier",
        "code_challenge",

        # Secrets
        "client_secret",
        "client_secret_enc",  # actual DB column on CoreConnection
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


def add_service_name(logger: Any, method_name: str, event_dict: dict) -> dict:
    """
    Add service name to log events for filtering in Better Stack.

    Reads SERVICE_NAME env var. Used to distinguish backend logs from MCP
    server logs when both ship to the same Better Stack source. Falls back
    to "priority-guard-suite" if unset (e.g., local dev or scripts).

    Args:
        logger: Logger instance (unused, required by structlog)
        method_name: Method name (unused, required by structlog)
        event_dict: Log event dictionary

    Returns:
        Event dictionary with `service` field
    """
    if "service" not in event_dict:
        event_dict["service"] = os.getenv("SERVICE_NAME", "priority-guard-suite")
    return event_dict


def configure_logging(environment: str | None = None) -> None:
    """
    Configure structlog for JSON-formatted logging with optional Better Stack shipping.

    Sets up processors for:
    - Timestamp (ISO format)
    - Log level
    - Correlation ID injection
    - Sensitive data scrubbing
    - Exception formatting
    - JSON rendering

    If BETTER_STACK_SOURCE_TOKEN env var is set, also ships logs to Better Stack.

    Args:
        environment: Environment name (default: from ENV env var or "dev")
    """
    if environment is None:
        environment = os.getenv("ENV", "dev")

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

            # Add service name for filtering in Better Stack
            add_service_name,

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
    # Explicitly set root level (basicConfig may not change it if handlers exist)
    logging.root.setLevel(log_level)

    # Suppress uvicorn access logs (too noisy)
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.access").propagate = False

    # Get a logger for startup messages
    logger = structlog.get_logger()

    # Better Stack log shipping (optional)
    token = os.getenv("BETTER_STACK_SOURCE_TOKEN", "")
    if token:
        try:
            from logtail import LogtailHandler
            # Idempotency: skip if a LogtailHandler is already attached
            # Use type name check for robustness (works with mocks in tests)
            already_attached = any(
                type(h).__name__ == "LogtailHandler" for h in logging.root.handlers
            )
            if already_attached:
                logger.info("logging.betterstack.already_configured")
            else:
                logtail_handler = LogtailHandler(source_token=token)
                logging.root.addHandler(logtail_handler)
                logger.info("logging.betterstack.enabled")
        except Exception as e:
            # DO NOT raise — service must start even if Better Stack is unreachable
            # or the logtail package has an import-time issue.
            logger.warning(
                "logging.betterstack.init_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
    else:
        logger.info("logging.betterstack.disabled")

    # Log configuration complete
    logger.info(
        "logging.configured",
        environment=environment,
        log_level=logging.getLevelName(log_level)
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
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
