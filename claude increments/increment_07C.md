Increment 7C: Structured Logging + Security Hardening (Production-Ready)

Goal: Add correlation ID tracing across both servers, structured logging with proper retention, global security headers, and minimal monitoring for OAuth provider.

Architecture Reality Check
Two-server system:

MCP Server (port 8001) - receives ChatGPT requests, validates tokens
Backend (port 8000) - executes business logic, accesses DB/Redis

Correlation flow must work across this boundary:
ChatGPT → MCP (generates/receives correlation_id) 
       → Backend (receives correlation_id via header)
       → Redis/Celery (logs with same correlation_id)

Core Deliverables
1. Cross-Server Correlation ID Propagation
File: backend/core/middleware.py (NEW)
pythonfrom fastapi import Request
from uuid import uuid4

@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    # Accept from upstream (MCP server) or generate
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
    request.state.correlation_id = correlation_id
    
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response
File: backend/apps/focused/mcp_server.py (MODIFY)
python# When MCP forwards to backend:
async def call_backend_api(endpoint: str, params: dict, correlation_id: str):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Correlation-ID": correlation_id  # ← CRITICAL
    }
    response = await http_client.post(
        f"http://localhost:8000{endpoint}",
        json=params,
        headers=headers
    )
    return response
2. Structured Logging with Retention Strategy
File: backend/core/logging_config.py (NEW)
pythonimport structlog
import logging

def configure_logging(environment: str = "production"):
    # Log levels by environment
    level = logging.INFO if environment == "production" else logging.DEBUG
    
    # Scrub sensitive data
    def scrub_sensitive(logger, method_name, event_dict):
        REDACT_KEYS = [
            "access_token", "refresh_token", "authorization_code","authorization",
            "code_verifier", "client_secret", "password"
        ]
        for key in REDACT_KEYS:
            if key in event_dict:
                event_dict[key] = "[REDACTED]"
        return event_dict
    
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            scrub_sensitive,  # ← Prevent token leakage
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    
    logging.basicConfig(
        format="%(message)s",
        level=level,
        stream=sys.stdout  # → CloudWatch Logs
    )

logger = structlog.get_logger()
Log Level Policy:

INFO: Business events (token issued, webhook received, calendar synced)
WARNING: Rate limits hit, renewal needed
ERROR: OAuth failures, API errors, validation failures
CRITICAL: Security violations, PKCE failures, token revocation errors

Retention Policy:

CloudWatch Log Groups: 30 days (matches compliance requirements)
Log Groups:

/focused/backend (port 8000)
/focused/mcp (port 8001)


Estimated volume at 40K DAU: ~2-3 GB/month

3. Usage in OAuth Endpoints
File: backend/core/oauth_provider.py (MODIFY)
python@router.post("/oauth/focused/token")
async def token_endpoint(request: Request, ...):
    correlation_id = request.state.correlation_id
    
    logger.info(
        "oauth.token.request",
        correlation_id=correlation_id,
        grant_type=grant_type,
        client_id=client_id
    )
    
    try:
        # ... token logic ...
        logger.info(
            "oauth.token.success",
            correlation_id=correlation_id,
            jti=jti,
            scope=scope
        )
    except InvalidGrantError as e:
        logger.error(
            "oauth.token.error",
            correlation_id=correlation_id,
            error_type="invalid_grant",
            error=str(e)
        )
        raise
NEVER log: tokens, codes, verifiers, client secrets
ALWAYS log: correlation_id, client_id, grant_type, scope, JTI, error types

4. Global Security Headers
File: backend/core/middleware.py (MODIFY)
python@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    
    # Apply to ALL endpoints (OAuth, webhooks, health, API)
    response.headers.update({
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Cache-Control": "no-store",
        "Pragma": "no-cache"
    })
    return response

5. Enhanced Rate Limit Logging
File: backend/core/rate_limit.py (MODIFY from 7B)
pythonasync def check_rate_limit(key: str, limit: int, window: int, request: Request):
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window)
    
    if count > limit:
        logger.warning(
            "rate_limit.exceeded",
            correlation_id=request.state.correlation_id,
            key_pattern=key.split(":")[0],  # Don't log IP
            count=count,
            limit=limit,
            window=window
        )
        raise RateLimitExceeded(retry_after=window)

6. Celery Job Logging
File: backend/core/celery_app.py (MODIFY)
python@celery_app.task
def cleanup_expired_tokens():
    correlation_id = str(uuid4())  # Generate for background job
    
    logger.info(
        "oauth.cleanup.start",
        correlation_id=correlation_id
    )
    
    deleted_codes = db.query(OAuthAuthorizationCode).filter(
        OAuthAuthorizationCode.expires_at < datetime.now(UTC)
    ).delete()
    
    deleted_tokens = db.query(OAuthAccessToken).filter(
        OAuthAccessToken.expires_at < datetime.now(UTC)
    ).delete()
    
    db.commit()
    
    logger.info(
        "oauth.cleanup.complete",
        correlation_id=correlation_id,
        deleted_codes=deleted_codes,
        deleted_tokens=deleted_tokens
    )
```

### 7. Minimal Monitoring (CloudWatch Insights)

**CloudWatch Log Insights Queries:**
```
# OAuth token failures (alert if >5/min)
fields @timestamp, correlation_id, error_type, client_id
| filter @message like /oauth.token.error/
| stats count() as failures by bin(1m)
| filter failures > 5
```
```
# Webhook processing errors
fields @timestamp, correlation_id, user_id, error_type
| filter @message like /webhook.google_calendar.error/
| stats count() by bin(5m)
```
```
# Rate limit violations
fields @timestamp, correlation_id, key_pattern
| filter @message like /rate_limit.exceeded/
| stats count() by key_pattern, bin(5m)
Alert Configuration (CloudWatch Alarms):

OAuth token failures: >5 errors/min → Email to support@priority-guard.com
Webhook failures: >10 errors/5min → Email alert
Google API rate limit: >3 hits/hour → Email alert

8. Standardized Error Responses
File: backend/core/oauth_exceptions.py (NEW)
pythonclass OAuthError(Exception):
    def __init__(self, error: str, description: str, status_code: int):
        self.error = error
        self.description = description
        self.status_code = status_code

class InvalidClientError(OAuthError):
    def __init__(self, description: str = "Invalid client"):
        super().__init__("invalid_client", description, 401)

class InvalidGrantError(OAuthError):
    def __init__(self, description: str = "Invalid grant"):
        super().__init__("invalid_grant", description, 400)

@app.exception_handler(OAuthError)
async def oauth_error_handler(request: Request, exc: OAuthError):
    correlation_id = getattr(request.state, "correlation_id", str(uuid4()))
    
    logger.error(
        "oauth.error",
        correlation_id=correlation_id,
        error=exc.error,
        description=exc.description
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error,
            "error_description": exc.description
        },
        headers={
            "X-Correlation-ID": correlation_id,
            "WWW-Authenticate": f'Bearer realm="{settings.OAUTH_ISSUER}"'
        }
    )

Testing Requirements
1. Cross-Server Correlation Test
pythonasync def test_correlation_propagation():
    # MCP generates correlation_id
    correlation_id = str(uuid4())
    
    # MCP forwards to backend
    response = await mcp_client.call_tool(
        "check_calendar",
        headers={"X-Correlation-ID": correlation_id}
    )
    
    # Verify backend received it
    backend_logs = get_logs(correlation_id)
    assert len(backend_logs) > 0
    assert all(log["correlation_id"] == correlation_id for log in backend_logs)
2. Log Format Validation
pythondef test_log_format():
    # Generate log entry
    logger.info("test.event", user_id="123", scope="read")
    
    # Parse as JSON
    log_line = capture_stdout()
    log_data = json.loads(log_line)
    
    # Verify required fields
    assert "timestamp" in log_data
    assert "level" in log_data
    assert "event" in log_data
    assert log_data["event"] == "test.event"
3. Token Scrubbing Test
pythondef test_token_scrubbing():
    logger.info(
        "oauth.test",
        access_token="secret123",
        client_id="valid-client"
    )
    
    log_line = capture_stdout()
    log_data = json.loads(log_line)
    
    assert log_data["access_token"] == "[REDACTED]"
    assert log_data["client_id"] == "valid-client"
4. Performance Test
python@pytest.mark.benchmark
def test_logging_performance():
    # Baseline without logging
    start = time.time()
    for _ in range(1000):
        process_request()
    baseline = time.time() - start
    
    # With structured logging
    start = time.time()
    for _ in range(1000):
        logger.info("test", data="value")
        process_request()
    with_logging = time.time() - start
    
    # Logging overhead must be <10% of request time
    overhead = (with_logging - baseline) / baseline
    assert overhead < 0.10
5. Security Headers Test
pythonasync def test_security_headers_all_endpoints():
    endpoints = [
        "/api/focused/health",
        "/oauth/focused/authorize",
        "/webhook/focused/google_calendar/123"
    ]
    
    for endpoint in endpoints:
        response = await client.get(endpoint)
        assert "X-Content-Type-Options" in response.headers
        assert "Strict-Transport-Security" in response.headers
        assert response.headers["Cache-Control"] == "no-store"

Dependencies
toml[tool.poetry.dependencies]
structlog = "^24.1.0"
python-json-logger = "^2.0.7"  # Fallback if structlog fails
```

---

## Deferred to Later Increments

- ❌ Full observability stack (Prometheus/Grafana) → at 10K users per scale plan
- ❌ Distributed tracing (OpenTelemetry) → add if debugging becomes critical
- ❌ Custom dashboards → start with CloudWatch queries
- ❌ Metrics exporters → defer until monitoring needs clarify
- ❌ Log aggregation beyond CloudWatch → only if multi-region deployment happens

---

## File Changes
```
backend/
├── core/
│   ├── middleware.py              # NEW: correlation + security headers
│   ├── logging_config.py          # NEW: structlog setup + scrubbing
│   ├── oauth_exceptions.py        # NEW: standardized errors
│   ├── oauth_provider.py          # MODIFY: add logging
│   ├── rate_limit.py              # MODIFY: add logging (from 7B)
│   └── celery_app.py              # MODIFY: add logging to cleanup jobs
├── apps/focused/
│   ├── mcp_server.py              # MODIFY: forward correlation_id
│   └── logic_sync.py              # MODIFY: add logging to sync pipeline
└── main.py                        # MODIFY: register middleware + exception handlers

Success Criteria

✅ Any request can be traced from ChatGPT → MCP → Backend → Redis using correlation_id
✅ All OAuth/webhook failures logged with context (no token leakage)
✅ Security headers present on every endpoint (verified via tests)
✅ CloudWatch alerts fire when error rates exceed thresholds
✅ Log scrubbing prevents sensitive data exposure
✅ Performance overhead from logging <10ms P95 latency increase


Verification Steps

Start both servers (MCP + Backend)
Make OAuth request → verify correlation_id in both log streams
Trigger rate limit → verify warning logged with key pattern
View CloudWatch Logs → confirm JSON formatting + no token leakage
Run load test → confirm P95 latency stays under budget
RetryClaude can make mistakes. Please double-check responses.