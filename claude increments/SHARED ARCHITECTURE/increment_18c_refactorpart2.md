# FINAL BRIEFING — Part 2 Refactor: Move Google OAuth Router to Shared Layer

## Goal

Promote the Google OAuth router from `backend/apps/focused/routers/` into the shared backend layer so all SDK apps can rely on a single, central Google OAuth entrypoint. This is a backend-only refactor. No business logic changes. No MCP changes.

---

## File Movements

**FROM**
```
backend/apps/focused/routers/oauth_google_router.py
```

**TO**
```
backend/core/routers/oauth_google_router.py
```

This aligns with existing conventions such as:
```
backend/core/routers/oauth_provider_router.py
```

---

## Tasks

### 1. Move the Router File

Move:
```
backend/apps/focused/routers/oauth_google_router.py
```
→
```
backend/core/routers/oauth_google_router.py
```

No code changes inside the file yet.

### 2. Update Imports

Every place that currently imports:
```python
from backend.apps.focused.routers.oauth_google_router import router
```

must be updated to:
```python
from backend.core.routers.oauth_google_router import router
```

This is required in `backend/main.py`.

Nothing changes in MCP code.

### 3. Update Include Path in Main App

Before:
```python
app.include_router(oauth_google_router, prefix="/auth/focused/google")
```

After:
```python
app.include_router(oauth_google_router, prefix="/auth/google")
```

This is the only functional change because the goal is to make this router shared.

### 4. Update Backend URL Construction

This happens in backend, NOT MCP.

Before:
```python
f"{settings.BACKEND_PUBLIC_URL}/auth/focused/google/start?token={token}"
```

After:
```python
f"{settings.BACKEND_PUBLIC_URL}/auth/google/start?token={token}"
```

This must be updated in:
- `backend/apps/focused/routers/google_connection_router.py` line 87

MCP tools remain untouched.

### 5. Update GOOGLE_REDIRECT_URI

Google Console redirect URIs must change from:
```
https://api.priority-guard.com/auth/focused/google/callback
```

to:
```
https://api.priority-guard.com/auth/google/callback
```

And update:
- `settings.GOOGLE_REDIRECT_URI`
- environment variables in Railway
- tests referencing redirect URI

### 6. Update Tests

All integration tests referencing the old path must be updated:
- `/auth/focused/google/start`
- `/auth/focused/google/callback`

Change to:
- `/auth/google/start`
- `/auth/google/callback`

Search-and-replace across:
```
tests/integration/google_oauth/
```

### 7. E2E Verification Required

After the move you must verify:

1. MCP → backend → Google redirect still works
2. Opaque token still validated
3. State stored and consumed correctly
4. Callback stores tokens correctly
5. Check_calendar works after connection
6. Reconnect flow still works
7. Disconnect flow still works

This is the riskiest part of the refactor.

---

## Non-Goals (Do NOT do these)

- Do NOT change Google OAuth logic
- Do NOT rewrite business logic
- Do NOT remove existing PKCE/state/token utilities
- Do NOT touch MCP tools
- Do NOT change CoreConnection model
- Do NOT change the connect/disconnect flow

Only move and rewire paths.

---

## Summary

This refactor:

- Centralizes Google OAuth flow
- Makes logic shared across apps
- Eliminates app-specific routing
- Aligns with existing core router structure
- Preserves all logic with minimal risk
- Requires only path + import + config updates

Final location:
```
backend/core/routers/oauth_google_router.py
```