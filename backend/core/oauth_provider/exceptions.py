"""
Standardized OAuth 2.1 exceptions (Increment 7C).

Provides RFC 6749-compliant error responses with structured logging.
"""

from fastapi import HTTPException


class OAuthError(HTTPException):
    """
    Base class for OAuth errors.

    Provides standardized error responses per RFC 6749 section 5.2.
    """

    def __init__(self, error: str, description: str, status_code: int = 400):
        """
        Initialize OAuth error.

        Args:
            error: OAuth error code (e.g., "invalid_grant")
            description: Human-readable error description
            status_code: HTTP status code (default: 400)
        """
        self.error = error
        self.description = description
        super().__init__(status_code=status_code, detail=description)


class InvalidRequestError(OAuthError):
    """
    Error: invalid_request

    The request is missing a required parameter, includes an
    invalid parameter value, includes a parameter more than once,
    or is otherwise malformed.
    """

    def __init__(self, description: str = "Invalid request"):
        super().__init__("invalid_request", description, status_code=400)


class InvalidClientError(OAuthError):
    """
    Error: invalid_client

    Client authentication failed (e.g., unknown client, no client
    authentication included, or unsupported authentication method).
    """

    def __init__(self, description: str = "Invalid client"):
        super().__init__("invalid_client", description, status_code=401)


class InvalidGrantError(OAuthError):
    """
    Error: invalid_grant

    The provided authorization grant (e.g., authorization code, refresh token)
    is invalid, expired, revoked, does not match the redirection URI used in
    the authorization request, or was issued to another client.

    Per OAuth 2.1 spec (RFC 6749 Section 5.2), invalid_grant returns 400 Bad Request.
    """

    def __init__(self, description: str = "Invalid grant"):
        super().__init__("invalid_grant", description, status_code=400)


class UnauthorizedClientError(OAuthError):
    """
    Error: unauthorized_client

    The authenticated client is not authorized to use this
    authorization grant type.
    """

    def __init__(self, description: str = "Unauthorized client"):
        super().__init__("unauthorized_client", description, status_code=400)


class UnsupportedGrantTypeError(OAuthError):
    """
    Error: unsupported_grant_type

    The authorization grant type is not supported by the
    authorization server.
    """

    def __init__(self, description: str = "Unsupported grant type"):
        super().__init__("unsupported_grant_type", description, status_code=400)


class InvalidScopeError(OAuthError):
    """
    Error: invalid_scope

    The requested scope is invalid, unknown, malformed, or
    exceeds the scope granted by the resource owner.
    """

    def __init__(self, description: str = "Invalid scope"):
        super().__init__("invalid_scope", description, status_code=400)


class AccessDeniedError(OAuthError):
    """
    Error: access_denied

    The resource owner or authorization server denied the request.
    """

    def __init__(self, description: str = "Access denied"):
        super().__init__("access_denied", description, status_code=403)


class UnsupportedResponseTypeError(OAuthError):
    """
    Error: unsupported_response_type

    The authorization server does not support obtaining an
    authorization code using this method.
    """

    def __init__(self, description: str = "Unsupported response type"):
        super().__init__("unsupported_response_type", description, status_code=400)


class ServerError(OAuthError):
    """
    Error: server_error

    The authorization server encountered an unexpected condition
    that prevented it from fulfilling the request.
    """

    def __init__(self, description: str = "Server error"):
        super().__init__("server_error", description, status_code=500)


class TemporarilyUnavailableError(OAuthError):
    """
    Error: temporarily_unavailable

    The authorization server is currently unable to handle the request
    due to a temporary overloading or maintenance of the server.
    """

    def __init__(self, description: str = "Temporarily unavailable"):
        super().__init__("temporarily_unavailable", description, status_code=503)
