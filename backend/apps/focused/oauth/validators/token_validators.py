"""
Token Validators - Pure validation functions for token requests.

No database calls. Only argument/form validation.
"""

from datetime import datetime, timezone


def validate_grant_type(grant_type: str) -> tuple[bool, str | None]:
    """
    Validate grant_type is supported.

    Allowed values:
    - authorization_code
    - refresh_token

    Args:
        grant_type: Grant type from request

    Returns:
        tuple: (is_valid, error_message)

    Example:
        >>> validate_grant_type("authorization_code")
        (True, None)
        >>> validate_grant_type("client_credentials")
        (False, "unsupported_grant_type")
    """
    if grant_type not in ("authorization_code", "refresh_token"):
        return False, "unsupported_grant_type"
    return True, None


def validate_authorization_code_request(
    code: str | None,
    code_verifier: str | None,
    client_id: str | None,
    redirect_uri: str | None
) -> tuple[bool, str | None]:
    """
    Validate required fields for authorization_code grant.

    Args:
        code: Authorization code
        code_verifier: PKCE code verifier
        client_id: Client identifier
        redirect_uri: Redirect URI

    Returns:
        tuple: (is_valid, error_field_name)

    Example:
        >>> validate_authorization_code_request("abc", "xyz", "client-1", "https://example.com")
        (True, None)
        >>> validate_authorization_code_request(None, "xyz", "client-1", "https://example.com")
        (False, "code")
    """
    if not code:
        return False, "code"
    if not code_verifier:
        return False, "code_verifier"
    if not client_id:
        return False, "client_id"
    if not redirect_uri:
        return False, "redirect_uri"
    return True, None


def validate_refresh_token_request(
    refresh_token: str | None,
    client_id: str | None
) -> tuple[bool, str | None]:
    """
    Validate required fields for refresh_token grant.

    Args:
        refresh_token: Refresh token
        client_id: Client identifier

    Returns:
        tuple: (is_valid, error_field_name)

    Example:
        >>> validate_refresh_token_request("abc123", "client-1")
        (True, None)
        >>> validate_refresh_token_request(None, "client-1")
        (False, "refresh_token")
    """
    if not refresh_token:
        return False, "refresh_token"
    if not client_id:
        return False, "client_id"
    return True, None


def validate_token_not_expired(expires_at: datetime) -> bool:
    """
    Check if token has not expired.

    Args:
        expires_at: Token expiration datetime (timezone-aware)

    Returns:
        bool: True if not expired, False if expired

    Example:
        >>> from datetime import timedelta
        >>> future = datetime.now(timezone.utc) + timedelta(hours=1)
        >>> validate_token_not_expired(future)
        True
        >>> past = datetime.now(timezone.utc) - timedelta(hours=1)
        >>> validate_token_not_expired(past)
        False
    """
    return expires_at >= datetime.now(timezone.utc)


def validate_client_id_match(expected: str, actual: str) -> bool:
    """
    Validate client_id matches expected value.

    Args:
        expected: Expected client_id
        actual: Actual client_id from request

    Returns:
        bool: True if match, False otherwise

    Example:
        >>> validate_client_id_match("client-1", "client-1")
        True
        >>> validate_client_id_match("client-1", "client-2")
        False
    """
    return expected == actual


def validate_redirect_uri_match(expected: str, actual: str) -> bool:
    """
    Validate redirect_uri matches expected value.

    Args:
        expected: Expected redirect_uri
        actual: Actual redirect_uri from request

    Returns:
        bool: True if match, False otherwise

    Example:
        >>> validate_redirect_uri_match("https://example.com", "https://example.com")
        True
        >>> validate_redirect_uri_match("https://example.com", "https://evil.com")
        False
    """
    return expected == actual
