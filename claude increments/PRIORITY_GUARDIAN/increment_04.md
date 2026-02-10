# Make Google OAuth Scope Configurable Per App

## Problem

`backend/core/google_oauth.py` hardcodes `calendar.readonly` scope in two places. PG needs the narrower `calendar.events.readonly`. Core modules should not hardcode app-specific scopes.

## What must change

Two functions in `backend/core/google_oauth.py` accept scope as a parameter instead of hardcoding it:

### 1. `generate_auth_url_with_pkce(code_challenge, state)` 
Add `scope: str` parameter. Remove hardcoded `"https://www.googleapis.com/auth/calendar.readonly"`.

### 2. `exchange_code(code, http_client, code_verifier, correlation_id)`
Add `required_scope: str` parameter. Replace the hardcoded `required_scope` variable with the parameter.

## Callers to update

The caller that passes scope is in the **service layer**, not the router:

- `backend/core/oauth/google_oauth_service.py` → `initiate_oauth_flow()` calls `generate_auth_url_with_pkce()`
- `backend/core/oauth/google_oauth_service.py` → `complete_oauth_flow()` calls `exchange_code()`

The service is also shared core. The scope must come from the **app layer** — meaning whoever calls the service must pass the scope down.

Trace the call chain from PG's `google_connection_router.py` and the shared `oauth_google_router.py` (callback) to understand how scope flows through. The goal: app-specific config determines scope, core functions just receive it.

## PG scope value

`https://www.googleapis.com/auth/calendar.events.readonly`

## Where to define the PG scope

`backend/apps/priority_guardian/pg_config.py` — add `GOOGLE_CALENDAR_SCOPE` constant. This keeps app-specific config in the app layer.

## Constraints

- Do not break Focused's code paths. If Focused calls these functions too, make sure it still works (pass its scope, or default to the old value if needed since Focused is frozen).
- No behavior change other than scope parameterization.
- Core modules must not import from app modules.

## Unit tests

- Test: `generate_auth_url_with_pkce` includes the passed scope in the URL
- Test: `exchange_code` validates the passed scope, not a hardcoded one
- Test: passing wrong scope to `exchange_code` raises ValueError

## Integration tests

None needed. This is a pure parameter threading change.