# Phase 1: OAuth Provider Relocation - Detailed Migration Plan

## Status: READY TO EXECUTE
**Generated**: 2025-11-24
**Estimated**: 30-45 minutes
**Risk**: Medium (many file moves, import updates)

---

## Pre-Migration Checklist

- [x] Investigation complete
- [x] Dependencies analyzed
- [x] Dead code identified
- [x] Brief updated with correct URL strategy
- [ ] All tests passing before migration
- [ ] Git working tree clean

---

## Migration Steps

### Step 1: Create New Directory Structure

```bash
mkdir -p backend/core/oauth_provider
mkdir -p backend/core/oauth_provider/jwt
mkdir -p backend/core/oauth_provider/services
mkdir -p backend/core/oauth_provider/validators
mkdir -p backend/core/routers
```

### Step 2: Move OAuth Provider Module (focused → core)

Move entire `backend/apps/focused/oauth/` to `backend/core/oauth_provider/`:

| From | To |
|------|-----|
| `backend/apps/focused/oauth/__init__.py` | `backend/core/oauth_provider/__init__.py` |
| `backend/apps/focused/oauth/authorize.py` | `backend/core/oauth_provider/authorize.py` |
| `backend/apps/focused/oauth/consent_ui.py` | `backend/core/oauth_provider/consent_ui.py` |
| `backend/apps/focused/oauth/discovery.py` | `backend/core/oauth_provider/discovery.py` |
| `backend/apps/focused/oauth/jwks.py` | `backend/core/oauth_provider/jwks.py` |
| `backend/apps/focused/oauth/register_client.py` | `backend/core/oauth_provider/register_client.py` |
| `backend/apps/focused/oauth/revoke.py` | `backend/core/oauth_provider/revoke.py` |
| `backend/apps/focused/oauth/token_endpoint.py` | `backend/core/oauth_provider/token_endpoint.py` |
| `backend/apps/focused/oauth/jwt/__init__.py` | `backend/core/oauth_provider/jwt/__init__.py` |
| `backend/apps/focused/oauth/jwt/jwt_signer.py` | `backend/core/oauth_provider/jwt/jwt_signer.py` |
| `backend/apps/focused/oauth/services/__init__.py` | `backend/core/oauth_provider/services/__init__.py` |
| `backend/apps/focused/oauth/services/authorization_service.py` | `backend/core/oauth_provider/services/authorization_service.py` |
| `backend/apps/focused/oauth/services/client_service.py` | `backend/core/oauth_provider/services/client_service.py` |
| `backend/apps/focused/oauth/services/consent_service.py` | `backend/core/oauth_provider/services/consent_service.py` |
| `backend/apps/focused/oauth/services/jwks_service.py` | `backend/core/oauth_provider/services/jwks_service.py` |
| `backend/apps/focused/oauth/services/revoke_service.py` | `backend/core/oauth_provider/services/revoke_service.py` |
| `backend/apps/focused/oauth/services/token_service.py` | `backend/core/oauth_provider/services/token_service.py` |
| `backend/apps/focused/oauth/validators/__init__.py` | `backend/core/oauth_provider/validators/__init__.py` |
| `backend/apps/focused/oauth/validators/client_metadata.py` | `backend/core/oauth_provider/validators/client_metadata.py` |
| `backend/apps/focused/oauth/validators/pkce.py` | `backend/core/oauth_provider/validators/pkce.py` |
| `backend/apps/focused/oauth/validators/token_validators.py` | `backend/core/oauth_provider/validators/token_validators.py` |

### Step 3: Move OAuth Provider Router

| From | To |
|------|-----|
| `backend/apps/focused/routers/oauth_provider_router.py` | `backend/core/routers/oauth_provider_router.py` |

### Step 4: Consolidate Core OAuth Files

| From | To | Action |
|------|-----|--------|
| `backend/core/oauth_models.py` | `backend/core/oauth_provider/models.py` | MOVE |
| `backend/core/oauth_exceptions.py` | `backend/core/oauth_provider/exceptions.py` | MOVE |
| `backend/core/jwt_utils.py` | `backend/core/oauth_provider/jwt/utils.py` | MOVE |
| `backend/core/oauth_logic.py` | N/A | DELETE (dead code) |
| `backend/core/oauth_provider.py` | N/A | DELETE (stub) |

### Step 5: Update Internal Imports (within oauth_provider module)

After moving files, update all internal imports within the oauth_provider module:

**Files to Update:**
- All files in `backend/core/oauth_provider/` (endpoints, services, validators)
- `backend/core/routers/oauth_provider_router.py`

**Find/Replace Pattern:**
```python
# OLD:
from backend.apps.focused.oauth.xxx import yyy
from backend.core.oauth_models import zzz
from backend.core.oauth_exceptions import aaa
from backend.core.jwt_utils import bbb

# NEW:
from backend.core.oauth_provider.xxx import yyy
from backend.core.oauth_provider.models import zzz
from backend.core.oauth_provider.exceptions import aaa
from backend.core.oauth_provider.jwt.utils import bbb
```

**Specific Import Updates:**

1. **authorize.py** imports:
   - `from backend.core.models import CoreConnection` → NO CHANGE (correct)
   - `from backend.core.oauth_provider.services.authorization_service import ...`
   - `from backend.core.oauth_provider.validators.pkce import ...`

2. **token_endpoint.py** imports:
   - `from backend.core.oauth_provider.services.token_service import ...`
   - `from backend.core.oauth_provider.validators.token_validators import ...`
   - `from backend.core.oauth_provider.validators.pkce import ...`
   - `from backend.core.oauth_provider.models import OAuthAuthorizationCode, OAuthAccessToken`

3. **token_service.py** imports:
   - `from backend.core.oauth_provider.jwt.utils import create_access_token, create_refresh_token, ...`
   - `from backend.core.oauth_provider.models import OAuthAuthorizationCode, OAuthAccessToken`
   - `from backend.core.encryption import encrypt_token, decrypt_token, hash_refresh_token` → NO CHANGE (correct)

4. **jwt_signer.py** imports:
   - `from backend.core.oauth_provider.jwt.utils import create_access_token`

5. **oauth_provider_router.py** imports:
   ```python
   # OLD:
   from backend.apps.focused.oauth.authorize import router as authorize_router
   from backend.apps.focused.oauth.consent_ui import router as consent_router
   from backend.apps.focused.oauth.discovery import router as discovery_router
   from backend.apps.focused.oauth.jwks import router as jwks_router
   from backend.apps.focused.oauth.register_client import router as register_router
   from backend.apps.focused.oauth.token_endpoint import router as token_router
   from backend.apps.focused.oauth.revoke import router as revoke_router

   # NEW:
   from backend.core.oauth_provider.authorize import router as authorize_router
   from backend.core.oauth_provider.consent_ui import router as consent_router
   from backend.core.oauth_provider.discovery import router as discovery_router
   from backend.core.oauth_provider.jwks import router as jwks_router
   from backend.core.oauth_provider.register_client import router as register_router
   from backend.core.oauth_provider.token_endpoint import router as token_router
   from backend.core.oauth_provider.revoke import router as revoke_router
   ```

### Step 6: Update External Imports (main.py, tests, etc.)

**backend/main.py:**
```python
# OLD:
from backend.apps.focused.routers.oauth_provider_router import router as oauth_provider_router
from backend.core.oauth_exceptions import OAuthError

# NEW:
from backend.core.routers.oauth_provider_router import router as oauth_provider_router
from backend.core.oauth_provider.exceptions import OAuthError
```

**Test files** (find all with grep):
```bash
grep -r "from backend.apps.focused.oauth" tests/
grep -r "from backend.core.oauth_models" tests/
grep -r "from backend.core.oauth_exceptions" tests/
grep -r "from backend.core.jwt_utils" tests/
```

Update each test file's imports to use new paths.

### Step 7: Delete Old Directories

```bash
rm -rf backend/apps/focused/oauth/
```

### Step 8: Delete Dead Code Files

```bash
rm backend/core/oauth_logic.py
rm backend/core/oauth_provider.py
```

### Step 9: Validation

1. **Import Check:**
   ```bash
   python -c "from backend.core.oauth_provider import *"
   python -c "from backend.core.routers.oauth_provider_router import router"
   ```

2. **Run All Tests:**
   ```bash
   poetry run pytest tests/oauth/test_oauth_regression_baseline.py -v
   poetry run pytest tests/focused/ -v
   ```

3. **Start Server:**
   ```bash
   poetry run uvicorn backend.main:app --reload
   ```

4. **Verify Endpoints:**
   ```bash
   curl http://localhost:8000/.well-known/openid-configuration
   curl http://localhost:8000/.well-known/oauth-protected-resource
   curl http://localhost:8000/oauth/focused/jwks
   ```

5. **Verify URLs unchanged:**
   - ✅ `/oauth/focused/authorize`
   - ✅ `/oauth/focused/token`
   - ✅ `/oauth/focused/revoke`
   - ✅ `/oauth/focused/register`
   - ✅ `/.well-known/openid-configuration`
   - ✅ `/.well-known/oauth-protected-resource`

---

## Post-Migration Checklist

- [ ] All endpoints respond correctly
- [ ] All 26 OAuth regression tests passing
- [ ] All focused tests passing
- [ ] No import errors in any module
- [ ] `backend/apps/focused/oauth/` deleted
- [ ] `backend/core/oauth_logic.py` deleted
- [ ] `backend/core/oauth_provider.py` deleted
- [ ] URLs unchanged (ChatGPT SDK compatibility)
- [ ] Git commit created with detailed message

---

## Rollback Plan

If anything breaks:

1. **Git rollback:**
   ```bash
   git reset --hard HEAD
   ```

2. **Or revert commit:**
   ```bash
   git revert <commit-hash>
   ```

---

## Notes

- **URLs MUST NOT CHANGE** - ChatGPT SDK has `/oauth/focused/*` hardcoded
- Only module location changes, not functionality
- Zero functional changes - pure refactoring
- MCP server (`mcp/focused/mcp_auth.py`) does NOT need import updates (uses JWKS URL, not imports)
- Google OAuth (`backend/core/google_oauth.py`) does NOT need updates (separate module)

---

## Success Criteria

✅ `backend/apps/focused/oauth/` no longer exists
✅ `backend/core/oauth_provider/` contains all OAuth provider logic
✅ `backend/core/routers/oauth_provider_router.py` exists
✅ All imports updated and working
✅ All tests passing
✅ Server starts without errors
✅ All endpoints respond correctly
✅ URLs unchanged (`/oauth/focused/*`)
✅ Dead code deleted (`oauth_logic.py`, `oauth_provider.py`)
