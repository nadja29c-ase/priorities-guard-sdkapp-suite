"""
Priority Guardian - Main FastAPI application.

Mounts OAuth provider and all SDK app routers.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from backend.core.config import settings
from backend.core.logging import init_logging
from backend.core.middleware import RequestIDMiddleware
from backend.core.database import test_connection
from backend.apps.focused.focused_router import router as focused_router

# Initialize logging first
init_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info(
        f"Starting {settings.APP_NAME} in {settings.ENV} environment",
        extra={"request_id": "startup"}
    )

    # Test database connection
    try:
        await test_connection()
        logger.info(
            "Database connection established",
            extra={"request_id": "startup"}
        )
    except Exception as e:
        logger.error(
            f"Database connection failed: {e}",
            extra={"request_id": "startup"}
        )
        raise

    yield

    # Shutdown
    logger.info(
        "Shutting down application",
        extra={"request_id": "shutdown"}
    )


# Create FastAPI app
app = FastAPI(
    title="Priority Guardian",
    description="Backend for Priority Guardian SDK apps",
    version="0.1.0",
    lifespan=lifespan,
)

# Add RequestIDMiddleware
app.add_middleware(RequestIDMiddleware)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "success": True,
        "data": {
            "message": "Priority Guardian Backend"
        }
    }


# Include focused router with prefix
app.include_router(focused_router, prefix="/api/focused")
