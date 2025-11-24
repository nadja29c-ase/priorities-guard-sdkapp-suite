# Refactoring Brief: OAuth Provider Relocation + Test Cleanup

## Context

Priority Guardian is an SDK app suite with a **shared backend** serving multiple apps (Focused, Meeting Decliner, Task Scheduler). The OAuth 2.1 provider authenticates ChatGPT → Priority Guardian for ALL apps, differentiated only by scopes.

**Current Problem:** OAuth provider implementation incorrectly lives inside `backend/apps/focused/` instead of shared `backend/core/`.

---

## Architectural Principle (from project docs)

> "Shared OAuth provider for ChatGPT (issues tokens to all apps)"
> "Priority Guardian backend serves as OAuth Provider to ChatGPT SDK, enabling user authentication across all apps"

- Single JWKS endpoint, single issuer, single client registration
- Scopes differentiate apps: `focused.read`, `focused.write`, `decliner.read`, etc.
- OAuth provider is SHARED infrastructure, not app-specific

---

## Part 1: OAuth Provider Relocation

### Files to MOVE (focused → core)

| Current Location | New Location |
|-----------------|--------------|
| `backend/apps/focused/oauth/` (entire module) | `backend/core/oauth_provider/` |
| `backend/apps/focused/routers/oauth_provider_router.py` | `backend/core/routers/oauth_provider_router.py` |

### Files to KEEP in focused (correct location)

- `backend/apps/focused/routers/oauth_google_router.py` — outbound OAuth CLIENT to Google
- Everything else in `focused/` is app-specific and correct

### Files to CONSOLIDATE into `backend/core/oauth_provider/`

These loose files at `backend/core/` root must move into the oauth_provider module:

| Current Location | New Location | Status |
|-----------------|--------------|--------|
| `backend/core/oauth_models.py` | `backend/core/oauth_provider/models.py` | ✅ MOVE |
| `backend/core/oauth_exceptions.py` | `backend/core/oauth_provider/exceptions.py` | ✅ MOVE |
| `backend/core/jwt_utils.py` | `backend/core/oauth_provider/jwt/utils.py` | ✅ MOVE (only used by OAuth provider) |
| `backend/core/oauth_logic.py` | N/A | ❌ DELETE (dead code, zero imports, duplicate of validators) |
| `backend/core/oauth_provider.py` | N/A | ❌ DELETE (pure stub from increment 7A) |

**Decision:** All OAuth provider code consolidated into `backend/core/oauth_provider/` module. No loose `oauth_*.py` files at core/ root.

### Import Updates Required

After move, update all imports from:
```python
from backend.apps.focused.oauth.xxx import yyy
```
To:
```python
from backend.core.oauth_provider.xxx import yyy
```

Files likely affected:
- `backend/main.py`
- `backend/apps/focused/routers/__init__.py`
- `mcp/focused/mcp_auth.py`
- All test files referencing OAuth

### Router Registration

In `backend/main.py`, the OAuth provider router should be mounted at app level, not under focused:

```python
# Current (wrong): Under focused app include
# Correct: Import from core and mount at app level
from backend.core.routers.oauth_provider_router import router as oauth_provider_router
app.include_router(oauth_provider_router)  # URLs stay /oauth/focused/* (ChatGPT SDK hardcoded)
```

**CRITICAL**: URL paths MUST stay `/oauth/focused/authorize`, `/oauth/focused/token`, etc.
ChatGPT SDK has these hardcoded. Only the module location changes, NOT the URLs.

---

## Part 2: Test Folder Cleanup

### Current Structure (messy)

```
tests/
├── focused/           # 25+ test files, mixed concerns
├── oauth/             # 3 files including .bak file
├── sdk app 2/         # Empty placeholder
└── __init__.py
```

### Target Structure

```
tests/
├── unit/
│   ├── core/
│   │   ├── test_oauth_provider.py      # OAuth provider unit tests
│   │   ├── test_jwt_utils.py
│   │   ├── test_rate_limit.py
│   │   └── test_middleware.py
│   └── focused/
│       ├── test_sync_conflicts.py
│       ├── test_focus_session_model.py
│       ├── test_calendar_timezone.py
│       └── test_cleanup.py
├── integration/
│   ├── test_oauth_flow.py              # Full OAuth flow tests
│   ├── test_google_calendar.py
│   ├── test_webhook_flow.py
│   └── test_mcp_integration.py
├── conftest.py                          # Shared fixtures
└── __init__.py
```

### Files to DELETE

- `tests/oauth/test_oauth_regression_baseline.py.bak` — backup file
- `tests/focused/*.sh` — shell scripts don't belong in pytest structure
- `tests/sdk app 2/` — empty placeholder with space in name

### Files to CONSOLIDATE

Many test files are increment-specific (`test_increment_7a_*.py`). Consolidate by feature:

| Current Files | Consolidate Into |
|--------------|------------------|
| `test_increment_7a_oauth_skeleton.py`, `test_increment_7b_oauth.py`, `test_7c_simple.py`, `test_7d_auth_simple.py` | `tests/unit/core/test_oauth_provider.py` + `tests/integration/test_oauth_flow.py` |
| `test_increment_6b.py`, `test_increment_6c_cleanup.py`, `test_increment_6d_conflicts.py` | `tests/unit/focused/test_sync_*.py` |
| `test_mcp_auth_7d.py`, `test_mcp_validation.py`, `test_mcp_errors.py` | `tests/integration/test_mcp_integration.py` |

### Conftest Consolidation

- `tests/focused/conftest.py` → merge fixtures into `tests/conftest.py`
- `tests/oauth/conftest.py` → merge fixtures into `tests/conftest.py`

---

## Validation Checklist

After refactoring:

1. [ ] All OAuth endpoints work: `/oauth/authorize`, `/oauth/token`, `/oauth/jwks`, `/oauth/register`, `/oauth/revoke`
2. [ ] Discovery endpoints work: `/.well-known/openid-configuration`, `/.well-known/oauth-protected-resource`
3. [ ] MCP server can validate tokens using backend JWKS
4. [ ] Google OAuth flow still works (unchanged in focused/)
5. [ ] All existing tests pass (after import updates)
6. [ ] No duplicate code between `core/oauth_provider/` and old `core/oauth_*.py` files

---

## Out of Scope

- No functional changes to OAuth logic
- No new features
- No changes to database models or migrations
- MCP server location is correct (stays in `mcp/focused/`)

---

## Success Criteria

1. `backend/apps/focused/oauth/` no longer exists
2. `backend/core/oauth_provider/` contains all OAuth provider logic
3. `backend/core/google_oauth.py` remains for Google client (unchanged)
3. Tests organized by type (unit/integration) and component (core/focused)
4. No `.bak` files or shell scripts in tests/
5. All imports updated and working
6. Zero functionality changes