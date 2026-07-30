"""
RFC 8252 loopback redirect URI support at DCR (Part B).

Claude Code and MCP Inspector bind an EPHEMERAL port for their OAuth callback, so a
fixed-port allowlist entry cannot serve them. Before this change, DCR accepted loopback
only on the two hardcoded port-6274 entries; a reviewer testing the production server
on any other port failed at registration.

Two layers are deliberately distinct and both are asserted here:
  DCR       "may anyone register this URI?"  -> platform allowlist + loopback rule
  authorize "does it match what THIS client  -> exact match, unchanged by Part B
             registered?"

Every test states the bug that would still pass it.
"""

import pytest

from backend.core.config import Settings
from backend.core.oauth_provider.validators.client_metadata import (
    validate_redirect_uris,
    _is_loopback_redirect_uri,
)
from backend.core.oauth_provider.authorize import _normalize_redirect_uri


# The production allowlist, derived — never hand-copied. A hardcoded fixture would stay
# green while someone deleted the OpenAI reviewer callback from the real list.
PRODUCTION_ALLOWLIST = list(Settings._CHATGPT_REDIRECT_URIS)


def _accepts(uri: str) -> bool:
    valid, _ = validate_redirect_uris([uri], allowed_uris=PRODUCTION_ALLOWLIST)
    return valid


# ============================================================================
# §6.3 contract — one assertion per row
# ============================================================================

ACCEPTED = [
    "http://localhost:6274/oauth/callback",
    "http://localhost:53821/oauth/callback",
    "http://127.0.0.1:9999/oauth/callback/debug",
    "http://localhost/callback",
    "http://LOCALHOST:6274/oauth/callback",
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
    "https://chatgpt.com/connector/oauth/ABC123",
    "https://chatgpt.com/connector_platform_oauth_redirect",
    "https://platform.openai.com/apps-manage/oauth",
]

REJECTED = [
    "http://localhost.evil.com:8080/oauth/callback",
    "http://127.0.0.1.evil.com/callback",
    "http://evil.com/oauth/callback",
    "https://localhost:6274/oauth/callback",
    "http://localhost:6274/evil",
    "http://localhost:6274/oauth/callback?x=1",
    "http://localhost:6274/oauth/callback#f",
    "http://user:pw@localhost:6274/oauth/callback",
    "http://localhost:abc/oauth/callback",
    "http://localhost:99999/oauth/callback",
    "http://localhost:0/oauth/callback",
    "http://[::1]:41234/callback",
]


@pytest.mark.parametrize("uri", ACCEPTED)
def test_contract_accepts(uri):
    """
    Bug this catches: an ephemeral-port loopback URI rejected at DCR — the defect Part B
    exists to fix, observed in production on 2026-07-30 as HTTP 400
    "redirect_uri not in allowlist" — or a widening that breaks an existing platform
    callback.
    """
    assert _accepts(uri), f"{uri} must be accepted at DCR"


@pytest.mark.parametrize("uri", REJECTED)
def test_contract_rejects(uri):
    """
    Bug this catches: the loopback rule matching by substring/prefix instead of on the
    parsed hostname, which would accept attacker-controlled hosts like
    localhost.evil.com; or accepting https/query/fragment/userinfo variants that the
    narrow rule must exclude.
    """
    assert not _accepts(uri), f"{uri} must be rejected at DCR"


# ============================================================================
# Parser hazards — §6.2
# ============================================================================

@pytest.mark.parametrize("uri", [
    "http://localhost:abc/oauth/callback",
    "http://localhost:99999/oauth/callback",
    "http://localhost:-1/oauth/callback",
])
def test_malformed_port_rejects_without_raising(uri):
    """
    Bug this catches: urlsplit(...).port raises ValueError on a non-numeric or
    out-of-range port. Unhandled, a malformed DCR request becomes an HTTP 500 instead of
    a clean 400 — an availability and error-contract defect, not just a validation one.
    """
    try:
        valid, _ = validate_redirect_uris([uri], allowed_uris=PRODUCTION_ALLOWLIST)
    except Exception as exc:  # noqa: BLE001 — the point of the test
        pytest.fail(f"{uri} raised {type(exc).__name__} instead of rejecting: {exc}")
    assert valid is False


def test_empty_port_is_accepted_and_both_layers_agree():
    """
    An EMPTY port ("http://localhost:/callback") is not malformed — RFC 3986 permits an
    empty port component and urlsplit reports port=None. Accepted here, and authorize
    normalizes it too, so the layers agree.

    Bug this catches: "hardening" the port rule to reject an empty port — a FALSE
    NEGATIVE that would block a legitimate client for no security gain. (Note the
    asymmetry: DCR being NARROWER than authorize is always safe, since nothing
    unregistered can match at authorize. The ::1 case was dangerous because DCR was
    WIDER. This case is the opposite direction, so the cost is usability, not a
    register-but-cannot-authorize client.)
    """
    uri = "http://localhost:/oauth/callback"
    assert _accepts(uri) is True
    assert _normalize_redirect_uri(uri) is not None


def test_port_zero_is_not_conflated_with_absent_port():
    """
    Bug this catches: testing the parsed port with `if not port`, which treats port 0 as
    "no port supplied" and silently accepts http://localhost:0/... — the classic falsy
    conflation this rule is written to avoid.
    """
    assert _is_loopback_redirect_uri("http://localhost/callback") is True
    assert _is_loopback_redirect_uri("http://localhost:0/callback") is False


def test_ipv6_loopback_is_excluded_deliberately():
    """
    Bug this catches: re-adding ::1 to the DCR loopback rule. authorize.py's
    _normalize_redirect_uri strips ports with netloc.split(":")[0], which is IPv4-only
    and yields "[" for "[::1]:41234" — so an accepted ::1 URI could be REGISTERED but
    never authorized, producing a client that fails later wearing a different error.
    DCR and authorize must agree; this asserts they do, in the rejecting direction.
    """
    uri = "http://[::1]:41234/callback"
    assert _accepts(uri) is False
    assert _normalize_redirect_uri(uri) is None


# ============================================================================
# Non-regression — §6.4 and §13
# ============================================================================

def test_production_allowlist_is_unchanged():
    """
    Bug this catches: silent removal of a platform callback from the production
    allowlist — most damagingly https://platform.openai.com/apps-manage/oauth, the
    OpenAI reviewer callback. A hand-copied fixture would stay green through exactly
    that deletion; this asserts against the real list.
    """
    assert PRODUCTION_ALLOWLIST == [
        "https://chatgpt.com/connector/oauth/",
        "https://chatgpt.com/connector_platform_oauth_redirect",
        "https://platform.openai.com/apps-manage/oauth",
        "https://claude.ai/api/mcp/auth_callback",
        "https://claude.com/api/mcp/auth_callback",
        "http://localhost:6274/oauth/callback",
        "http://localhost:6274/oauth/callback/debug",
    ]


def test_chatgpt_prefix_semantics_preserved():
    """
    Bug this catches: converting the trailing-slash prefix entry to an exact match,
    which would break ChatGPT Dynamic Client Registration for every new connector on two
    published live apps (Unpack v2.0, Priority Guardian V1.0) — the §0.2 trap.
    """
    assert _accepts("https://chatgpt.com/connector/oauth/ABC123")
    assert _accepts("https://chatgpt.com/connector/oauth/xyz-789")
    # Prefix must not degrade into substring matching on another host
    assert not _accepts("https://evil.com/https://chatgpt.com/connector/oauth/A")


def test_empty_redirect_uri_list_rejected():
    """
    Bug this catches: the loopback branch being placed ahead of the emptiness check, so
    a registration with no redirect_uris at all slips through.
    """
    valid, error = validate_redirect_uris([], allowed_uris=PRODUCTION_ALLOWLIST)
    assert valid is False
    assert error == "At least one redirect_uri is required"


def test_legacy_none_allowlist_still_https_only():
    """
    Bug this catches: the loopback rule leaking into the legacy allowed_uris=None path,
    which would let plain http through wherever that mode is used. Production always
    passes the settings list (register_client.py:126), so this documents a boundary
    rather than a live path.
    """
    valid, _ = validate_redirect_uris(["http://localhost:53821/oauth/callback"], allowed_uris=None)
    assert valid is False


@pytest.mark.parametrize("uri", ACCEPTED)
def test_dcr_acceptance_implies_authorize_acceptance(uri):
    """
    Bug this catches: DCR and authorize diverging — a URI registrable but never
    authorizable, which is worse than rejecting it because the failure surfaces later
    and looks like a different defect. This is the check that caught the ::1 gap.
    """
    assert _normalize_redirect_uri(uri) is not None, (
        f"{uri} is accepted at DCR but rejected by authorize normalization"
    )
