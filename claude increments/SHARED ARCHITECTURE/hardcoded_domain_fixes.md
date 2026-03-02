# Hygiene: Hardcoded Domain Fixes

## Context

Three files contain hardcoded production domains instead of using config values. These break portability and create silent failures if domains change.

## Fix 1: PG resources.py — redirect_domains

**File:** `mcp_server/priority_guardian/handlers/resources.py`

`redirect_domains` is hardcoded to `"https://priorities-guard-sdkapp-suite.onrender.com"` in 3 places (list_resources, list_resource_templates, handle_read_resource). Meanwhile `ui.domain` already correctly uses `WIDGET_DOMAIN` from config.

**What to do:**

Import BACKEND_URL from the MCP server config:
```python
from mcp_server.priority_guardian.config import MCP_SERVER_URL, BACKEND_URL
```

At module level, add:
```python
BACKEND_DOMAIN = _extract_origin(BACKEND_URL)
```

`BACKEND_URL` already exists in `mcp_server/priority_guardian/config.py` as:
```python
BACKEND_URL = get_env("PG_BACKEND_URL", default="http://localhost:8000").rstrip("/")
```

Replace all 3 occurrences of:
```python
"redirect_domains": ["https://priorities-guard-sdkapp-suite.onrender.com"],
```
with:
```python
"redirect_domains": [BACKEND_DOMAIN],
```

**Render env var `PG_BACKEND_URL`** must be set to `https://priorities-guard-sdkapp-suite.onrender.com` in production. Verify this is already set — if not, add it before deploying.

## Fix 2: google_calendar.py — User-Agent

**File:** `backend/core/google_calendar.py`

Line ~20:
```python
GOOGLE_USER_AGENT = "Focused/1.0 (+https://www.priority-guard.com)"
```

This module is shared across Focused and Priority Guardian. The User-Agent should reflect the suite, not a single app, and use the configured domain.

Replace with:
```python
from backend.core.config import settings

GOOGLE_USER_AGENT = f"PriorityGuardSuite/1.0 (+{settings.BACKEND_PUBLIC_URL})"
```

`settings` is already imported in this file. `BACKEND_PUBLIC_URL` already exists in config with default `"https://www.priority-guard.com"`.

## Fix 3: google_calendar.py — Webhook address (TWO issues)

**File:** `backend/core/google_calendar.py`

In `register_webhook()`, line ~156:
```python
"address": f"https://www.priority-guard.com/webhook/focused/google_calendar/{user_id}",
```

This has **two problems**:

**Problem A: Hardcoded domain** — must use config.

**Problem B: `/{user_id}` in path is a latent bug.** The webhook route handler is mounted at `/webhook/focused/google_calendar` with NO `{user_id}` path parameter. The route resolves the user via `X-Goog-Channel-ID` header lookup in the DB. If this webhook registration were ever called, Google would POST to `/webhook/focused/google_calendar/{user_id}` and get a 404 because FastAPI has no matching route.

Replace with:
```python
"address": f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/webhook/focused/google_calendar",
```

The `.rstrip('/')` prevents double-slash if `BACKEND_PUBLIC_URL` ends with `/`. The `{user_id}` is removed because the route doesn't accept it — user identification happens via the `X-Goog-Channel-ID` header.

`settings` is already imported. No new dependencies.

**Note:** The `user_id` parameter to `register_webhook()` is still needed — it's used by the caller (`logic_registerwebhook.py`) for logging and connection lookup. It is NOT needed in the webhook URL itself.

## What NOT to change

- `backend/core/config.py` — no changes needed, `BACKEND_PUBLIC_URL` already exists
- `mcp_server/priority_guardian/config.py` — no changes needed, `BACKEND_URL` already exists
- Clarity resources.py — already clean
- Google API endpoint URLs (googleapis.com) — correct to hardcode
- Redis timeouts, retry counts, Celery task timeouts — correct to hardcode
- Rate limit values — correct to hardcode
- Any migration or model

## Unit Tests

No new tests needed. These are config wiring changes with no branching logic. Existing tests that mock these values will continue to work.

Verify manually after deploy:
1. MCP Inspector: check `redirect_domains` in resource `_meta` uses correct backend domain
2. Google Calendar: register a test webhook, confirm the `address` field uses `BACKEND_PUBLIC_URL`

## Pre-Deploy

- Verify Render env var `PG_BACKEND_URL` is set for the MCP server service
- Verify Render env var `BACKEND_PUBLIC_URL` is set for the backend service
- Read `doc/OPERATIONS_PREDEPLOY.md` for additional checks

## Risk

Minimal. Pure config wiring. No logic changes. If env vars are already set (which they should be), behavior is identical to current hardcoded values.
