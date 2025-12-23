"""
Priority Guardian - Main FastAPI application.
Mounts OAuth provider and all SDK app routers.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
import httpx

from backend.core.config import settings
from backend.core.logging import configure_logging, get_logger
from backend.core.middleware import CorrelationIDMiddleware, SecurityHeadersMiddleware
from backend.core.database import test_connection
from backend.core.database import engine
from backend.core.redis_client import redis_client
from backend.core.oauth_provider.exceptions import OAuthError

# Import new modular routers
from backend.apps.focused.routers.tools_router import router as tools_router
from backend.apps.focused.routers.webhook_router import router as webhook_router
from backend.core.routers.oauth_google_router import router as oauth_google_router
from backend.apps.focused.routers.health_router import router as health_router
from backend.apps.focused.routers.admin_router import router as admin_router
from backend.core.routers.oauth_provider_router import router as oauth_provider_router
from backend.apps.focused.routers.onboarding_router import router as onboarding_router
from backend.apps.focused.routers.shortcut_router import router as shortcut_router
from backend.apps.focused.routers.offboarding_router import router as offboarding_router
from backend.apps.focused.routers.google_connection_router import router as google_connection_router
from backend.apps.clarity import clusters_router

# Initialize logging first
configure_logging()

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} in {settings.ENV} environment")

    # CRITICAL: Validate OAuth keys exist (Increment 7A)
    if not settings.OAUTH_RSA_PRIVATE_KEY or not settings.OAUTH_RSA_PUBLIC_KEY:
        raise RuntimeError(
            "OAuth RSA keys not configured. "
            "Run: python scripts/generate_oauth_keys.py"
        )

    # CRITICAL: Validate keys can be loaded (Increment 7A)
    try:
        from backend.core.crypto import _private_key, _public_key
        logger.info(f"OAuth keys loaded successfully (kid={settings.OAUTH_JWT_KID})")
    except Exception as e:
        raise RuntimeError(f"Failed to load OAuth RSA keys: {e}")

    # Initialize httpx client
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    logger.info("HTTP client initialized")

    # Initialize Redis connection
    await redis_client.connect()

    # Verify Redis connection health
    if redis_client.is_connected():
        logger.info("Redis connection healthy")
    else:
        logger.warning("Redis connection failed - webhook idempotency/throttling will be degraded")
        # Don't raise - app continues with degraded functionality

    # Test database connection
    try:
        await test_connection()

    except Exception as e:
        logger.warning(f"Database connection failed: {e}")
        raise

    yield

    # Shutdown
    logger.info("Shutting down application")

    # Close httpx client
    await app.state.http_client.aclose()
    logger.info("HTTP client closed")

    # Close Redis connection
    await redis_client.close()
    logger.info("Redis connection closed")

    # Dispose DB engine. should always be the last teardown step for safety
    await engine.dispose()
    logger.info("DB engine disposed")


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
async def validation_exception_handler(_: Request, exc: RequestValidationError):
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


# -------------------------------------------------------------
# OAuth Error Handler (Increment 7C)
# -------------------------------------------------------------

@app.exception_handler(OAuthError)
async def oauth_exception_handler(request: Request, exc: OAuthError):
    """
    Handle OAuth errors with RFC 6749-compliant responses.

    Returns JSON error responses per OAuth 2.1 specification.
    """
    # Extract correlation_id for logging
    correlation_id = getattr(request.state, 'correlation_id', 'system')
    request_logger = logger.bind(correlation_id=correlation_id)

    request_logger.warning(
        "oauth.error",
        error=exc.error,
        description=exc.description,
        status_code=exc.status_code
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error,
            "error_description": exc.description
        }
    )


# Add Correlation ID and Security Headers Middleware (Increment 7C)
"""
CorrelationIDMiddleware: Generates or accepts correlation_id for request tracing
SecurityHeadersMiddleware: Applies OWASP-recommended security headers globally
"""
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CorrelationIDMiddleware)


@app.get("/")
async def root():
    """Root endpoint.A health-check / landing endpoint so you can hit the root URL and confirm the backend is running"""
    return {
        "success": True,
        "data": {
            "message": "Priority Guardian Backend"
        }
    }


@app.get("/privacy")
async def privacy_policy():
    """Serve the Privacy Policy HTML page."""
    file_path = Path(__file__).parent / "static" / "PrivacyPolicy_PGS.html"
    return FileResponse(file_path)


# Include new modular routers
app.include_router(tools_router, prefix="/api/focused/tools")
app.include_router(webhook_router, prefix="/webhook/focused")
app.include_router(oauth_google_router, prefix="/auth/google")
app.include_router(health_router, prefix="/api/focused")
app.include_router(admin_router, prefix="/api/focused")

# Include OAuth provider router (Increment 7A - OAuth Provider Skeleton)
# NOTE: No prefix - endpoints include full paths (/.well-known/*, /oauth/focused/*)
app.include_router(oauth_provider_router)
app.include_router(onboarding_router, prefix="/api/focused/onboarding")
app.include_router(shortcut_router, prefix="/shortcut/focused")
app.include_router(offboarding_router, prefix="/api/focused")
app.include_router(google_connection_router, prefix="/api/focused/google")

# Clarity SDK app router (Increment 05)
app.include_router(clusters_router, prefix="/api/clarity")
