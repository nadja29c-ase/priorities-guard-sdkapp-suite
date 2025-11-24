"""
OAuth Provider Router — Thin orchestrator for OAuth 2.1 provider endpoints.

This module is a THIN orchestrator that delegates all OAuth functionality
to specialized modules.

Architecture:
- All business logic extracted to backend/core/oauth_provider/
- Each endpoint has its own module + service layer
- Validators separated for reusability
- Zero inline logic in this router

Included Endpoints:
- Discovery: /.well-known/openid-configuration, oauth-protected-resource
- JWKS: /oauth/focused/jwks
- Authorization: /oauth/focused/authorize
- Consent UI: /oauth/focused/consent
- Token: /oauth/focused/token (authorization_code, refresh_token grants)
- Registration: /oauth/focused/register (dynamic client registration)
- Revocation: /oauth/focused/revoke (RFC 7009)

Status: Refactored for maintainability and security audits
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

# Include extracted routers
router.include_router(authorize_router)
router.include_router(consent_router)
router.include_router(discovery_router)
router.include_router(jwks_router)
router.include_router(register_router)
router.include_router(token_router)
router.include_router(revoke_router)
