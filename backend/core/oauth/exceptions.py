"""
Exception hierarchy for Google OAuth operations.

Service layer raises these exceptions; router catches and renders HTML.
"""


class GoogleOAuthError(Exception):
    """Base class for all Google OAuth errors."""


class ConnectionTokenExpiredError(GoogleOAuthError):
    """Opaque token invalid or expired."""


class StateInvalidError(GoogleOAuthError):
    """OAuth state missing, invalid, or expired."""


class TokenExchangeError(GoogleOAuthError):
    """Google rejected the authorization code or scope missing."""


class StateStorageError(GoogleOAuthError):
    """Failed to store OAuth state in Redis (service unavailable)."""
