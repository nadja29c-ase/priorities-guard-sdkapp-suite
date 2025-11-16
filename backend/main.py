"""
Priority Guardian - Main FastAPI application.
Mounts OAuth provider and all SDK app routers.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import httpx

from backend.core.config import settings
from backend.core.logging import init_logging
from backend.core.middleware import RequestIDMiddleware
from backend.core.database import test_connection
from backend.apps.focused.focused_router import router as focused_router
from backend.apps.focused.auth_router import router as auth_router
from backend.core.database import engine

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

    # Initialize httpx client
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    logger.info(
        "HTTP client initialized",
        extra={"request_id": "startup"}
    )

    # Test database connection
    try:
        await test_connection()
    
    except Exception as e:
        logger.warning(
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

    # Close httpx client
    await app.state.http_client.aclose()
    logger.info(
        "HTTP client closed",
        extra={"request_id": "shutdown"}
    )
    # Dispose DB engine. should always be the last teardown step for safety
    await engine.dispose()
    logger.info(
        "DB engine disposed",
        extra={"request_id": "shutdown"}
    )


# Create FastAPI app
app = FastAPI(
    title="Priority Guardian",
    description="Backend for Priority Guardian SDK apps",
    version="0.1.0",
    lifespan=lifespan,
)

# Add custom exception handler for validation errors
# -------------------------------------------------------------
# Friendly validation error messages
# -------------------------------------------------------------

FRIENDLY_MESSAGES = {
    "value_error.missing": "This field is required.",
    "value_error": "Invalid value.",
    "type_error.integer": "Must be a valid number.",
    "type_error.float": "Must be a valid number.",
    "type_error.bool": "Must be true or false.",
    "type_error.string": "Must be a text value.",
    "type_error.list": "Must be a list.",
    "type_error.dict": "Must be an object.",
    "type_error.datetime": "Must be a valid date/time (ISO format).",
    "type_error.date": "Must be a valid date (YYYY-MM-DD).",
    "extra_forbidden": "This field is not allowed.",
    "string_too_short": "This value is too short.",
    "string_too_long": "This value is too long.",
    "greater_than": "Value must be greater.",
    "less_than": "Value must be smaller.",
}


def translate_message(err_type: str, default_msg: str) -> str:
    """
    Convert Pydantic's technical error messages into human-friendly text. Turn ugly messages into nice ones.
    """
    if err_type in FRIENDLY_MESSAGES:
        return FRIENDLY_MESSAGES[err_type]

    # Fallback on prefix-matching (e.g., type_error.float.ge)
    for prefix, friendly in FRIENDLY_MESSAGES.items():
        if err_type.startswith(prefix):
            return friendly

    # If no mapping exists, return original
    return default_msg


# -------------------------------------------------------------
# Validation Error Handler (replaces FastAPI default)
# -------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Turn Pydantic/FastAPI validation errors into:
    {
       "success": false,
       "error": { "code": "VALIDATION_ERROR", "message": "...", "details": [...] }
    }
    """
    details = []

    for err in exc.errors():
        loc = err.get("loc", [])
        field = ".".join(str(p) for p in loc if p not in ("body", "query", "path"))

        err_type = err.get("type", "")
        default_msg = err.get("msg", "Invalid value")
        friendly_msg = translate_message(err_type, default_msg)

        details.append({
            "field": field or None,
            "message": friendly_msg,
            "type": err_type
        })

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Your request contains invalid or missing fields.",
                "details": details
            }
        }
    )

# Add RequestIDMiddleware
"""When a request hits your backend:
- The middleware generates a random request_id.
- Stores it in request.state.request_id.
- Calls your endpoint.
- After your endpoint finishes, it might log something.
- Returns the response.
- This happens for every single request, automatically, without changing your endpoint code."""
app.add_middleware(RequestIDMiddleware)


@app.get("/")
async def root():
    """Root endpoint.A health-check / landing endpoint so you can hit the root URL and confirm the backend is running"""
    return {
        "success": True,
        "data": {
            "message": "Priority Guardian Backend"
        }
    }


# Include focused router with prefix
app.include_router(focused_router, prefix="/api/focused")

# Include auth router with prefix
app.include_router(auth_router, prefix="/auth/focused")
