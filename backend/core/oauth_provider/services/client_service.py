"""
Client Service - OAuth 2.1 dynamic client registration.

Handles client creation with secure credential generation and encryption.
"""

import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.encryption import encrypt_token
from backend.core.logging import get_logger, mask_client_id
from backend.core.models import CoreConnection

logger = get_logger(__name__)


async def create_oauth_client(
    db: AsyncSession,
    client_name: str,
    redirect_uris: list[str],
    grant_types: list[str] | None = None,
    scopes: list[str] | None = None,
    correlation_id: str | None = None
) -> tuple[str, str]:
    """
    Create a new OAuth client with encrypted credentials.

    Generates:
    - Unique client_id (pg-client-{uuid})
    - Secure client_secret (32-byte URL-safe token)
    - Encrypted client_secret_enc (AES-256 via Fernet)

    Args:
        db: Database session
        client_name: Human-readable client name
        redirect_uris: List of allowed redirect URIs
        grant_types: Optional list of grant types (default: authorization_code, refresh_token)
        scopes: List of scopes. Required in practice — passing None raises ValueError.
                Typing stays Optional to preserve the signature; callers must always
                provide explicit scopes (per-route defaults are computed in
                register_client.py).
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
        pg-client-12345678-1234-1234-1234-123456789abc
        >>> print(client_secret)
        dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
    """
    # Set default grant types
    if grant_types is None:
        grant_types = ["authorization_code", "refresh_token"]

    # Scopes must be explicitly provided by the caller.
    # Previously this block fell back to a union of scopes across ALL SDK apps,
    # which is a cross-app privilege escalation landmine. Per-route defaults are
    # computed in register_client.py — no global default is correct here.
    if scopes is None:
        raise ValueError(
            "scopes must be explicitly provided — no global defaults allowed. "
            "Callers should resolve per-route defaults before calling create_oauth_client."
        )

    # Generate client credentials
    # Prefix: pg = Priority Guardian (neutral, works for all apps)
    client_id = f"pg-client-{uuid4()}"
    client_secret = secrets.token_urlsafe(32)  # 256-bit random secret

    # Encrypt client_secret for database storage (AES-256)
    # CRITICAL: Never store plain-text client_secret
    client_secret_encrypted = encrypt_token(client_secret)

    # Create client record as OAuth provider connection
    # Note: user_id is NULL for OAuth provider connections
    #
    # MODELING DECISION: provider=client_name
    # We reuse the provider field for the human-readable client name.
    # This means multiple OAuth clients can share the same provider value.
    # Queries like "SELECT * FROM connections WHERE provider='X'" may return
    # multiple rows. Use connection_type='oauth_provider' + client_id for
    # unique lookups. If this becomes problematic, consider adding a fixed
    # provider value (e.g., "oauth_client") and a separate client_name column.
    client = CoreConnection(
        user_id=None,  # OAuth provider clients are not user-specific
        provider=client_name,  # Human-readable name (see note above)
        connection_type="oauth_provider",
        client_id=client_id,
        client_secret_enc=client_secret_encrypted,
        redirect_uris=redirect_uris,
        grant_types=grant_types,
        # Required fields (set to defaults for oauth_provider connections)
        encrypted_access_token="",  # Not applicable for inbound OAuth
        scopes=scopes,  # OAuth scopes (defaults or requested)
        # token_expires_at: Not meaningful for oauth_provider connections.
        # OAuth provider clients don't have expiring tokens - they issue tokens.
        # Set to 1 year as a placeholder to satisfy NOT NULL constraint.
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
    )

    db.add(client)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    # Log success (no secrets logged)
    request_logger = logger.bind(correlation_id=correlation_id) if correlation_id else logger
    request_logger.info(
        "oauth.register.success",
        client_id=mask_client_id(client_id),
        client_name=client_name,
        redirect_uris_count=len(redirect_uris)
    )

    # Return plain-text client_secret (only time it's available)
    return client_id, client_secret
