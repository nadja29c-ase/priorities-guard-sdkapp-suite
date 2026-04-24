Important confirmation:

redis_client.connect() swallows exceptions (line: "Don't raise - allow app to start without Redis") and sets self._client = None
is_connected() returns False in that case
So main.py's if redis_client.is_connected() check IS the actual gate

My Redis-hardening fix for main.py alone is insufficient. If I only change main.py to raise, connect() still swallows the exception and returns normally — is_connected() returns False — then main.py raises. That works functionally but loses the original exception's traceback. Better: fix both places, or at minimum ensure the error message is useful.
Also noting: comments inside redis_client.py still say "Don't raise - allow app to start without Redis" and "gracefully degrade." Those comments contradict the hardening we're adding. The webhook helpers (check_webhook_idempotency, etc.) correctly fall back to "allow" when Redis is down — those are fine, because webhooks aren't security-critical. But connect()'s comment is now wrong.
The question is scope. Your rule: don't over-engineer, but don't take shortcuts. I'll scope the Redis fix to main.py + a minimal redis_client.connect() change so the startup error is actionable. Not touching the webhook helpers — those have correct degraded-mode behavior for their use case (non-security-critical).
Now the briefing.

Claude Code Briefing — main.py Quality Fixes (Post-Inc-78/79)
Context
Code review of backend/main.py after Inc 78, Inc 79, and B2-7 work identified three production-readiness gaps. This increment closes all three as one atomic PR (related area, small changes, single review).
Fix 1: Remove dead-code condition in OAuth exception handler (2 lines).
Fix 2: Harden Redis startup to raise instead of silently degrading (~8 lines across 2 files).
Fix 3: Add startup check for duplicate routes to prevent silent FastAPI route shadowing (~15 lines).
Scope
Fix 1 — OAuth exception handler: remove dead-code condition
File: backend/main.py
In oauth_exception_handler, the "WWW-Authenticate" not in headers condition is dead code. headers is initialized to {} two lines above, so the check is always True.
Replace:
python    # Build headers dict - add WWW-Authenticate for 401 on OAuth endpoints (B2-7)
    headers = {}
    if (
        exc.status_code == 401
        and request.url.path.startswith("/oauth/")
        and "WWW-Authenticate" not in headers
    ):
        headers["WWW-Authenticate"] = WWW_AUTHENTICATE_VALUE
With:
python    # Build headers dict - add WWW-Authenticate for 401 on OAuth endpoints (B2-7)
    headers = {}
    if exc.status_code == 401 and request.url.path.startswith("/oauth/"):
        headers["WWW-Authenticate"] = WWW_AUTHENTICATE_VALUE
Do not change any other part of oauth_exception_handler.
Fix 2 — Redis startup hardening
Background: Redis is load-bearing for OAuth security (rate limiting, authorization context, token replay prevention). Current startup treats Redis failure as "degraded mode" and continues serving, which silently disables rate limiting and token-replay protection. This is a latent security gap.
Two files change.
File: backend/core/redis_client.py
In RedisClient.connect(), make the failure path re-raise after logging, instead of silently setting self._client = None. Replace:
python    async def connect(self):
        """Initialize Redis connection pool."""
        try:
            self._client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            await self._client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            # Don't raise - allow app to start without Redis
            # Webhook handlers will gracefully degrade
            self._client = None
With:
python    async def connect(self):
        """Initialize Redis connection pool.

        Raises RuntimeError on failure. Redis is load-bearing for OAuth security
        (rate limiting, authorization context, token replay prevention) — the app
        MUST NOT serve requests without it. Runtime callers that observe temporary
        Redis unavailability (via is_connected()) still degrade gracefully; this
        change only affects the startup path.
        """
        try:
            self._client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            await self._client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            self._client = None
            logger.error(f"Redis connection failed at startup: {e}")
            raise RuntimeError(
                "Redis connection failed at startup. Redis is required for OAuth "
                "rate limiting, authorization context storage, and token replay "
                "prevention. Refusing to serve requests without it."
            ) from e
Do NOT touch is_connected(), get(), set(), delete(), or any other method. The webhook helpers (check_webhook_idempotency, check_renewal_throttle, set_needs_sync, etc.) correctly observe is_connected() for RUNTIME Redis unavailability — they remain unchanged. Only the STARTUP path changes.
File: backend/main.py
In lifespan, simplify the Redis startup block to rely on connect() raising. Replace:
python    # Initialize Redis connection
    await redis_client.connect()

    # Verify Redis connection health
    if redis_client.is_connected():
        logger.info("Redis connection healthy")
    else:
        logger.warning("Redis connection failed - webhook idempotency/throttling will be degraded")
        # Don't raise - app continues with degraded functionality
With:
python    # Initialize Redis connection
    # Redis is load-bearing for OAuth security (rate limiting, authorization
    # context, token replay). connect() raises on failure.
    await redis_client.connect()
    logger.info("Redis connection healthy")
Fix 3 — Duplicate route startup check
File: backend/main.py
Add a new helper function _assert_no_duplicate_routes and call it once at the end of the module, after all app.include_router(...) calls. Fails loudly at startup if two routers register the same (method, path) pair.
Add the helper function immediately after the import block at the top of the file (after the last from backend... import, before # Initialize logging first):
pythondef _assert_no_duplicate_routes(app: FastAPI) -> None:
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
At the very end of the file, after the last app.include_router(...) call, add:
python
# Validate no duplicate routes across all registered routers.
# Runs at module import time, before uvicorn starts accepting requests.
_assert_no_duplicate_routes(app)
Implementation Approach — Copy and Adjust, Never Rewrite

Copy backend/main.py verbatim. Make only the three changes listed above.
Copy backend/core/redis_client.py verbatim. Change ONLY the connect() method body + docstring. Do NOT touch any other method, helper function, or comment elsewhere in the file.
Do NOT change any other file.
Do NOT reorder imports, rename variables, or reformat existing code.
Do NOT adjust the webhook helper functions (check_webhook_idempotency, check_renewal_throttle, set_needs_sync, get_needs_sync, delete_needs_sync). Their existing behavior (fall back to "allow" / "no sync" when Redis is down) is correct for their non-security-critical use case and is out of scope.
Do NOT touch the schema validation, DB connection test, or OAuth key validation blocks in lifespan.
Do NOT change the global exception handler. (ChatGPT's suggestion to log repr(exc) was rejected — repr() of SQLAlchemy exceptions leaks SQL + parameters, which is a GDPR violation for this backend.)

Out of Scope

Changes to webhook idempotency / throttle / needs_sync helpers in redis_client.py
Changes to the global global_exception_handler
Changes to any router file
DB connection retry logic (Render platform handles this)
Schema validator changes
HTTP client timeout audit (that's a caller-site concern, not a main.py concern)
Documenting the cancelled OAuth resource allowlist (handled separately in ADR 003)

Tests
Unit tests
File: tests/unit/core/test_assert_no_duplicate_routes.py (new)
python"""
Unit test for _assert_no_duplicate_routes in backend/main.py.

Verifies that the duplicate-route guard fails loudly when two routers register
the same (method, path), and passes silently otherwise.
"""

import pytest
from fastapi import FastAPI, APIRouter

from backend.main import _assert_no_duplicate_routes


def test_no_duplicates_passes():
    """App with unique routes passes the check."""
    app = FastAPI()
    r1 = APIRouter()

    @r1.get("/foo")
    async def foo():
        return {"ok": True}

    @r1.get("/bar")
    async def bar():
        return {"ok": True}

    app.include_router(r1)
    _assert_no_duplicate_routes(app)  # Should not raise


def test_duplicate_raises():
    """Two routers registering the same (method, path) raises RuntimeError."""
    app = FastAPI()
    r1 = APIRouter()
    r2 = APIRouter()

    @r1.get("/collision")
    async def collision_v1():
        return {"version": 1}

    @r2.get("/collision")
    async def collision_v2():
        return {"version": 2}

    app.include_router(r1)
    app.include_router(r2)

    with pytest.raises(RuntimeError, match="Duplicate routes detected"):
        _assert_no_duplicate_routes(app)


def test_same_path_different_methods_passes():
    """Same path with different HTTP methods is not a duplicate."""
    app = FastAPI()
    r = APIRouter()

    @r.get("/resource")
    async def get_resource():
        return {"ok": True}

    @r.post("/resource")
    async def post_resource():
        return {"ok": True}

    app.include_router(r)
    _assert_no_duplicate_routes(app)  # Should not raise
Integration tests
No new integration tests required. The Fix 1 dead-code removal doesn't change observable behavior. Fix 2's new behavior (startup raise on Redis down) is tested indirectly by the existing startup path — if Redis is down, the app fails to start, and existing integration tests using fake_redis_client fixture continue to work unchanged.
Existing tests that must continue to pass:

Any test using fake_redis_client fixture (patches redis_client globally; connect() is not called in test context)
OAuth integration tests (authorize, token, register) — Fix 1 only removes dead code, no behavior change
Inc 78 reconcile tests — no change to reconcile paths

Pre-Deploy Checklist
Before committing, read doc/OPERATIONS_PREDEPLOY.md.
Before deploying:

Verify Redis is reachable from the backend service on Render. The REDIS_URL env var must point to a healthy Redis instance. With Fix 2, if Redis is unavailable at deploy time, the backend will fail to start — Render will retry via its standard platform retry mechanism.
No new env vars required.
No DB migration required.

Acceptance Criteria

 oauth_exception_handler no longer has the "WWW-Authenticate" not in headers check
 oauth_exception_handler's behavior is otherwise identical (headers dict still initialized to {}, WWW-Authenticate still added under the same two conditions)
 RedisClient.connect() raises RuntimeError on connection failure
 RedisClient.connect()'s error includes the chained original exception (raise ... from e)
 main.py lifespan block calls await redis_client.connect() without follow-up is_connected() check
 _assert_no_duplicate_routes function exists at module scope in main.py
 _assert_no_duplicate_routes(app) is called at the end of main.py after all include_router calls
 Three new unit tests in tests/unit/core/test_assert_no_duplicate_routes.py pass
 No other methods in redis_client.py are modified
 Webhook helpers (check_webhook_idempotency etc.) are unchanged
 global_exception_handler is unchanged
 Existing test suites pass: pytest tests/unit tests/integration -v

Files Touched

backend/main.py (modified)
backend/core/redis_client.py (modified — only connect())
tests/unit/core/test_assert_no_duplicate_routes.py (new)

That's it. Three small, correct, production-grade quality fixes.

Effort estimate:

Claude Code implementation: ~30 min
Review: ~15 min
Deploy: standard