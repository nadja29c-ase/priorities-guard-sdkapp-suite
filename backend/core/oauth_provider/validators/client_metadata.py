"""
Client Metadata Validation for OAuth 2.1 Dynamic Client Registration.

Validates client registration requests per RFC 7591.
"""

from typing import List
from urllib.parse import urlsplit, urlunsplit

# RFC 8252 loopback redirect support for native/local MCP clients.
#
# Loopback IP literals with ephemeral ports are the sanctioned native-app pattern
# (RFC 8252). "localhost" is NOT endorsed by RFC 8252 §8.3 — it explicitly prefers IP
# literals because name resolution can be redirected — but the MCP specification and
# Anthropic's documented callbacks use it, so it is accepted under the same narrow
# restrictions as an interoperability requirement.
#
# IPv6 ::1 is DELIBERATELY EXCLUDED, not overlooked.
# authorize.py::_normalize_redirect_uri strips the port with
# `parsed.netloc.lower().split(":")[0]`, which is IPv4-only: for "[::1]:41234" it
# yields "[", so the ::1 entry in its localhost tuple is unreachable and the URI is
# rejected with "Invalid redirect_uri format". Accepting ::1 here would let a client
# REGISTER a redirect URI that can never complete an authorization — a worse failure
# than rejecting it, because it surfaces later and looks like something else.
# Fixing the authorize-side host parsing is the correct long-term resolution, but that
# function is shared with the ChatGPT authorize path on two published apps, so it is
# filed as backlog rather than changed here. Verified 2026-07-30: of every URI this
# validator accepts, "[::1]" was the only one authorize rejects.
#
# Matching operates on the PARSED url, never on the raw string. The .port attribute
# raising on a malformed port is handled explicitly below.
_LOOPBACK_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1"})

# Callback paths accepted on loopback. Exact match only.
_LOOPBACK_PATHS: frozenset[str] = frozenset({
    "/oauth/callback",
    "/oauth/callback/debug",
    "/callback",
})


def _is_loopback_redirect_uri(uri: str) -> bool:
    """
    True only for a narrowly-constrained RFC 8252 style loopback redirect URI.

    ALL of the following must hold:
      - scheme is exactly http (https loopback is rejected — not the native-app pattern)
      - parsed hostname is exactly one of localhost / 127.0.0.1 (see _LOOPBACK_HOSTS
        for why ::1 is excluded)
      - port is any valid port, or absent; port 0 is rejected
      - path exactly matches an approved callback path
      - no query, no fragment, no userinfo

    Returns False (never raises) for malformed input, so a bad DCR request produces a
    clean 400 rather than a 500.
    """
    try:
        parts = urlsplit(uri)
    except ValueError:
        return False

    # VALIDATE THE STRING THAT GETS STORED, NOT A CLEANED COPY OF IT.
    # urlsplit follows WHATWG and silently strips ASCII tab/CR/LF from anywhere in the
    # URL, plus leading/trailing whitespace. register_client.py persists the RAW
    # redirect_uris, so without this check we would validate string A and store string
    # B — e.g. "http://local\thost:53821/oauth/callback" validates as localhost.
    #
    # Not a redirect-hijack vector: stripping only REMOVES characters, so it cannot turn
    # evil.com into localhost, and every downstream layer (urlsplit, authorize's
    # _normalize_redirect_uri, WHATWG browsers) strips identically — so DCR and
    # authorize still agree. It is a validate/persist integrity defect: any future
    # consumer of client.redirect_uris that does NOT strip identically inherits the
    # divergence.
    #
    # Round-trip rather than blacklisting specific characters: it closes the class.
    # Verified against every accepted URI in the §6.3 contract, including
    # "http://LOCALHOST:6274/oauth/callback" (urlunsplit preserves netloc case) and
    # "http://localhost:/oauth/callback" (empty port) — zero false positives.
    #
    # Deliberately scoped to the loopback branch. Non-loopback entries are already immune
    # because they are exact string matches — a tab-injected https://claude.ai/... simply
    # fails equality. Keeping it here preserves §6.4 and §10 by construction. The
    # allowlist PREFIX rule has the same defect and is pre-existing: backlog item 15,
    # ChatGPT path, two published apps — not touched here.
    if urlunsplit(parts) != uri:
        return False

    if parts.scheme != "http":
        return False

    # hostname is the parser's normalized form: lowercased, and for IPv6 the brackets
    # of "http://[::1]:41234/callback" are stripped — comparing against "[::1]" would
    # silently reject every IPv6 loopback.
    hostname = parts.hostname
    if hostname is None or hostname not in _LOOPBACK_HOSTS:
        return False

    # Accessing .port raises ValueError on a non-numeric or out-of-range port
    # (":abc", ":99999"). Catch it here so it becomes a rejection, not a 500.
    try:
        port = parts.port
    except ValueError:
        return False

    # Port 0 is rejected. Compared against None explicitly: `not port` would conflate
    # port 0 with "port absent".
    if port is not None and port == 0:
        return False

    if parts.path not in _LOOPBACK_PATHS:
        return False

    if parts.query or parts.fragment:
        return False

    if parts.username is not None or parts.password is not None:
        return False

    return True


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
    - RFC 8252 loopback URIs are additionally accepted on any port, under the narrow
      constraints in _is_loopback_redirect_uri (Claude Code / MCP Inspector bind an
      ephemeral port, so a fixed-port allowlist entry cannot serve them)
    - When allowlist is None (legacy mode), only HTTPS check is performed

    NOTE — this is the DCR layer, answering "may anyone register this URI?". It is a
    platform allowlist and is deliberately NOT the exact-match layer. Authorization-time
    matching against the specific client's own registered URIs stays exact
    (authorize.py:528-532) and is untouched by this function.

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
            # RFC 8252 loopback: accepted on any port, independent of the allowlist.
            # Additive — every non-loopback URI still takes the allowlist path below
            # with its semantics unchanged.
            if _is_loopback_redirect_uri(uri):
                return True

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
