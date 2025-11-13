"""
Structured JSON logging for Priority Guardian.

Configures JSON formatter with required fields and suppresses uvicorn access logs.
"""

import logging
import sys
from pythonjsonlogger import jsonlogger

from backend.core.config import settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with required fields."""

    def add_fields(self, log_record, record, message_dict):
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = self.formatTime(record, self.datefmt)
        log_record["level"] = record.levelname
        log_record["app_name"] = settings.APP_NAME

        # Add request_id if available
        if hasattr(record, "request_id"):
            log_record["request_id"] = record.request_id


def init_logging() -> None:
    """Initialize structured JSON logging."""
    # Create handler
    handler = logging.StreamHandler(sys.stdout)

    # Set JSON formatter
    formatter = CustomJsonFormatter(
        "%(timestamp)s %(level)s %(app_name)s %(name)s %(message)s"
    )
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(settings.LOG_LEVEL)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Suppress uvicorn access logs
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.access").propagate = False
