# Increment 18: Google Connection MCP Tools

## Goal

Implement MCP tools that allow users to connect and disconnect their Google Calendar account through ChatGPT. This bridges the gap between ChatGPT OAuth (inbound) and Google OAuth (outbound).

## Why This Is Needed

After completing ChatGPT OAuth, the user has a valid token but **no Google Calendar connection**. Currently:
- `check_calendar` fails with "Google not connected"
- User has no way to initiate Google OAuth from within ChatGPT
- The `/auth/focused/google/start` endpoint exists but requires `user_id` which cannot be safely exposed in a URL

**Solution:** MCP tools that generate opaque, single-use tokens for secure OAuth initiation.

---

## Scope

### In Scope
- **MCP Server:** Two new tools + one new helper function
- **Backend:** Two new endpoints + two new helper functions
- **Backend:** Modify existing `/start` endpoint to accept opaque token
- **Config:** One new environment variable

### Out of Scope
- Changes to Google OAuth callback (`/auth/focused/google/callback`)
- Changes to existing `/api/focused/disconnect` endpoint (Increment 10)
- Widget UI (future increment)
- Cross-app shared tooling (future architecture decision)

---

## Security Design: Opaque Token Flow

**Problem:** We cannot expose `user_id` in browser URLs because:
- URLs are visible to users (violates pseudonymous principle)
- URLs can be logged, shared, or intercepted
- Violates OpenAI store policies on internal identifier exposure

**Solution:** Use short-lived, single-use opaque tokens.

### Two Redis Layers (By Design)

The flow uses two separate Redis keys for different purposes:

```
Layer 1: google_connect:{token}
├── Purpose: Bridge ChatGPT → browser securely
├── Created by: POST /api/focused/google/initiate-connection
├── Contains: user_id
├── TTL: 10 minutes
└── Consumed by: GET /auth/focused/google/start?token=xxx

Layer 2: oauth_state:{state} (EXISTING - Increment 11)
├── Purpose: CSRF protection for Google callback
├── Created by: /auth/focused/google/start (after token validation)
├── Contains: {user_id, code_verifier}
├── TTL: 10 minutes
└── Consumed by: /auth/focused/google/callback
```

This is correct - they serve different security purposes.

### Flow Diagram

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐      ┌─────────┐
│   ChatGPT   │      │ MCP Server  │      │   Backend   │      │  Redis  │
└──────┬──────┘      └──────┬──────┘      └──────┬──────┘      └────┬────┘
       │                    │                    │                   │
       │ call connect_      │                    │                   │
       │ google_calendar    │                    │                   │
       │───────────────────▶│                    │                   │
       │                    │                    │                   │
       │                    │ GET /api/focused/  │                   │
       │                    │ google/connection- │                   │
       │                    │ status             │                   │
       │                    │───────────────────▶│                   │
       │                    │                    │                   │
       │                    │  {connected: false}│                   │
       │                    │◀───────────────────│                   │
       │                    │                    │                   │
       │                    │ POST /api/focused/ │                   │
       │                    │ google/initiate    │                   │
       │                    │───────────────────▶│                   │
       │                    │                    │                   │
       │                    │                    │ SET google_connect│
       │                    │                    │ :{token} = user_id│
       │                    │                    │ EX 600            │
       │                    │                    │──────────────────▶│
       │                    │                    │                   │
       │                    │   {token, url}     │                   │
       │                    │◀───────────────────│                   │
       │                    │                    │                   │
       │  {connect_url}     │                    │                   │
       │◀───────────────────│                    │                   │
       │                    │                    │                   │
       │ User clicks URL ═══════════════════════▶│                   │
       │ (browser request)  │                    │                   │
       │                    │                    │ GET google_connect│
       │                    │                    │ :{token}          │
       │                    │                    │──────────────────▶│
       │                    │                    │                   │
       │                    │                    │ DEL google_connect│
       │                    │                    │ :{token}          │
       │                    │                    │──────────────────▶│
       │                    │                    │                   │
       │                    │                    │ SET oauth_state:  │
       │                    │                    │ {state}={user_id, │
       │                    │                    │ code_verifier}    │
       │                    │                    │──────────────────▶│
       │                    │                    │                   │
       │◀═══════════════════════════════════════│                   │
       │         Redirect to Google OAuth        │                   │
```

---

## MCP Tools to Implement

### 1. `connect_google_calendar`

**Purpose:** Check Google connection status and provide secure connect URL if needed.

**Required Scope:** `focused.write`

**Input Parameters:** None (user identity comes from JWT)

**Output - Already Connected:**
```json
{
  "success": true,
  "data": {
    "status": "connected",
    "connected_at": "2025-01-15T10:30:00Z",
    "message": "Google Calendar is already connected."
  }
}
```

**Output - Not Connected:**
```json
{
  "success": true,
  "data": {
    "status": "not_connected",
    "connect_url": "https://api.priority-guard.com/auth/focused/google/start?token=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
    "expires_in": 600,
    "message": "Click the link to connect your Google Calendar. The link expires in 10 minutes."
  }
}
```

**Implementation Pattern:**
```python
@mcp.tool(
    name="connect_google_calendar",
    description="Check Google Calendar connection status. If not connected, returns a secure link to connect."
)
@handle_mcp_errors("connect_google_calendar")
async def connect_google_calendar(
    meta: Optional[Dict[str, Any]] = None
) -> str:
    tool_name = "connect_google_calendar"
    
    auth_context = await authenticate_request(tool_name, meta)
    user_id = auth_context["user_id"]
    correlation_id = auth_context["correlation_id"]
    
    # Check current connection status
    status_response = await backend_get(
        "/api/focused/google/connection-status",
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    if status_response.get("connected"):
        return json.dumps({
            "success": True,
            "data": {
                "status": "connected",
                "connected_at": status_response.get("connected_at"),
                "message": "Google Calendar is already connected."
            }
        })
    
    # Not connected - get connection URL
    initiate_response = await backend_post(
        "/api/focused/google/initiate-connection",
        {},
        user_id=user_id,
        correlation_id=correlation_id
    )
    
    return json.dumps({
        "success": True,
        "data": {
            "status": "not_connected",
            "connect_url": initiate_response["connect_url"],
            "expires_in": initiate_response["expires_in"],
            "message": "Click the link to connect your Google Calendar. The link expires in 10 minutes."
        }
    })
```

---

### 2. `disconnect_google_calendar`

**Purpose:** Disconnect Google Calendar and revoke tokens.

**Required Scope:** `focused.write`

**Input Parameters:** 
- `confirm` (boolean, required): User must confirm disconnection

**Output - Success:**
```json
{
  "success": true,
  "data": {
    "status": "disconnected",
    "message": "Google Calendar has been disconnected. Your calendar data has been removed."
  }
}
```

**Output - Not Connected:**
```json
{
  "success": true,
  "data": {
    "status": "not_connected",
    "message": "Google Calendar is not connected."
  }
}
```

**Output - Confirmation Required:**
```json
{
  "success": false,
  "error": {
    "code": "CONFIRMATION_REQUIRED",
    "message": "Please confirm disconnection by setting confirm=true. This will revoke access and delete cached calendar data."
  }
}
```

**Implementation Notes:**
- Reuses existing `POST /api/focused/disconnect` from Increment 10
- That endpoint already handles: Google token revocation, webhook channel stop, cache clearing, idempotency

---

## Backend Changes

### 1. New File: `backend/apps/focused/routers/google_connection_router.py`

```python
"""
Google connection status and initiation endpoints.

Increment 18: Provides MCP tools with connection status and secure OAuth initiation.
"""

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.models import CoreConnection
from backend.core.google_oauth import store_connection_token
from backend.core.config import settings

router = APIRouter(tags=["Google Connection"])


@router.get("/connection-status")
async def get_connection_status(
    x_user_id: str = Header(..., alias="X-User-ID"),
    session: AsyncSession = Depends(get_db),
):
    """
    Check if user has an active Google Calendar connection.
    
    Called by MCP server with X-User-ID header.
    """
    result = await session.execute(
        select(CoreConnection).where(
            CoreConnection.user_id == x_user_id,
            CoreConnection.provider == "google",
            CoreConnection.revoked_at.is_(None),
        )
    )
    connection = result.scalar_one_or_none()
    
    if connection:
        return {
            "connected": True,
            "connected_at": connection.created_at.isoformat() if connection.created_at else None,
            "scopes": connection.scopes,
        }
    
    return {"connected": False}


@router.post("/initiate-connection")
async def initiate_connection(
    x_user_id: str = Header(..., alias="X-User-ID"),
):
    """
    Generate a secure, single-use token for Google OAuth initiation.
    
    Returns an opaque token that can be used in a browser URL.
    The token expires in 10 minutes and can only be used once.
    
    Security:
        - Token is cryptographically random (secrets.token_urlsafe)
        - Token stored in Redis with 10-minute TTL
        - Token deleted after first use (single-use)
        - user_id never exposed in URL
    """
    token = await store_connection_token(x_user_id)
    
    connect_url = f"{settings.BACKEND_PUBLIC_URL}/auth/focused/google/start?token={token}"
    
    return {
        "token": token,
        "connect_url": connect_url,
        "expires_in": 600,
    }
```

---

### 2. Add to `backend/core/config.py`

```python
# Add to Settings class:

# Public URL for browser-facing endpoints (used in OAuth initiation)
BACKEND_PUBLIC_URL: str = "https://api.priority-guard.com"
```

**Also add to Railway environment variables.**

---

### 3. Add to `backend/core/google_oauth.py`

Add these two functions alongside existing `store_oauth_state()` and `verify_and_get_oauth_state()`:

```python
import secrets
from backend.core.redis_client import redis_client

# Connection token TTL (10 minutes)
CONNECTION_TOKEN_TTL = 600


async def store_connection_token(user_id: str) -> str:
    """
    Generate and store an opaque token for Google OAuth initiation.
    
    The token maps to user_id in Redis and expires after 10 minutes.
    Used to securely initiate Google OAuth without exposing user_id in URL.
    
    Args:
        user_id: The user's internal ID
        
    Returns:
        Opaque token string (43 characters, URL-safe)
    """
    token = secrets.token_urlsafe(32)
    redis_key = f"google_connect:{token}"
    
    await redis_client.set(redis_key, user_id, ex=CONNECTION_TOKEN_TTL)
    
    return token


async def verify_connection_token(token: str) -> str | None:
    """
    Verify and consume a connection token.
    
    Retrieves the user_id associated with the token and deletes the token
    (single-use). Returns None if token is invalid or expired.
    
    Args:
        token: The opaque token from the URL
        
    Returns:
        user_id if valid, None if invalid/expired
    """
    redis_key = f"google_connect:{token}"
    
    # Get and delete atomically would be ideal, but GET + DEL is acceptable
    user_id = await redis_client.get(redis_key)
    
    if user_id is None:
        return None
    
    # Delete token (single-use)
    await redis_client.delete(redis_key)
    
    # Redis returns bytes, decode if necessary
    if isinstance(user_id, bytes):
        user_id = user_id.decode("utf-8")
    
    return user_id
```

---

### 4. Modify `backend/apps/focused/routers/oauth_google_router.py`

**Change the `/start` endpoint signature and add token validation:**

```python
# REPLACE the existing start_google_oauth function

from backend.core.google_oauth import (
    exchange_code,
    generate_auth_url_with_pkce,
    generate_code_challenge,
    generate_code_verifier,
    generate_state_token,
    store_oauth_state,
    verify_and_get_oauth_state,
    verify_connection_token,  # ADD THIS IMPORT
)


@router.get("/start")
async def start_google_oauth(
    request: Request,
    token: str = Query(..., description="Opaque connection token from /api/focused/google/initiate-connection"),
):
    """
    Initiate Google OAuth flow with PKCE.

    Security (Increment 18):
        - Accepts opaque token instead of user_id (user_id never in URL)
        - Token is single-use (deleted after validation)
        - Token expires after 10 minutes
        - Generates PKCE code_verifier and code_challenge (S256)
        - Stores state + user_id + code_verifier in Redis (10-min TTL)

    Args:
        request: FastAPI request object
        token: Opaque connection token (required query parameter)

    Returns:
        307 redirect to Google authorization URL, or HTML error page
    """
    request_id = getattr(request.state, "request_id", "unknown")
    log = logger.bind(request_id=request_id)

    # Validate and consume connection token
    user_id = await verify_connection_token(token)
    
    if user_id is None:
        log.warning("oauth_start_invalid_token", token_prefix=token[:8] if token else "none")
        return _html_error(
            title="Link Expired",
            message="This connection link has expired or has already been used. Please return to ChatGPT and request a new link.",
            status_code=400,
        )

    log = log.bind(user_id=user_id)
    log.info("oauth_start_initiated")

    try:
        # Generate PKCE values
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)

        # Generate state token
        state = generate_state_token()

        # Store state in Redis with user_id and code_verifier
        stored = await store_oauth_state(
            state=state,
            user_id=user_id,
            code_verifier=code_verifier,
        )

        if not stored:
            log.error("oauth_start_state_storage_failed")
            return _html_error(
                title="Service Unavailable",
                message="Unable to initiate authorization. Please try again.",
                status_code=503,
            )

        # Generate authorization URL with PKCE
        auth_url = generate_auth_url_with_pkce(
            code_challenge=code_challenge,
            state=state,
        )

        log.info("oauth_start_redirecting_to_google")

        # Redirect to Google
        return RedirectResponse(url=auth_url, status_code=307)

    except Exception as e:
        log.exception("oauth_start_unexpected_error")
        return _html_error(
            title="Error",
            message="An unexpected error occurred. Please try again.",
            status_code=500,
        )
```

---

### 5. Update `backend/main.py`

Add import and router registration:

```python
# Add import at top with other router imports:
from backend.apps.focused.routers.google_connection_router import router as google_connection_router

# Add router registration (near other app.include_router calls):
app.include_router(google_connection_router, prefix="/api/focused/google")
```

---

## MCP Server Changes

### 1. Add `backend_get()` helper to `mcp_server/focused/server.py`

Add this function near the existing `backend_post()`:

```python
async def backend_get(
    path: str,
    user_id: str,
    correlation_id: str
) -> dict:
    """
    Send a GET request to the backend API with user identity headers.

    Args:
        path: API path (e.g., "/api/focused/google/connection-status")
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID for tracing

    Returns:
        Response JSON from backend

    Raises:
        httpx.HTTPStatusError: If backend returns error status
    """
    global http_client
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=30.0)

    url = f"{BACKEND_URL}{path}"

    headers = {
        "X-User-ID": user_id,
        "X-Correlation-ID": correlation_id,
    }

    logger.info(
        "backend.api.call",
        correlation_id=correlation_id,
        url=path,
        user_id=user_id
    )

    resp = await http_client.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()
```

### 2. Add scope mappings to `mcp_server/focused/mcp_auth.py`

If tool-to-scope mapping exists, add:

```python
# Add to TOOL_SCOPES dict (or equivalent):
"connect_google_calendar": ["focused.write"],
"disconnect_google_calendar": ["focused.write"],
```

### 3. Add the two tools to `mcp_server/focused/server.py`

See implementation patterns in "MCP Tools to Implement" section above.

---

## Callback UX

**No changes needed to `/auth/focused/google/callback`.**

The existing HTML success page is sufficient:

```html
<h1>Connected Successfully</h1>
<p>Your Google Calendar has been connected. You can close this window.</p>
```

**User flow:**
1. User clicks connect URL in ChatGPT
2. Browser opens, redirects to Google
3. User approves calendar access
4. Google redirects to callback
5. User sees success page
6. User returns to ChatGPT (manually)
7. User says "check my calendar" or similar
8. `check_calendar` now works

---

## Security Considerations

| Risk | Mitigation |
|------|------------|
| User ID exposure | Opaque token instead of UUID in URL |
| Token replay | Single-use (deleted after first use) |
| Token expiration | 10-minute TTL in Redis |
| Accidental disconnect | Requires `confirm=true` parameter |
| Token logging | Never log full token, only first 8 chars |

---

## File Changes Summary

| File | Change |
|------|--------|
| `backend/core/config.py` | Add `BACKEND_PUBLIC_URL` setting |
| `backend/core/google_oauth.py` | Add `store_connection_token()`, `verify_connection_token()` |
| `backend/apps/focused/routers/google_connection_router.py` | **NEW FILE** |
| `backend/apps/focused/routers/oauth_google_router.py` | Modify `/start` to accept `?token=` |
| `backend/main.py` | Import + include `google_connection_router` |
| `mcp_server/focused/server.py` | Add `backend_get()` + 2 tools |
| `mcp_server/focused/mcp_auth.py` | Add scope mappings for new tools |
| Railway env vars | Add `BACKEND_PUBLIC_URL` |

---

## Acceptance Criteria

1. [ ] `connect_google_calendar` tool registered in MCP server
2. [ ] `disconnect_google_calendar` tool registered in MCP server
3. [ ] `GET /api/focused/google/connection-status` returns correct status
4. [ ] `POST /api/focused/google/initiate-connection` generates opaque token
5. [ ] Token stored in Redis with key `google_connect:{token}` and 10-min TTL
6. [ ] `/auth/focused/google/start` accepts `?token=` parameter (not `?user_id=`)
7. [ ] Token is single-use (deleted after validation)
8. [ ] Expired/invalid token returns user-friendly HTML error
9. [ ] Disconnect requires `confirm=true` parameter
10. [ ] Both tools enforce `focused.write` scope
11. [ ] `BACKEND_PUBLIC_URL` environment variable used for URL construction
12. [ ] No user_id or full token in logs (only token prefix for debugging)

---

## Testing

### Unit Tests
- `store_connection_token()` generates 43-character URL-safe string
- `store_connection_token()` stores in Redis with correct key and TTL
- `verify_connection_token()` returns user_id for valid token
- `verify_connection_token()` returns None for expired/invalid token
- `verify_connection_token()` deletes token after use (single-use)

### Integration Tests
- User with Google connection → `connect_google_calendar` returns "connected"
- User without connection → `connect_google_calendar` returns URL with opaque token
- Valid token in `/start` → redirects to Google
- Expired token in `/start` → shows "Link Expired" HTML error
- Replayed token (second use) → shows "Link Expired" HTML error
- `disconnect_google_calendar` without confirm → returns CONFIRMATION_REQUIRED error
- `disconnect_google_calendar` with confirm=true → calls `/api/focused/disconnect`, returns success
- `disconnect_google_calendar` when not connected → returns "not_connected"

### Manual E2E Test
1. Complete ChatGPT OAuth flow
2. Call `connect_google_calendar` → get URL with opaque token
3. Verify token is NOT a UUID (should be random string)
4. Click URL, complete Google OAuth
5. Call `connect_google_calendar` → returns "connected"
6. Call `check_calendar` → works
7. Call `disconnect_google_calendar` with confirm=true
8. Call `check_calendar` → fails with "Google not connected"
9. Call `connect_google_calendar` again → get new URL
10. Try old URL from step 2 → should show "Link Expired" error

---

## Reference Documents

- "Priority Guardian" & Focused: Shared Backend — Architecture, Data Flow, Storage Strategy
- Increment 10: Offboarding + Disconnect (existing `/disconnect` endpoint)
- Increment 11: Google OAuth PKCE (existing `/start` and `/callback`)
- Increment 7D: MCP Token Validation (authentication patterns)