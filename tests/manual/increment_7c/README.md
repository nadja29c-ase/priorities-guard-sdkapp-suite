# Increment 7C Manual Tests

Manual tests for logging, middleware, and security headers.

## Prerequisites

1. **Server must be running** (Terminal 2):
   ```bash
   cd "/Users/nadja/Desktop/Priority Guard Suite/priority-guardian"
   uvicorn backend.main:app --reload --port 8000
   ```

2. **Open Terminal 2** to watch logs during tests

## Test 1: Server Startup (Manual Check)

Check Terminal 2 logs for:
- ✅ Structured JSON logs
- ✅ `"correlation_id": "system"`
- ✅ `"event": "logging.configured"`

## Test 2: Correlation ID Propagation

```bash
bash tests/manual/increment_7c/test_2_correlation_id.sh
```

**Expected:**
- Step 1: Response header `X-Correlation-ID: test-manual-123`
- Step 2: Response header `X-Correlation-ID: <UUID>`
- Terminal 2 logs show matching correlation_id

## Test 3: Security Headers

```bash
bash tests/manual/increment_7c/test_3_security_headers.sh
```

**Expected Output:** All 6 headers on both endpoints:
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains
Cache-Control: no-store
Pragma: no-cache
```

## Test 4: Log Format Validation

```bash
bash tests/manual/increment_7c/test_4_log_format.sh
```

**Manual verification:**
1. Copy a log line from Terminal 2
2. Test it's valid JSON:
   ```bash
   echo '{"timestamp":"..."}' | python3 -m json.tool
   ```

**Expected fields:**
- `timestamp` (ISO 8601)
- `level` (info/warning/error)
- `correlation_id` (UUID)
- `event` (dot-notation)

## Test 5: Sensitive Data Scrubbing (Manual)

**During any OAuth test**, check Terminal 2 logs for sensitive fields:

**Expected (PASS):**
```json
{
  "access_token": "[REDACTED]",
  "refresh_token": "[REDACTED]",
  "client_secret": "[REDACTED]"
}
```

**Not Expected (FAIL):**
```json
{
  "access_token": "eyJhbGci...",  ❌ Exposed!
  "client_id": "focused-client-...",  ✅ OK (not sensitive)
}
```

## Test 6: OAuth Error Response Format

```bash
bash tests/manual/increment_7c/test_6_oauth_errors.sh
```

**Expected:**
- **Step 6.1** (invalid scope): RFC 6749 error redirect to `redirect_uri?error=invalid_scope&error_description=...&state=...`
- **Step 6.2** (invalid client_id): HTTP 401 error (not redirected - security best practice)
- Terminal 2 shows `"event": "oauth.error"`

**Note on OAuth error handling:**
- **Missing required parameters** → FastAPI validation errors (correct behavior)
- **Invalid client_id or redirect_uri** → HTTP errors (can't trust untrusted client/redirect_uri)
- **Invalid scope/response_type** (trusted client) → RFC 6749 error redirect

---

## Optional Tests (Require Redis/Celery)

### Test 7: Rate Limit Logging

**Prerequisites:** Redis must be running

```bash
for i in {1..25}; do
  curl -s http://localhost:8000/oauth/focused/authorize?client_id=test 2>&1 | head -1
done
```

**Check Terminal 2 for:**
```json
{
  "event": "rate_limit.exceeded",
  "key_pattern": "ratelimit:oauth:authorize",
  "count": 21,
  "limit": 20
}
```

### Test 8: Background Job Logging

**Prerequisites:** Celery worker and beat scheduler running

Start in separate terminals:
```bash
# Terminal 3:
poetry run celery -A backend.core.celery_app worker --loglevel=info

# Terminal 4:
poetry run celery -A backend.core.celery_app beat --loglevel=info
```

**Check for:**
```json
{
  "event": "oauth.cleanup.codes.start",
  "correlation_id": "<UUID>"
}
{
  "event": "oauth.cleanup.codes.complete",
  "deleted_count": 0
}
```

---

## Quick Test Summary

**Minimum tests (no Redis/Celery):**
- ✅ Test 1: Server startup logs
- ✅ Test 2: Correlation ID propagation
- ✅ Test 3: Security headers
- ✅ Test 4: Log format
- ✅ Test 5: Sensitive data scrubbing (during OAuth tests)
- ✅ Test 6: OAuth error format

**Optional tests (need Redis/Celery):**
- ⏳ Test 7: Rate limit logging
- ⏳ Test 8: Background job logging

**Estimated time:** 5-10 minutes for core tests
