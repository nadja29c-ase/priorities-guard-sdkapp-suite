"""
JWKS Endpoint - JSON Web Key Set for JWT signature verification.

Provides public keys for validating JWTs issued by this OAuth provider.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.core.oauth_provider.services.jwks_service import get_jwks

router = APIRouter(tags=["oauth-provider"])


@router.get("/oauth/focused/jwks")
@router.get("/oauth/pg/jwks")
@router.get("/oauth/mindsort/jwks")
async def jwks_endpoint():
    """
    JSON Web Key Set (JWKS) endpoint.

    Returns public keys for JWT signature verification.
    Cached in Redis with 24h TTL.

    Returns:
        JSONResponse: JWKS document containing public keys

    Example Response:
        {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": "oauth-rsa-key-2024",
                    "n": "...",
                    "e": "AQAB"
                }
            ]
        }
    """
    jwks = await get_jwks()
    return JSONResponse(jwks)
