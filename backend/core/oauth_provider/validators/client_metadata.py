"""
Client Metadata Validation for OAuth 2.1 Dynamic Client Registration.

Validates client registration requests per RFC 7591.
"""

from typing import List


def validate_redirect_uris(
    redirect_uris: List[str],
    allowed_uris: List[str] | None = None
) -> tuple[bool, str | None]:
    """
    Validate redirect URIs for client registration.

    RFC 9728 B2-8 Security Requirements:
    - At least one redirect_uri required
    - When allowlist is provided, URIs must match an allowlist entry
    - Entries ending with "/" are prefix matches (for dynamic callback IDs)
    - Other entries are exact string matches
    - When allowlist is None (legacy mode), only HTTPS check is performed

    Args:
        redirect_uris: List of redirect URIs to validate
        allowed_uris: Optional allowlist of permitted redirect URIs.
            Entries ending with "/" are treated as prefix matches.
            Other entries require exact match.
            If None, falls back to HTTPS-only validation (legacy behavior).

    Returns:
        tuple: (is_valid, error_message)
            - (True, None) if valid
            - (False, error_message) if invalid

    Example:
        >>> allowed = ["https://chatgpt.com/connector/oauth/", "https://example.com/cb"]
        >>> validate_redirect_uris(["https://chatgpt.com/connector/oauth/ABC123"], allowed)
        (True, None)  # prefix match
        >>> validate_redirect_uris(["https://example.com/cb"], allowed)
        (True, None)  # exact match
        >>> validate_redirect_uris(["https://evil.com/callback"], allowed)
        (False, "redirect_uri not in allowlist")
    """
    if not redirect_uris or len(redirect_uris) == 0:
        return False, "At least one redirect_uri is required"

    if allowed_uris is not None:
        # RFC 9728 B2-8: Allowlist validation
        # Entries ending with "/" are prefix matches (e.g., connector/oauth/)
        # All other entries are exact string matches
        def _is_allowed(uri: str) -> bool:
            for allowed in allowed_uris:
                if allowed.endswith("/"):
                    # Prefix match for entries like "https://chatgpt.com/connector/oauth/"
                    if uri.startswith(allowed):
                        return True
                else:
                    # Exact match for other entries
                    if uri == allowed:
                        return True
            return False

        for uri in redirect_uris:
            if not _is_allowed(uri):
                return False, "redirect_uri not in allowlist"
    else:
        # Legacy mode: Only check HTTPS (for backward compatibility)
        for uri in redirect_uris:
            if not uri.startswith("https://"):
                return False, "redirect_uri must use HTTPS"

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
