# Clarity Increment 04: OAuth Integration

## Goal

Wire Clarity MCP to shared OAuth provider. Every tool call tied to authenticated `user_id`.

## Architecture

- **Single OAuth provider** serving both `/oauth/focused/*` (legacy) and `/oauth/pg/*` (new alias)
- **Clarity uses `/oauth/pg/*`** (pg = Priority Guardian)
- **Add `clarity.write` scope** to existing provider
- **Clarity MCP** validates same JWTs, checks `clarity.write` scope
- `/oauth/focused` remains for Focused app; remove after `/oauth/pg` proven stable
- **Note:** Both `/oauth/focused/.well-known/*` and `/oauth/pg/.well-known/*` return canonical `/oauth/pg/*` endpoints. Legacy discovery still works but directs clients to the new path.

## Scope

### In Scope
- Add `/oauth/pg/*` alias routes (same handlers as `/oauth/focused/*`)
- Add `clarity.write` scope to discovery endpoints
- Create Clarity MCP auth module (adapt from Focused)
- Create Clarity MCP config with `CLARITY_*` env vars
- Create Clarity MCP discovery endpoint
- Wire auth into `cluster_raw_thoughts` tool
- Extract `user_id` from JWT

### Out of Scope
- DB persistence (next increment)
- Removing `/oauth/focused` routes (future cleanup)
- `clarity.read` scope (YAGNI)
- Widget changes

---

## Backend Changes

### 1. Add `/oauth/pg/*` Alias Routes

**File:** `backend/core/routers/oauth_provider_router.py`

Add alias routes that point to same handlers:

```python
"""
OAuth Provider Router — Thin orchestrator for OAuth 2.1 provider endpoints.

Serves two route prefixes:
- /oauth/focused/* (legacy, used by Focused app)
- /oauth/pg/* (new, used by Clarity and future apps)

Both use identical handlers, keys, and issuer semantics.
"""

from fastapi import APIRouter

# Import extracted OAuth modules
from backend.core.oauth_provider.authorize import router as authorize_router
from backend.core.oauth_provider.consent_ui import router as consent_router
from backend.core.oauth_provider.discovery import router as discovery_router
from backend.core.oauth_provider.jwks import router as jwks_router
from backend.core.oauth_provider.register_client import router as register_router
from backend.core.oauth_provider.token_endpoint import router as token_router
from backend.core.oauth_provider.revoke import router as revoke_router

router = APIRouter(tags=["oauth-provider"])

# /oauth/focused/* routes (legacy - Focused app)
router.include_router(authorize_router, prefix="/oauth/focused")
router.include_router(consent_router, prefix="/oauth/focused")
router.include_router(discovery_router, prefix="/oauth/focused")
router.include_router(jwks_router, prefix="/oauth/focused")
router.include_router(register_router, prefix="/oauth/focused")
router.include_router(token_router, prefix="/oauth/focused")
router.include_router(revoke_router, prefix="/oauth/focused")

# /oauth/pg/* routes (new alias - Clarity and future apps)
router.include_router(authorize_router, prefix="/oauth/pg")
router.include_router(consent_router, prefix="/oauth/pg")
router.include_router(discovery_router, prefix="/oauth/pg")
router.include_router(jwks_router, prefix="/oauth/pg")
router.include_router(register_router, prefix="/oauth/pg")
router.include_router(token_router, prefix="/oauth/pg")
router.include_router(revoke_router, prefix="/oauth/pg")
```

### 2. Add `clarity.write` Scope to Discovery

**File:** `backend/core/oauth_provider/discovery.py`

```python
"""
Discovery Endpoints - OAuth 2.1 and OpenID Connect discovery.

Provides metadata endpoints for OAuth client discovery:
- OpenID Connect Discovery (/.well-known/openid-configuration)

NOTE: oauth-protected-resource is NOT served here. Each MCP server
publishes its own /.well-known/oauth-protected-resource with the
correct resource URL for that specific MCP server.

Supports scopes for all Priority Guardian apps:
- focused.* (Focused app)
- clarity.* (Clarity app)
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.core.config import settings

router = APIRouter(tags=["oauth-provider"])


@router.get("/.well-known/openid-configuration")
async def openid_configuration():
    """
    OpenID Connect Discovery endpoint.

    Returns OAuth provider configuration for ChatGPT discovery.
    """
    return JSONResponse({
        "issuer": settings.OAUTH_ISSUER,
        "authorization_endpoint": f"{settings.OAUTH_ISSUER}/oauth/pg/authorize",
        "token_endpoint": f"{settings.OAUTH_ISSUER}/oauth/pg/token",
        "jwks_uri": f"{settings.OAUTH_ISSUER}/oauth/pg/jwks",
        "registration_endpoint": f"{settings.OAUTH_ISSUER}/oauth/pg/register",
        "scopes_supported": [
            "focused.read", 
            "focused.write", 
            "focused.notify",
            "clarity.write"
        ],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"]
    })


# NOTE: oauth-protected-resource is NOT served from the backend OAuth provider.
# Each MCP server publishes its own /.well-known/oauth-protected-resource
# with the correct resource URL for that specific MCP server.
# See: mcp_server/clarity/discovery.py, mcp_server/focused/discovery.py
```

---

## MCP Clarity Changes

### 3. Create Clarity Config

**New file:** `mcp_server/clarity/config.py`

```python
"""
Configuration for Clarity MCP Server.

Centralizes all MCP-specific settings including JWT validation,
JWKS fetching, and OAuth client configuration.

Uses /oauth/pg/* endpoints (shared Priority Guardian OAuth provider).
"""

import os
from typing import Optional


# ============================================================================
# Environment Detection
# ============================================================================

ENV = os.getenv("ENV", "dev")


# ============================================================================
# Helper Functions
# ============================================================================

def get_env(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """Get environment variable with optional default and requirement check."""
    value = os.getenv(key, default)

    if required and value is None:
        if ENV in ("production", "staging"):
            raise RuntimeError(
                f"Required environment variable {key} not set. "
                f"This is required in {ENV} environment."
            )

    return value


# ============================================================================
# JWT Validation Settings
# ============================================================================

# JWKS URL - uses /oauth/pg/ (Priority Guardian shared OAuth)
CLARITY_JWKS_URL = get_env(
    "CLARITY_JWKS_URL",
    default="http://localhost:8000/oauth/pg/jwks"
)

# Expected JWT issuer (iss claim)
# NOTE: Uses domain-only issuer to match existing Focused pattern.
# Path-qualified issuer (e.g., .../oauth/pg) is a future hardening task.
CLARITY_ISSUER = get_env(
    "CLARITY_ISSUER",
    default="https://www.priority-guard.com"
)

# Expected JWT audience (aud claim)
CLARITY_AUDIENCE = get_env(
    "CLARITY_AUDIENCE",
    default="https://www.priority-guard.com"
)

# Expected ChatGPT client ID for azp claim validation
CHATGPT_CLIENT_ID_CLARITY = get_env(
    "CHATGPT_CLIENT_ID_CLARITY",
    required=True
)

# Token expiry grace period (seconds)
TOKEN_EXPIRY_GRACE_SECONDS = int(get_env(
    "TOKEN_EXPIRY_GRACE_SECONDS",
    default="30"
))

# JWKS cache settings
JWKS_CACHE_TTL_SECONDS = int(get_env(
    "JWKS_CACHE_TTL_SECONDS",
    default=str(24 * 3600)
))

JWKS_MAX_STALE_SECONDS = int(get_env(
    "JWKS_MAX_STALE_SECONDS",
    default=str(7 * 24 * 3600)
))

JWKS_FETCH_TIMEOUT_SECONDS = int(get_env(
    "JWKS_FETCH_TIMEOUT_SECONDS",
    default="5"
))


# ============================================================================
# Backend Configuration
# ============================================================================

BACKEND_URL = get_env(
    "CLARITY_BACKEND_URL",
    default="http://localhost:8000"
).rstrip("/")


# ============================================================================
# OAuth Discovery Configuration
# ============================================================================

# Clarity MCP Server public URL
MCP_SERVER_URL = get_env(
    "CLARITY_MCP_SERVER_URL",
    default="http://localhost:8002"
).rstrip("/")

# OAuth Authorization Server URL (uses /oauth/pg/)
OAUTH_ISSUER_URL = get_env(
    "CLARITY_OAUTH_ISSUER_URL",
    default="http://localhost:8000/oauth/pg"
)

# Supported OAuth scopes
SCOPES_SUPPORTED = ["clarity.write"]


# ============================================================================
# Scope Definitions
# ============================================================================

TOOL_SCOPES = {
    "cluster_raw_thoughts": ["clarity.write"],
}


# ============================================================================
# Logging Configuration
# ============================================================================

LOG_LEVEL = get_env("LOG_LEVEL", default="INFO")
```

### 4. Create Clarity Auth Module

**New file:** `mcp_server/clarity/mcp_auth.py`

Copy entire contents of `mcp_server/focused/mcp_auth.py`, then:

1. Change import to use clarity config (proper rename, no aliasing):

```python
from mcp_server.clarity.config import (
    CLARITY_JWKS_URL,
    CLARITY_ISSUER,
    CLARITY_AUDIENCE,
    CHATGPT_CLIENT_ID_CLARITY,
    TOKEN_EXPIRY_GRACE_SECONDS,
    JWKS_CACHE_TTL_SECONDS,
    JWKS_MAX_STALE_SECONDS,
    JWKS_FETCH_TIMEOUT_SECONDS,
    TOOL_SCOPES,
    MCP_SERVER_URL,
)
```

2. Rename all variable usages in the file:
   - `FOCUSED_JWKS_URL` → `CLARITY_JWKS_URL`
   - `FOCUSED_ISSUER` → `CLARITY_ISSUER`
   - `FOCUSED_AUDIENCE` → `CLARITY_AUDIENCE`
   - `CHATGPT_CLIENT_ID_FOCUSED` → `CHATGPT_CLIENT_ID_CLARITY`

3. Add this comment at top of file:

```python
"""
JWT Authentication and Authorization for Clarity MCP Server.

NOTE: This module is intentionally duplicated from mcp_server/focused/mcp_auth.py.
Future refactoring should extract shared auth logic to mcp_server/common/oauth_auth.py.
Duplication is acceptable for now to maintain app isolation during development.
"""
```

### 5. Create Clarity Discovery Module

**New file:** `mcp_server/clarity/discovery.py`

MCP server is a **resource server**, not an authorization server. Only `oauth-protected-resource` belongs here. ChatGPT discovers OpenID metadata from `/oauth/pg`, not from MCP.

```python
"""
OAuth Discovery Endpoint for Clarity MCP Server.

Only provides oauth-protected-resource metadata.
OpenID/authorization server discovery belongs to the backend OAuth provider,
not the MCP resource server.
"""

from fastapi import APIRouter
from mcp_server.clarity.config import (
    MCP_SERVER_URL,
    OAUTH_ISSUER_URL,
    SCOPES_SUPPORTED,
)

router = APIRouter()


@router.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource():
    """OAuth 2.0 Protected Resource Metadata (RFC 9728)."""
    return {
        "resource": MCP_SERVER_URL,
        "authorization_servers": [OAUTH_ISSUER_URL],
        "scopes_supported": SCOPES_SUPPORTED,
    }
```

### 6. Update Clarity Server

**File:** `mcp_server/clarity/server.py`

Add these changes:

#### 6a. Add imports at top:

```python
import json
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from mcp_server.clarity.config import (
    MCP_SERVER_URL,
    OAUTH_ISSUER_URL,
)
from mcp_server.clarity.mcp_auth import (
    authenticate_request,
    UnauthorizedError,
    InsufficientScopeError,
    build_unauthorized_error,
    build_forbidden_error,
)
from mcp_server.clarity.discovery import oauth_protected_resource
```

#### 6b. Add middleware class (copy from focused):

```python
class MCPContentTypeAndAcceptFixMiddleware:
    """
    Fix ChatGPT → FastMCP header mismatch:
    - ChatGPT sends Content-Type: application/octet-stream
    - ChatGPT sends Accept: */*
    FastMCP requires:
    - Content-Type: application/json
    - Accept: text/event-stream (for SSE handshake)
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            if scope.get("path") == "/mcp":

                new_headers = []
                modified = False

                for name, value in scope["headers"]:
                    if name == b"content-type" and b"application/octet-stream" in value:
                        value = b"application/json"
                        modified = True

                    if name == b"accept":
                        value = b"text/event-stream, application/json"
                        modified = True

                    new_headers.append((name, value))

                if modified:
                    scope = dict(scope)
                    scope["headers"] = new_headers

        await self.app(scope, receive, send)
```

#### 6c. Add discovery route wrapper:

```python
async def wellknown_oauth_protected_resource(request):
    """Starlette wrapper for discovery.oauth_protected_resource."""
    logger.info("oauth.discovery.request")
    return JSONResponse(await oauth_protected_resource())
```

#### 6d. Update `create_app()`:

```python
def create_app():
    """
    Create the ASGI application.

    FastMCP is the root app with:
    - CORS middleware for widget compatibility
    - Discovery routes for OAuth
    - Header fix middleware for ChatGPT
    """
    fastmcp_app = mcp.streamable_http_app()

    # Add CORS
    try:
        from starlette.middleware.cors import CORSMiddleware
        fastmcp_app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=False,
        )
    except Exception:
        pass

    # Discovery routes - only oauth-protected-resource (MCP is resource server, not auth server)
    # ChatGPT checks both root and /mcp suffixed versions
    discovery_routes = [
        Route("/oauth-protected-resource", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
        Route("/oauth-protected-resource/mcp", wellknown_oauth_protected_resource, methods=["GET", "HEAD", "OPTIONS"]),
    ]
    discovery_app = Starlette(routes=discovery_routes)

    # Mount discovery routes
    fastmcp_app.mount("/.well-known", discovery_app)

    # Wrap with header-fix middleware
    return MCPContentTypeAndAcceptFixMiddleware(fastmcp_app)
```

#### 6e. Update tool handler to authenticate:

In `_call_tool_request()`, add auth before validation:

```python
async def _call_tool_request(req: mcp_types.CallToolRequest) -> mcp_types.CallToolResult:
    """Handle tool calls with authentication."""
    name = req.params.name
    arguments = req.params.arguments or {}
    meta = getattr(req.params, '_meta', None) or {}

    logger.info("clarity.tool.call_received",
                tool_name=name,
                argument_keys=list(arguments.keys()),
                widget_version=WIDGET_VERSION)

    if name == "cluster_raw_thoughts":
        # ============================================================
        # AUTHENTICATION (new)
        # ============================================================
        try:
            auth_context = await authenticate_request(name, meta)
            user_id = auth_context["user_id"]
            correlation_id = auth_context["correlation_id"]
            
            logger.info("clarity.tool.authenticated",
                        user_id=user_id,
                        correlation_id=correlation_id,
                        tool_name=name)
                        
        except UnauthorizedError:
            logger.warning("clarity.tool.unauthorized", tool_name=name)
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text=json.dumps(build_unauthorized_error())
                )],
                isError=True,
            )
        except InsufficientScopeError:
            logger.warning("clarity.tool.forbidden", tool_name=name)
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text=json.dumps(build_forbidden_error())
                )],
                isError=True,
            )

        # ============================================================
        # EXISTING VALIDATION + TOOL LOGIC (unchanged)
        # ============================================================
        validated_request = None
        # ... rest of existing code ...
```

---

## Environment Variables

### Production (Railway)

**Clarity MCP service:**
```
ENV=production
CLARITY_JWKS_URL=https://priorities-guard-fastapi-backend-production.up.railway.app/oauth/pg/jwks
CLARITY_ISSUER=https://www.priority-guard.com
CLARITY_AUDIENCE=https://www.priority-guard.com
CLARITY_MCP_SERVER_URL=https://<clarity-mcp-production-url>
CLARITY_OAUTH_ISSUER_URL=https://priorities-guard-fastapi-backend-production.up.railway.app/oauth/pg
CLARITY_BACKEND_URL=https://priorities-guard-fastapi-backend-production.up.railway.app
CHATGPT_CLIENT_ID_CLARITY=<from ChatGPT connector registration>
```

### Local Development
```
ENV=dev
CLARITY_JWKS_URL=http://localhost:8000/oauth/pg/jwks
CLARITY_ISSUER=https://www.priority-guard.com
CLARITY_AUDIENCE=https://www.priority-guard.com
CLARITY_MCP_SERVER_URL=http://localhost:8002
CLARITY_OAUTH_ISSUER_URL=http://localhost:8000/oauth/pg
CLARITY_BACKEND_URL=http://localhost:8000
CHATGPT_CLIENT_ID_CLARITY=test-client-id
```

---

## ChatGPT Connector Registration

Register a new ChatGPT connector for Clarity MCP (separate from Focused):
1. Go to ChatGPT developer console
2. Create new MCP connector for Clarity
3. Set MCP server URL to Clarity's production URL
4. Complete OAuth registration
5. Save the client_id as `CHATGPT_CLIENT_ID_CLARITY`

---

## Unit Tests

**File:** `tests/unit/mcp/test_clarity_auth.py`

```python
"""
Clarity MCP authentication unit tests.

Tests JWT validation and scope enforcement for Clarity tools.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import jwt
import time

from mcp_server.clarity.mcp_auth import (
    authenticate_request,
    validate_jwt,
    extract_bearer_token,
    check_scopes,
    UnauthorizedError,
    InsufficientScopeError,
)


class TestExtractBearerToken:
    """Test Bearer token extraction from Authorization header."""

    def test_valid_bearer_token(self):
        """Valid Bearer token extracted correctly."""
        token = extract_bearer_token("Bearer abc123")
        assert token == "abc123"

    def test_missing_header(self):
        """Missing header returns None."""
        assert extract_bearer_token(None) is None

    def test_empty_header(self):
        """Empty header returns None."""
        assert extract_bearer_token("") is None

    def test_wrong_scheme(self):
        """Non-Bearer scheme returns None."""
        assert extract_bearer_token("Basic abc123") is None

    def test_malformed_header(self):
        """Malformed header returns None."""
        assert extract_bearer_token("Bearer") is None
        assert extract_bearer_token("Bearertoken") is None


class TestCheckScopes:
    """Test scope validation."""

    def test_has_required_scope(self):
        """Token with required scope passes."""
        assert check_scopes({"clarity.write", "other"}, ["clarity.write"]) is True

    def test_missing_required_scope(self):
        """Token without required scope fails."""
        assert check_scopes({"focused.write"}, ["clarity.write"]) is False

    def test_empty_required_scopes(self):
        """Empty required scopes always passes."""
        assert check_scopes(set(), []) is True

    def test_multiple_required_scopes(self):
        """All required scopes must be present."""
        assert check_scopes({"a", "b", "c"}, ["a", "b"]) is True
        assert check_scopes({"a", "c"}, ["a", "b"]) is False


class TestAuthenticateRequest:
    """Test full authentication flow."""

    @pytest.mark.asyncio
    async def test_missing_authorization_header(self):
        """Missing Authorization header raises UnauthorizedError."""
        meta = {"headers": {}}
        
        with pytest.raises(UnauthorizedError):
            await authenticate_request("cluster_raw_thoughts", meta)

    @pytest.mark.asyncio
    async def test_invalid_token_format(self):
        """Invalid token format raises UnauthorizedError."""
        meta = {"headers": {"authorization": "InvalidFormat"}}
        
        with pytest.raises(UnauthorizedError):
            await authenticate_request("cluster_raw_thoughts", meta)

    @pytest.mark.asyncio
    async def test_wrong_scope_raises_insufficient(self):
        """Valid token with wrong scope raises InsufficientScopeError."""
        meta = {"headers": {"authorization": "Bearer validtoken"}}
        
        # Mock validate_jwt to return focused.write instead of clarity.write
        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"focused.write"},  # Wrong scope
                "jti": "token-id",
                "azp": "client-id"
            }
            
            with pytest.raises(InsufficientScopeError):
                await authenticate_request("cluster_raw_thoughts", meta)

    @pytest.mark.asyncio
    async def test_valid_token_returns_context(self):
        """Valid token with correct scope returns auth context."""
        meta = {"headers": {"authorization": "Bearer validtoken"}}
        
        with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
            mock_validate.return_value = {
                "user_id": "user-123",
                "scopes": {"clarity.write"},
                "jti": "token-id",
                "azp": "client-id"
            }
            
            result = await authenticate_request("cluster_raw_thoughts", meta)
            
            assert result["user_id"] == "user-123"
            assert "correlation_id" in result
            assert "clarity.write" in result["scopes"]
```

---

## Integration Tests

**File:** `tests/integration/test_clarity_oauth.py`

```python
"""
Clarity OAuth integration tests.

Tests end-to-end OAuth flow including discovery endpoints.
"""

import pytest
from httpx import AsyncClient


class TestClarityDiscoveryEndpoints:
    """Test OAuth discovery endpoints on Clarity MCP server."""

    @pytest.mark.asyncio
    async def test_oauth_protected_resource(self, clarity_client: AsyncClient):
        """GET /.well-known/oauth-protected-resource returns clarity scopes."""
        response = await clarity_client.get("/.well-known/oauth-protected-resource")
        
        assert response.status_code == 200
        data = response.json()
        assert "clarity.write" in data["scopes_supported"]
        assert "authorization_servers" in data

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_mcp_suffix(self, clarity_client: AsyncClient):
        """GET /.well-known/oauth-protected-resource/mcp also works."""
        response = await clarity_client.get("/.well-known/oauth-protected-resource/mcp")
        
        assert response.status_code == 200
        data = response.json()
        assert "clarity.write" in data["scopes_supported"]


class TestClarityToolAuth:
    """Test tool authentication."""

    @pytest.mark.asyncio
    async def test_tool_without_auth_returns_32001(self, clarity_client: AsyncClient):
        """Tool call without JWT returns -32001 error."""
        # Call tool without Authorization header
        response = await clarity_client.post("/mcp", json={
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "cluster_raw_thoughts",
                "arguments": {
                    "thoughts_exhausted": True,
                    "clusters": [{"cluster_name": "Test", "thought_items": ["item"]}]
                }
            },
            "id": 1
        })
        
        # Should return unauthorized error
        data = response.json()
        assert data.get("error", {}).get("code") == -32001

    @pytest.mark.asyncio
    async def test_tool_with_wrong_scope_returns_32003(self, clarity_client: AsyncClient, focused_only_token: str):
        """Tool call with focused.write (not clarity.write) returns -32003."""
        response = await clarity_client.post("/mcp", 
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "cluster_raw_thoughts",
                    "arguments": {
                        "thoughts_exhausted": True,
                        "clusters": [{"cluster_name": "Test", "thought_items": ["item"]}]
                    }
                },
                "id": 1
            },
            headers={"Authorization": f"Bearer {focused_only_token}"}
        )
        
        data = response.json()
        assert data.get("error", {}).get("code") == -32003
```

---

## Backend Integration Test

**File:** `tests/integration/test_oauth_pg_alias.py`

```python
"""
Test /oauth/pg/* alias routes work identically to /oauth/focused/*
"""

import pytest
from httpx import AsyncClient


class TestOAuthPgAlias:
    """Verify /oauth/pg/* routes work."""

    @pytest.mark.asyncio
    async def test_pg_jwks_endpoint(self, backend_client: AsyncClient):
        """GET /oauth/pg/jwks returns valid JWKS."""
        response = await backend_client.get("/oauth/pg/jwks")
        
        assert response.status_code == 200
        data = response.json()
        assert "keys" in data
        assert len(data["keys"]) > 0

    @pytest.mark.asyncio
    async def test_pg_openid_configuration(self, backend_client: AsyncClient):
        """GET /oauth/pg/.well-known/openid-configuration works."""
        response = await backend_client.get("/oauth/pg/.well-known/openid-configuration")
        
        assert response.status_code == 200
        data = response.json()
        assert "clarity.write" in data["scopes_supported"]

    @pytest.mark.asyncio
    async def test_pg_and_focused_return_same_jwks(self, backend_client: AsyncClient):
        """Both /oauth/pg/jwks and /oauth/focused/jwks return identical keys."""
        pg_response = await backend_client.get("/oauth/pg/jwks")
        focused_response = await backend_client.get("/oauth/focused/jwks")
        
        assert pg_response.json() == focused_response.json()
```

---

## Success Criteria

- [ ] `/oauth/pg/*` alias routes registered in backend
- [ ] `/oauth/pg/jwks` returns same keys as `/oauth/focused/jwks`
- [ ] `clarity.write` added to backend openid-configuration
- [ ] Backend does NOT serve oauth-protected-resource (MCP servers own that)
- [ ] `mcp_server/clarity/config.py` created with `CLARITY_*` env vars
- [ ] `mcp_server/clarity/mcp_auth.py` created (copied from focused, vars renamed)
- [ ] `mcp_server/clarity/discovery.py` created (oauth-protected-resource only)
- [ ] Clarity server mounts `/.well-known/oauth-protected-resource` with `/mcp` suffix
- [ ] `cluster_raw_thoughts` requires authentication
- [ ] Valid JWT with `clarity.write` → tool executes, `user_id` extracted
- [ ] Missing/invalid JWT → returns `-32001` with `mcp/www_authenticate`
- [ ] Wrong scope (e.g., `focused.write`) → returns `-32003`
- [ ] ChatGPT connector registered for Clarity
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Environment variables set in Railway

---

## Files Changed Summary

| File | Change |
|------|--------|
| `backend/core/routers/oauth_provider_router.py` | Add `/oauth/pg/*` alias routes |
| `backend/core/oauth_provider/discovery.py` | Add `clarity.write` scope, remove oauth-protected-resource |
| `mcp_server/clarity/config.py` | **NEW** - Clarity config |
| `mcp_server/clarity/mcp_auth.py` | **NEW** - Auth module (copied from focused, renamed vars) |
| `mcp_server/clarity/discovery.py` | **NEW** - oauth-protected-resource only |
| `mcp_server/clarity/server.py` | Add auth, discovery route, middleware |
| `tests/unit/mcp/test_clarity_auth.py` | **NEW** - Auth unit tests |
| `tests/integration/test_clarity_oauth.py` | **NEW** - OAuth integration tests |
| `tests/integration/test_oauth_pg_alias.py` | **NEW** - Alias route tests |

---

## Future Cleanup (Out of Scope)

After `/oauth/pg` is proven stable in production:
1. Migrate Focused to use `/oauth/pg/*`
2. Remove `/oauth/focused/*` routes
3. Update all `FOCUSED_*` env vars to generic names
4. Extract shared auth logic to `mcp_server/common/oauth_auth.py`
5. Tighten CORS from `allow_origins=["*"]` to ChatGPT domains + own domain
6. Consider path-qualified issuer (`https://www.priority-guard.com/oauth/pg`) for stricter JWT validation
