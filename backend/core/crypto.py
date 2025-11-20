"""
RSA key management and JWT signing for OAuth provider (Increment 7A).

Security:
- Keys loaded from environment variables (base64-encoded PEM)
- Private key never exposed via API
- JWKS contains only public components
- No key material in logs
"""

import base64
import logging

from jose import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from backend.core.config import settings

logger = logging.getLogger(__name__)

# Module-level key storage (loaded once on import)
_private_key: rsa.RSAPrivateKey | None = None
_public_key: rsa.RSAPublicKey | None = None
_jwks_cache: dict | None = None


def _load_private_key_from_env() -> rsa.RSAPrivateKey:
    """
    Load RSA private key from environment variable.

    Returns:
        RSA private key object

    Raises:
        RuntimeError: If key loading fails
    """
    try:
        # Decode base64 to get PEM bytes
        pem_bytes = base64.b64decode(settings.OAUTH_RSA_PRIVATE_KEY)

        # Load PEM as RSA private key
        private_key = serialization.load_pem_private_key(
            pem_bytes,
            password=None,
            backend=default_backend()
        )

        if not isinstance(private_key, rsa.RSAPrivateKey):
            raise ValueError("Key is not RSA private key")

        return private_key

    except Exception as e:
        raise RuntimeError(f"Failed to load RSA private key: {e}")


def _load_public_key_from_env() -> rsa.RSAPublicKey:
    """
    Load RSA public key from environment variable.

    Returns:
        RSA public key object

    Raises:
        RuntimeError: If key loading fails
    """
    try:
        # Decode base64 to get PEM bytes
        pem_bytes = base64.b64decode(settings.OAUTH_RSA_PUBLIC_KEY)

        # Load PEM as RSA public key
        public_key = serialization.load_pem_public_key(
            pem_bytes,
            backend=default_backend()
        )

        if not isinstance(public_key, rsa.RSAPublicKey):
            raise ValueError("Key is not RSA public key")

        return public_key

    except Exception as e:
        raise RuntimeError(f"Failed to load RSA public key: {e}")


def _initialize_keys():
    """Load keys on module import (fail fast if missing)."""
    global _private_key, _public_key

    try:
        _private_key = _load_private_key_from_env()
        _public_key = _load_public_key_from_env()
        logger.info(f"OAuth RSA keys loaded successfully (kid={settings.OAUTH_JWT_KID})")
    except Exception as e:
        raise RuntimeError(
            f"Failed to initialize OAuth keys: {e}. "
            "Run: python scripts/generate_oauth_keys.py"
        )


# Initialize keys on module import
_initialize_keys()


def sign_jwt(payload: dict, kid: str) -> str:
    """
    Sign a JWT using RS256 with private key.

    Args:
        payload: JWT payload (claims)
        kid: Key ID to include in JWT header

    Returns:
        Signed JWT string

    Raises:
        RuntimeError: If signing fails
    """
    if _private_key is None:
        raise RuntimeError("Private key not loaded")

    try:
        # Encode private key to PEM for python-jose
        private_pem = _private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        # Sign JWT with RS256
        token = jwt.encode(
            payload,
            private_pem,
            algorithm="RS256",
            headers={"kid": kid}
        )

        return token

    except Exception as e:
        logger.error(f"JWT signing failed: {e}")
        raise RuntimeError(f"Failed to sign JWT: {e}")


def get_current_jwks() -> dict:
    """
    Get JWKS (JSON Web Key Set) with public key components.

    Returns:
        JWKS dictionary with public key in JWK format

    Example:
        {
          "keys": [
            {
              "kty": "RSA",
              "use": "sig",
              "kid": "focused-2025-11",
              "alg": "RS256",
              "n": "<base64url_modulus>",
              "e": "AQAB"
            }
          ]
        }
    """
    global _jwks_cache

    # Return cached JWKS if available
    if _jwks_cache is not None:
        return _jwks_cache

    if _public_key is None:
        raise RuntimeError("Public key not loaded")

    try:
        # Extract public key components
        public_numbers = _public_key.public_numbers()

        # Convert to JWK format (RFC 7517)
        # n = modulus (base64url-encoded)
        # e = exponent (base64url-encoded)
        n = _int_to_base64url(public_numbers.n)
        e = _int_to_base64url(public_numbers.e)

        jwks = {
            "keys": [
                {
                    "kty": "RSA",
                    "use": "sig",
                    "kid": settings.OAUTH_JWT_KID,
                    "alg": "RS256",
                    "n": n,
                    "e": e
                }
            ]
        }

        # Cache JWKS
        _jwks_cache = jwks

        return jwks

    except Exception as e:
        logger.error(f"JWKS generation failed: {e}")
        raise RuntimeError(f"Failed to generate JWKS: {e}")


def _int_to_base64url(value: int) -> str:
    """
    Convert integer to base64url-encoded string.

    Args:
        value: Integer value (e.g., RSA modulus or exponent)

    Returns:
        Base64url-encoded string

    Note:
        Used for JWK encoding per RFC 7517
    """
    # Convert integer to bytes (big-endian)
    value_bytes = value.to_bytes((value.bit_length() + 7) // 8, byteorder='big')

    # Base64url encode (no padding)
    encoded = base64.urlsafe_b64encode(value_bytes).rstrip(b'=').decode('ascii')

    return encoded


# Expose public key for validation (7B will use this)
def get_public_key() -> rsa.RSAPublicKey:
    """
    Get public key for JWT validation.

    Returns:
        RSA public key object

    Note:
        Used by token validation logic in 7B
    """
    if _public_key is None:
        raise RuntimeError("Public key not loaded")
    return _public_key
