"""
Client Metadata Validation for OAuth 2.1 Dynamic Client Registration.

Validates client registration requests per RFC 7591.
"""

from typing import List


def validate_redirect_uris(redirect_uris: List[str]) -> tuple[bool, str | None]:
    """
    Validate redirect URIs for client registration.

    OAuth 2.1 Security Requirements:
    - At least one redirect_uri required
    - Must use HTTPS (no http:// allowed except localhost for development)

    Args:
        redirect_uris: List of redirect URIs to validate

    Returns:
        tuple: (is_valid, error_message)
            - (True, None) if valid
            - (False, error_message) if invalid

    Example:
        >>> validate_redirect_uris(["https://example.com/callback"])
        (True, None)
        >>> validate_redirect_uris([])
        (False, "At least one redirect_uri is required")
        >>> validate_redirect_uris(["http://example.com/callback"])
        (False, "redirect_uri must use HTTPS: http://example.com/callback")
    """
    if not redirect_uris or len(redirect_uris) == 0:
        return False, "At least one redirect_uri is required"

    for uri in redirect_uris:
        if not uri.startswith("https://"):
            return False, f"redirect_uri must use HTTPS: {uri}"

    return True, None


def validate_grant_types(grant_types: List[str] | None) -> tuple[bool, str | None]:
    """
    Validate grant types for client registration.

    Allowed grant types:
    - authorization_code
    - refresh_token

    Args:
        grant_types: List of grant types (or None for defaults)

    Returns:
        tuple: (is_valid, error_message)
            - (True, None) if valid
            - (False, error_message) if invalid

    Example:
        >>> validate_grant_types(["authorization_code", "refresh_token"])
        (True, None)
        >>> validate_grant_types(["client_credentials"])
        (False, "Invalid grant types. Allowed: authorization_code, refresh_token")
    """
    if grant_types is None:
        return True, None

    allowed_grant_types = {"authorization_code", "refresh_token"}
    if not set(grant_types).issubset(allowed_grant_types):
        return False, f"Invalid grant types. Allowed: {', '.join(allowed_grant_types)}"

    return True, None


def validate_client_name(client_name: str | None) -> tuple[bool, str | None]:
    """
    Validate client name for client registration.

    Args:
        client_name: Client name to validate

    Returns:
        tuple: (is_valid, error_message)
            - (True, None) if valid
            - (False, error_message) if invalid

    Example:
        >>> validate_client_name("My OAuth Client")
        (True, None)
        >>> validate_client_name(None)
        (False, "client_name is required")
    """
    if not client_name:
        return False, "client_name is required"

    return True, None
