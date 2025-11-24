"""
Token encryption using Fernet (AES-256).

Never logs or prints token values.
"""

import hashlib
from cryptography.fernet import Fernet, InvalidToken

from backend.core.config import settings


def _get_encryption_key() -> bytes:
    """Load encryption key from settings."""
    try:
        return settings.ENCRYPTION_KEY.encode()
    except Exception as e:
        raise ValueError(f"Invalid ENCRYPTION_KEY format: {e}")


_fernet = None


def _get_fernet() -> Fernet:
    """Get or create Fernet instance."""
    global _fernet
    if _fernet is None:
        try:
            _fernet = Fernet(_get_encryption_key())
        except Exception as e:
            raise ValueError(f"Failed to initialize Fernet cipher: {e}")
    return _fernet


def encrypt_token(token: str) -> str:
    """
    Encrypt a token using Fernet (AES-256).

    Args:
        token: Plain text token to encrypt

    Returns:
        Base64-encoded encrypted token

    Raises:
        ValueError: If encryption fails
    """
    if not token:
        raise ValueError("Token cannot be empty")

    try:
        fernet = _get_fernet()
        encrypted = fernet.encrypt(token.encode())
        return encrypted.decode()
    except Exception as e:
        raise ValueError(f"Token encryption failed: {e}")


def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypt a token using Fernet (AES-256).

    Args:
        encrypted_token: Base64-encoded encrypted token

    Returns:
        Plain text token

    Raises:
        ValueError: If decryption fails or token is invalid
    """
    if not encrypted_token:
        raise ValueError("Encrypted token cannot be empty")

    try:
        fernet = _get_fernet()
        decrypted = fernet.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except InvalidToken:
        raise ValueError("Invalid or corrupted encrypted token")
    except Exception as e:
        raise ValueError(f"Token decryption failed: {e}")


def hash_refresh_token(token: str) -> str:
    """
    Hash a refresh token using SHA-256 for database indexing.

    This allows O(1) indexed lookups instead of O(n) full table scans.
    The encrypted token is still stored for security, but the hash
    enables fast lookups.

    Args:
        token: Plain text refresh token

    Returns:
        64-character hex string (SHA-256 hash)

    Security Notes:
        - Uses SHA-256 (not for passwords, for indexing)
        - No salt needed (tokens are cryptographically random)
        - Enables indexed database lookup
        - Original encrypted token still stored for security

    Example:
        >>> hash_refresh_token("abc123...")
        "2c26b46b68ffc68ff99b453c1d30413413422d706..."
    """
    if not token:
        raise ValueError("Token cannot be empty")

    return hashlib.sha256(token.encode()).hexdigest()
