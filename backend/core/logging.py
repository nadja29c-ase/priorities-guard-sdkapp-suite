"""Backwards-compatible re-exports. All logic lives in shared.logging."""
from shared.logging import (  # noqa: F401
    scrub_sensitive_data,
    add_correlation_id,
    configure_logging,
    get_logger,
    mask_client_id,
)
