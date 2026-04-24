"""
OAuth Provider Router — Thin orchestrator for OAuth 2.1 provider endpoints.

This router is a THIN orchestrator that delegates all OAuth functionality
to specialized modules in backend/core/oauth_provider/.

Architecture (Post Phase 1 Refactoring):
- All OAuth provider code relocated from backend/apps/focused/oauth/ to backend/core/oauth_provider/
- Each endpoint has its own router module in backend/core/oauth_provider/
- Service layer separated in backend/core/oauth_provider/services/
- Validators in backend/core/oauth_provider/validators/
- JWT utilities in backend/core/oauth_provider/jwt/
- Shared models in backend/core/oauth_provider/models.py
- Shared exceptions in backend/core/oauth_provider/exceptions.py
- Zero inline logic in this orchestrator

Included Endpoints (served for three SDK app route families: focused, pg, mindsort):
- Discovery: /.well-known/openid-configuration, /.well-known/oauth-authorization-server
- JWKS: /oauth/{focused,pg,mindsort}/jwks
- Authorization: /oauth/{focused,pg,mindsort}/authorize (OAuth 2.1 + PKCE)
- Consent UI: /oauth/{focused,pg,mindsort}/consent
- Token: /oauth/{focused,pg,mindsort}/token (authorization_code, refresh_token grants)
- Registration: /oauth/{focused,pg,mindsort}/register (RFC 7591 dynamic client registration)
- Revocation: /oauth/{focused,pg,mindsort}/revoke (RFC 7009 token revocation)
- MindSort-specific discovery: /oauth/mindsort/.well-known/oauth-authorization-server

Status: Consolidated OAuth 2.1 provider for all SDK apps
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
from backend.core.oauth_provider.mindsort_discovery import router as mindsort_discovery_router

router = APIRouter(tags=["oauth-provider"])

# Include extracted routers
router.include_router(authorize_router)
router.include_router(consent_router)
router.include_router(discovery_router)
router.include_router(jwks_router)
router.include_router(register_router)
router.include_router(token_router)
router.include_router(revoke_router)

# MindSort AI app-specific discovery (mounted with prefix)
router.include_router(mindsort_discovery_router, prefix="/oauth/mindsort")
