"""
JWT Signer - OAuth 2.1 access token generation.

Handles JWT creation and signing with RS256.
"""

from datetime import timedelta
from uuid import UUID

from backend.core.oauth_provider.jwt.utils import create_access_token as core_create_access_token


def create_access_token(
    user_id: UUID,
    client_id: str,
    scope: str,
    expires_delta: timedelta | None = None
) -> tuple[str, str]:
    """
    Create a signed JWT access token.

    Delegates to core JWT utils for actual signing.

    Args:
        user_id: User UUID
        client_id: OAuth client identifier
        scope: Space-separated scopes (e.g., "focused.read focused.write")
        expires_delta: Token expiration delta (default: 1 hour from config)

    Returns:
        Tuple of (access_token, jti)
        - access_token: Signed RS256 JWT
        - jti: JWT ID (for revocation tracking)

    JWT Claims:
        - sub: User ID (UUID as string)
        - aud: OAuth issuer (audience)
        - iss: OAuth issuer
        - exp: Expiration timestamp (Unix epoch)
        - iat: Issued-at timestamp (Unix epoch)
        - jti: JWT ID (unique identifier)
        - scope: Space-separated scopes
        - client_id: OAuth client identifier

    Example:
        >>> access_token, jti = create_access_token(
        ...     UUID("12345678-1234-1234-1234-123456789abc"),
        ...     "focused-client-456",
        ...     "focused.read focused.write"
        ... )
        >>> print(jti)
        87654321-4321-4321-4321-210987654321
    """
    return core_create_access_token(
        user_id=user_id,
        client_id=client_id,
        scope=scope,
        expires_delta=expires_delta
    )
