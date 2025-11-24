#!/usr/bin/env python3
"""Generate test JWT token for manual testing of increment 7D."""

import os
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.core.crypto import sign_jwt
from backend.core.config import settings

def generate_token(
    user_id: str = "00000000-0000-0000-0000-000000000001",
    client_id: str = "focused-client-ff142fb8-19a6-4d48-b6b7-f4032974443d",
    scopes: str = "focused.read focused.write focused.notify",
    expiry_seconds: int = 3600
) -> str:
    """
    Generate a test JWT token.

    Args:
        user_id: Subject (sub) claim
        client_id: Authorized party (azp) claim
        scopes: Space-separated scopes
        expiry_seconds: Token expiry in seconds

    Returns:
        Signed JWT token string
    """
    # Create JWT payload
    now = int(time.time())
    payload = {
        "iss": "https://www.priority-guard.com/oauth/focused",
        "aud": "https://www.priority-guard.com/mcp/focused",
        "sub": user_id,
        "azp": client_id,
        "scope": scopes,
        "jti": f"test-token-{now}",
        "iat": now,
        "exp": now + expiry_seconds,
        "nbf": now - 10  # Valid from 10 seconds ago
    }

    # Sign JWT using backend crypto module
    token = sign_jwt(payload, kid=settings.OAUTH_JWT_KID)

    return token


if __name__ == "__main__":
    # Generate token with default settings
    token = generate_token()
    print(token)
