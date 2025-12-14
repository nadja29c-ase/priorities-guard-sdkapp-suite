# FINAL BRIEFING — Google OAuth Router Refactor (Minimal Rewrite, Correct Architecture)

## Goal

Refactor `oauth_google_router.py` into a clean layered structure that separates:

- HTTP routing
- OAuth orchestration logic
- database persistence
- HTML rendering
- exception handling

This must be done with minimal changes to existing logic, only restructuring.

---

## File Structure (Final)

```
backend/core/
├── html/
│   └── oauth_pages.py                 # HTMLResponse helpers (error/success)
├── oauth/
│   ├── exceptions.py                  # OAuth exception hierarchy
│   └── google_oauth_service.py        # Orchestration (start + callback logic)
└── repositories/
    └── google_connection_repo.py      # DB persistence for core_connections
```

---

## Layer Responsibilities (Final + Correct)

### 1. Router (Controller) — `oauth_google_router.py`

- Accepts query parameters (`token`, `code`, `state`, etc.)
- Validates required inputs are present
- Extracts `http_client` and `correlation_id`
- Calls service functions
- Catches service exceptions
- Returns HTML responses from `oauth_pages.py`

Router never touches Redis, PKCE, or database logic directly.

### 2. Service Layer — `google_oauth_service.py`

Contains all business logic for:

- verifying opaque token
- PKCE generation using existing utility functions
- storing OAuth state
- validating callback state
- exchanging authorization code
- calling repository to persist tokens

**Important:**

- Service returns data (e.g., redirect URL) or returns `None` on success.
- All failures are signaled by raising exceptions from `exceptions.py`.
- Service does NOT return `HTMLResponse` objects.
- Router handles presentation, Service handles logic.

### 3. Repository — `google_connection_repo.py`

Implements DB operations only:

- `upsert_google_connection(user_id, token_data, session)`
- `get_connection(user_id, session)` if needed in future

This layer contains no business logic and no FastAPI imports.

### 4. Templates / HTML — `oauth_pages.py`

Contains:

- `render_error(title, message, status_code)`
- `render_success()`

Both return `HTMLResponse`.

HTML escaping happens here.

No business logic.

### 5. Utilities — existing `backend/core/google_oauth.py`

Already provide:

- `generate_code_verifier()`
- `generate_code_challenge()`
- `generate_state_token()`
- `store_oauth_state()`
- `verify_and_get_oauth_state()`
- `verify_connection_token()`
- `exchange_code()`

The service must call these, not reimplement them.

---

## Exception Hierarchy (Final) — `exceptions.py`

```python
class GoogleOAuthError(Exception):
    """Base class for all Google OAuth errors."""

class ConnectionTokenExpiredError(GoogleOAuthError):
    """Opaque token invalid or expired."""

class StateInvalidError(GoogleOAuthError):
    """OAuth state missing, invalid, or expired."""

class TokenExchangeError(GoogleOAuthError):
    """Google rejected the authorization code or scope missing."""
```

Service raises these; router catches and renders HTML.

---

## Service API (Final, Correct)

### `initiate_oauth_flow()`

```python
async def initiate_oauth_flow(
    token: str,
    correlation_id: str
) -> str:
    """
    Validates and consumes opaque token.
    Creates PKCE + state.
    Stores state in Redis.
    Returns Google OAuth redirect URL.

    Raises:
        ConnectionTokenExpiredError
        GoogleOAuthError
    """
```

Returns only the Google redirect URL.
Router wraps it in `RedirectResponse`.

### `complete_oauth_flow()`

```python
async def complete_oauth_flow(
    code: str,
    state: str,
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    correlation_id: str
) -> None:
    """
    Validates state.
    Exchanges code via Google.
    Persists tokens using repository.
    Returns None on success.

    Raises:
        StateInvalidError
        TokenExchangeError
        GoogleOAuthError
    """
```

Success is implicit — if it returns without raising, it worked.

Router then returns success HTML.

---

## Router Shape (Final)

### `/auth/google/start`

```python
@router.get("/start")
async def start_google_oauth(request: Request, token: str = Query(...)):
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    try:
        redirect_url = await initiate_oauth_flow(token, correlation_id)
        return RedirectResponse(url=redirect_url, status_code=307)
    except ConnectionTokenExpiredError:
        return render_error("Link Expired", "This link has expired. Please request a new one.")
    except GoogleOAuthError:
        return render_error("Error", "Unable to initiate authorization. Please try again.", 500)
```

### `/auth/google/callback`

```python
@router.get("/callback")
async def google_oauth_callback(
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
    session: AsyncSession = Depends(get_db),
):
    correlation_id = getattr(request.state, "correlation_id", "unknown")
    http_client = request.app.state.http_client

    # Handle Google-side errors
    if error:
        if error == "access_denied":
            return render_error("Access Denied", "You denied access to your Google Calendar.")
        return render_error("Authorization Failed", error_description or "Google authorization failed.")

    # Validate required inputs (router responsibility)
    if not code or not state:
        return render_error("Invalid Request", "Missing required parameters.", 400)

    try:
        await complete_oauth_flow(code, state, session, http_client, correlation_id)
        return render_success()
    except StateInvalidError:
        return render_error("Session Expired", "Your authorization session expired. Please try again.")
    except TokenExchangeError:
        return render_error("Authorization Failed", "Google authorization failed. Please try again.")
    except GoogleOAuthError:
        return render_error("Error", "Unexpected error. Please try again.", 500)
```

---

## Repository Responsibilities (Final)

### `google_connection_repo.py`

```python
async def upsert_google_connection(user_id, token_data, session):
    # encrypt + upsert CoreConnection
    # set connection_type="google"
    # clear revoked_at on reconnect
```

Service passes the raw token data to repo.
Repo encrypts and persists.
Router does nothing with DB.

---

## Key Rules (Final + Required)

1. Router never touches repository or utilities.
2. Service never returns HTTP responses.
3. Service raises typed exceptions.
4. Router renders user-facing HTML.
5. Router validates input presence before calling service.
6. No business logic inside HTML renderer.
7. No duplication of PKCE/state/token logic.
8. Only the repository touches the DB.
9. `complete_oauth_flow` returns `None` on success (implicit success).

---

## Summary (Minimal Rewrites Only)

The refactor:

- reorganizes code without changing behavior
- moves logic into correct layers
- introduces stable service API
- introduces typed exceptions
- keeps routers tiny and declarative
- prepares the codebase for multi-app shared Google OAuth
- avoids dangerous coupling between layers
- dramatically reduces future risk

This is the final, complete, correct briefing.