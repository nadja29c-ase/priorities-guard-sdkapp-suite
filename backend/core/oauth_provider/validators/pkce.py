"""
PKCE (Proof Key for Code Exchange) Validation.

Implements RFC 7636 PKCE verification for OAuth 2.1 authorization code flow.
"""

import base64
import secrets
from hashlib import sha256


def verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """
    Verify PKCE code_verifier matches code_challenge.

    Implements S256 challenge method:
    - BASE64URL(SHA256(code_verifier)) == code_challenge

    Args:
        code_verifier: Client-provided code verifier (43-128 characters)
        code_challenge: Stored code challenge from authorization request

    Returns:
        bool: True if PKCE verification succeeds, False otherwise

    Example:
        >>> verify_pkce("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk", "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
        True
    """
    # Compute SHA256 hash of code_verifier
    code_verifier_hash = sha256(code_verifier.encode()).digest()

    # Base64url-encode the hash (without padding)
    code_challenge_computed = base64.urlsafe_b64encode(code_verifier_hash).rstrip(b'=').decode('ascii')

    # Constant-time comparison to prevent timing attacks
    return secrets.compare_digest(code_challenge_computed, code_challenge)


def validate_code_challenge_method(method: str) -> bool:
    """
    Validate code_challenge_method is S256.

    OAuth 2.1 requires S256 (no plain method allowed).

    Args:
        method: code_challenge_method from authorization request

    Returns:
        bool: True if method is "S256", False otherwise
    """
    return method == "S256"
