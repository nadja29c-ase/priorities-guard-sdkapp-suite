"""
Client Service - OAuth 2.1 dynamic client registration.

Handles client creation with secure credential generation and encryption.
"""

import secrets
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.encryption import encrypt_token
from backend.core.logging import get_logger
from backend.core.oauth_models import OAuthClient

logger = get_logger(__name__)


async def create_oauth_client(
    db: AsyncSession,
    client_name: str,
    redirect_uris: list[str],
    grant_types: list[str] | None = None,
    correlation_id: str | None = None
) -> tuple[str, str]:
    """
    Create a new OAuth client with encrypted credentials.

    Generates:
    - Unique client_id (focused-client-{uuid})
    - Secure client_secret (32-byte URL-safe token)
    - Encrypted client_secret_enc (AES-256 via Fernet)

    Args:
        db: Database session
        client_name: Human-readable client name
        redirect_uris: List of allowed redirect URIs
        grant_types: Optional list of grant types (default: authorization_code, refresh_token)
        correlation_id: Optional correlation ID for logging

    Returns:
        tuple: (client_id, client_secret)
            - client_id: Generated client identifier
            - client_secret: Plain-text client secret (return to client, never store)

    Security Notes:
        - client_secret is NEVER stored in plain text
        - Only encrypted client_secret_enc is persisted to database
        - Returns plain-text client_secret for one-time delivery to client
        - Client must store client_secret securely (never shown again)

    Example:
        >>> client_id, client_secret = await create_oauth_client(
        ...     db, "My App", ["https://example.com/callback"]
        ... )
        >>> print(client_id)
        focused-client-12345678-1234-1234-1234-123456789abc
        >>> print(client_secret)
        dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
    """
    # Set default grant types
    if grant_types is None:
        grant_types = ["authorization_code", "refresh_token"]

    # Generate client credentials
    client_id = f"focused-client-{uuid4()}"
    client_secret = secrets.token_urlsafe(32)  # 256-bit random secret

    # Encrypt client_secret for database storage (AES-256)
    # CRITICAL: Never store plain-text client_secret
    client_secret_encrypted = encrypt_token(client_secret)

    # Create client record
    client = OAuthClient(
        client_id=client_id,
        client_secret_enc=client_secret_encrypted,
        client_name=client_name,
        redirect_uris=redirect_uris,
        allowed_scopes="focused.read focused.write focused.notify",
        grant_types=grant_types
    )

    db.add(client)
    await db.commit()

    # Log success (no secrets logged)
    request_logger = logger.bind(correlation_id=correlation_id) if correlation_id else logger
    request_logger.info(
        "oauth.register.success",
        client_id=client_id,
        client_name=client_name,
        redirect_uris_count=len(redirect_uris)
    )

    # Return plain-text client_secret (only time it's available)
    return client_id, client_secret
