"""
Token encryption using Fernet (AES-256).

Never logs or prints token values.
"""

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
