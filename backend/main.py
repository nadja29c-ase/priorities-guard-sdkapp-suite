"""
Priority Guardian - Main FastAPI application.
Mounts OAuth provider and all SDK app routers.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
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

# Priority Guardian app routers (Increment 01)
from backend.apps.priority_guardian.routers.health_router import router as pg_health_router
from backend.apps.priority_guardian.routers.google_connection_router import router as pg_google_connection_router
from backend.apps.priority_guardian.routers.offboarding_router import router as pg_offboarding_router
# Priority Guardian app routers (Increment 02)
from backend.apps.priority_guardian.routers.priorities_router import router as pg_priorities_router
# Priority Guardian app routers (Increment 05)
from backend.apps.priority_guardian.routers.calendar_router import router as pg_calendar_router
# Priority Guardian app routers (Increment 06)
from backend.apps.priority_guardian.routers.weekly_report_router import router as pg_weekly_report_router
# Priority Guardian app routers (Increment 08)
from backend.apps.priority_guardian.routers.snapshot_router import router as pg_snapshot_router
# Priority Guardian app routers (Increment 21)
from backend.apps.priority_guardian.routers.pattern_router import router as pg_pattern_router
# Priority Guardian app routers (Increment 78)
from backend.apps.priority_guardian.routers.reconcile_router import router as pg_reconcile_router
# Priority Guardian app routers (Increment 89)
from backend.apps.priority_guardian.routers.widget_diagnostic import router as pg_widget_diagnostic_router

# Initialize logging first
configure_logging()

logger = get_logger(__name__)


def _assert_no_duplicate_routes(app: FastAPI) -> None:
    """Fail-fast at startup if any (method, path) pair is registered more than once.

    FastAPI silently overrides duplicate routes ("last one wins"), which can cause
    hard-to-diagnose production failures when two routers under the same prefix
    accidentally register identical sub-paths. This check converts silent shadow
    into a loud startup error.
    """
    from collections import Counter
    from fastapi.routing import APIRoute

    seen: Counter = Counter()
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                seen[(method, route.path)] += 1

    duplicates = {k: v for k, v in seen.items() if v > 1}
    if duplicates:
        raise RuntimeError(
            f"Duplicate routes detected (FastAPI silently overrides them): {duplicates}"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Startup
    logger.info("app.startup", app=settings.APP_NAME, environment=settings.ENV)

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
    # Redis is load-bearing for OAuth security (rate limiting, authorization
    # context, token replay). connect() raises on failure.
    await redis_client.connect()
    logger.info("Redis connection healthy")

    # Test database connection
    try:
        await test_connection()

    except Exception as e:
        logger.warning(f"Database connection failed: {e}")
        raise

    # Validate schema integrity (blocks startup if drift detected)
    from backend.core.schema_validator import validate_schema
    from backend.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        await validate_schema(session)

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


# -------------------------------------------------------------
# Root Health Check (for Render deploy health checks)
# -------------------------------------------------------------
# Fast, no auth, no DB - just confirms the app is running.
# Set Render Health Check Path to "/health" in dashboard.

@app.get("/health")
async def health_check():
    """Lightweight health check for deploy verification."""
    return {"status": "ok"}


# -------------------------------------------------------------
# robots.txt — Tell crawlers to stay out of the backend domain.
# This is the OAuth/API backend (priority-guard.com). The public
# marketing surface is fulfilling-productivity.com.
# -------------------------------------------------------------

@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    """Serve robots.txt to block all crawlers from the backend domain."""
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


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

    # Log validation errors for observability
    correlation_id = getattr(_.state, 'correlation_id', 'system')
    logger.warning(
        "http.validation_error",
        path=_.url.path,
        correlation_id=correlation_id,
        field_count=len(details),
    )

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
    Note: WWW-Authenticate headers are NOT emitted here. The AS does not know
    which RS the client is targeting, so it cannot emit resource_metadata headers.
    Token endpoint (token_endpoint.py) emits 'Bearer realm="oauth"' for 401s there.
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


# -------------------------------------------------------------
# Global Unhandled Exception Handler
# -------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Catch-all handler for unhandled exceptions.

    Ensures all 500 errors are logged with structured logging and correlation IDs,
    even from routes that don't have their own try/catch blocks.

    Re-raises exceptions that have their own handlers or require special handling.
    Does NOT log str(exc) — SQLAlchemy exceptions contain raw SQL with parameters.
    """
    import asyncio
    from fastapi import HTTPException
    from fastapi.exceptions import RequestValidationError

    # Re-raise exceptions that have dedicated handlers or need special handling
    if isinstance(exc, asyncio.CancelledError):
        raise exc  # Don't swallow - breaks graceful shutdown
    if isinstance(exc, (HTTPException, RequestValidationError, OAuthError)):
        raise exc  # These have their own handlers

    correlation_id = getattr(request.state, 'correlation_id', 'system')
    request_logger = logger.bind(correlation_id=correlation_id)

    # Log error_type only, NOT str(exc) — SQLAlchemy exceptions contain raw SQL
    request_logger.error(
        "http.unhandled_exception",
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method,
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
            }
        }
    )


# Add Correlation ID and Security Headers Middleware (Increment 7C)
# Middleware runs in reverse registration order (last registered = outermost = runs first)
# CorrelationIDMiddleware must be outermost so correlation_id is available to all inner middleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CorrelationIDMiddleware)


# Mount static files directory
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


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

# Priority Guardian SDK app routers (Increment 01)
app.include_router(pg_health_router, prefix="/api/priority-guardian")
app.include_router(pg_google_connection_router, prefix="/api/priority-guardian/google")
app.include_router(pg_offboarding_router, prefix="/api/priority-guardian")
# Priority Guardian SDK app routers (Increment 02)
app.include_router(pg_priorities_router, prefix="/api/priority-guardian")
# Priority Guardian SDK app routers (Increment 05)
app.include_router(pg_calendar_router, prefix="/api/priority-guardian")
# Priority Guardian SDK app routers (Increment 06)
app.include_router(pg_weekly_report_router, prefix="/api/priority-guardian")
# Priority Guardian SDK app routers (Increment 08)
app.include_router(pg_snapshot_router, prefix="/api/priority-guardian")
# Priority Guardian SDK app routers (Increment 21)
app.include_router(pg_pattern_router, prefix="/api/priority-guardian")
# Priority Guardian SDK app routers (Increment 78)
app.include_router(pg_reconcile_router, prefix="/api/priority-guardian")
# Priority Guardian SDK app routers (Increment 89)
app.include_router(pg_widget_diagnostic_router, prefix="/api/priority-guardian")

# Validate no duplicate routes across all registered routers.
# Runs at module import time, before uvicorn starts accepting requests.
_assert_no_duplicate_routes(app)
