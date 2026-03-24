"""
MindSort AI OAuth Discovery Endpoints.

Per-app authorization server discovery for MindSort AI.
Mounted at /oauth/mindsort by oauth_provider_router.

Issuer: shared root domain (https://www.priority-guard.com) — same JWT signer.
Endpoints: /oauth/mindsort/* — app-specific.
Scopes: clarity.write only.

ChatGPT flow:
  mindsort.priority-guard.com/.well-known/oauth-protected-resource
  → authorization_servers: ["https://www.priority-guard.com/oauth/mindsort"]
  → www.priority-guard.com/oauth/mindsort/.well-known/oauth-authorization-server  ← this document
  → registration_endpoint: .../oauth/mindsort/register
  → DCR assigns clarity.write scope
  → MindSort consent screen shown
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.core.config import settings

router = APIRouter(tags=["oauth-provider"])

SCOPES_SUPPORTED_MINDSORT = ["clarity.write"]


def _mindsort_authorization_server_metadata() -> dict:
    return {
        "issuer": settings.OAUTH_ISSUER,  # DO NOT change per app — shared JWT issuer for all apps. Changing this breaks token validation across PG and MindSort AI.
        "authorization_endpoint": f"{settings.OAUTH_ISSUER}/oauth/mindsort/authorize",
        "token_endpoint": f"{settings.OAUTH_ISSUER}/oauth/mindsort/token",
        "jwks_uri": f"{settings.OAUTH_ISSUER}/oauth/mindsort/jwks",
        "registration_endpoint": f"{settings.OAUTH_ISSUER}/oauth/mindsort/register",
        "scopes_supported": SCOPES_SUPPORTED_MINDSORT,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    }


@router.get("/.well-known/oauth-authorization-server")
async def mindsort_oauth_authorization_server():
    return JSONResponse(_mindsort_authorization_server_metadata())


@router.get("/.well-known/openid-configuration")
async def mindsort_openid_configuration():
    return JSONResponse(_mindsort_authorization_server_metadata())
