"""
A22 deployment gate (MindSort-Claude) — BearerAuthMiddleware validates tokens,
not merely header presence.

THE DEFECT THIS GUARDS AGAINST. The middleware tested only that an Authorization
header EXISTED. An expired token carries one, so it passed the gate, reached tool
dispatch, and came back as CallToolResult(isError=True) — an HTTP 200. Claude does
not honour a WWW-Authenticate header on a 200, so no re-auth was triggered and the
user saw "Authentication required. Please connect your account." as model text with
no Connect button. Token expiry mid-session is routine, not an edge case.

It also left tools/list entirely unauthenticated: `_list_tools` never calls
authenticate_request, so before this change ANY non-empty bearer returned the full
tool catalogue at 200. Verified live against production before the fix:

    curl -H "Authorization: Bearer not-a-real-token" .../mcp  -> 200 + full catalogue

The check must happen before the JSON-RPC message reaches the MCP SDK — once a tool
handler is running, its return value is already destined to be wrapped in a 200. So
these tests assert on the ASGI response the middleware emits and on whether the inner
app was reached at all, never on a tool result.

Harness mirrors tests/unit/mcp_pg_claude/test_bearer_auth_middleware_validation.py.

SCOPE OF PROOF — read before trusting a pass. These sign with a locally generated
RSA key and inject the public JWK by patching the shared module's _jwks_cache. They
prove the middleware CALLS validation and ACTS on its result. They do NOT prove
production JWKS resolution against the real issuer: no network fetch, no real key
rotation, no real issuer/audience pairing is exercised. The post-deploy valid-token
admission gate covers that; this file does not.

NOTE ON WHICH VALIDATOR IS EXERCISED: MindSort's middleware calls the SHARED
clarity.mcp_auth.validate_jwt (re-exported through mcp_auth_dupl), not PG's local
copy — one validator per app, the same one dispatch already uses. The two have
drifted on `azp` handling. These tests therefore patch the SHARED module's cache.
"""

import base64
import time
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
import jwt as pyjwt
from jwt import PyJWK
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from mcp_server.mindsort_claude.server_dupl import BearerAuthMiddleware


# =============================================================================
# JWT signing helpers
# =============================================================================

def _int_to_base64url(n: int, length: int) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode("ascii")


def _keypair(kid: str):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    numbers = private_key.public_key().public_numbers()
    jwk = PyJWK.from_dict({
        "kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256",
        "n": _int_to_base64url(numbers.n, 256),
        "e": _int_to_base64url(numbers.e, 3),
    })
    return private_pem, jwk


# Trusted key, plus an ATTACKER key sharing the SAME kid — that is what makes the
# bad-signature case a signature failure rather than an unknown-kid failure.
_TRUSTED_PEM, _TRUSTED_JWK = _keypair("test-key-id")
_ATTACKER_PEM, _ = _keypair("test-key-id")
_, _UNKNOWN_JWK = _keypair("some-other-kid")

# Sign with the REAL configured issuer/audience rather than patching them, so the
# issuer and audience checks run for real; only the signing key is substituted.
from mcp_server.mindsort_claude.mcp_auth_dupl import CLARITY_ISSUER, MCP_RESOURCE_URL

_ISS = CLARITY_ISSUER
_AUD = MCP_RESOURCE_URL


def _make_token(exp_offset_seconds: int = 300, pem: bytes = _TRUSTED_PEM,
                iss: str = None, aud: str = None, kid: str = "test-key-id") -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": iss or _ISS,
            "aud": aud or _AUD,
            "sub": "test-user-123",
            "scope": "clarity.write",
            "jti": "test-jti-456",
            "iat": now - 600,
            "nbf": now - 600,
            "exp": now + exp_offset_seconds,
        },
        pem, algorithm="RS256", headers={"kid": kid},
    )


@pytest.fixture
def trusted_jwks():
    """Serve the trusted public key; no network. Patches the SHARED module."""
    with patch("mcp_server.clarity.mcp_auth._jwks_cache") as cache:
        cache.fetch_jwks = AsyncMock(return_value=None)
        cache.get_signing_key = MagicMock(return_value=_TRUSTED_JWK)
        yield cache


@pytest.fixture
def jwks_unavailable():
    """JWKS fetch fails with no usable cache — what fetch_jwks raises once its
    stale-cache fallback is exhausted. A SERVER problem, not a token problem."""
    with patch("mcp_server.clarity.mcp_auth._jwks_cache") as cache:
        cache.fetch_jwks = AsyncMock(
            side_effect=Exception("JWKS fetch failed and no valid cache available: timeout")
        )
        cache.get_signing_key = MagicMock(
            side_effect=Exception("JWKS fetch failed and no valid cache available: timeout")
        )
        yield cache


# =============================================================================
# ASGI harness
# =============================================================================

WWW_AUTH = ('Bearer resource_metadata="https://mindsort-mcp.priority-guard.com'
            '/.well-known/oauth-protected-resource/mcp", scope="clarity.write"')


def _scope(headers=None, path="/mcp", method="POST"):
    return {"type": "http", "method": method, "path": path, "headers": headers or []}


def _receive_jsonrpc():
    """A well-formed tools/list body. The admit-half of these tests needs this: a
    malformed body would fail downstream for an unrelated reason and could be
    misread as a pass."""
    body = b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


class Captured:
    """Captures the ASGI response and whether the inner app was reached."""

    def __init__(self):
        self.messages = []
        self.inner_called = False

    async def send(self, message):
        self.messages.append(message)

    async def inner_app(self, scope, receive, send):
        self.inner_called = True
        # Stands in for the tool catalogue the real inner app would return.
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body",
                    "body": b'{"result":{"tools":[{"name":"organize_thoughts"}]}}'})

    @property
    def status(self):
        return self.messages[0]["status"]

    @property
    def headers(self):
        return {k.decode().lower(): v.decode() for k, v in self.messages[0]["headers"]}

    @property
    def body(self):
        return b"".join(m.get("body", b"") for m in self.messages if m["type"] == "http.response.body")


async def _run(headers, method="POST"):
    cap = Captured()
    mw = BearerAuthMiddleware(cap.inner_app, WWW_AUTH)
    await mw(_scope(headers, method=method), _receive_jsonrpc(), cap.send)
    return cap


def _bearer(token: str):
    return [(b"authorization", f"Bearer {token}".encode())]


# =============================================================================
# The defect itself
# =============================================================================

@pytest.mark.asyncio
async def test_expired_token_gets_401_with_challenge_and_never_reaches_dispatch(trusted_jwks):
    """THE A22 DEFECT. An expired token carries a header, so the presence-only gate
    admitted it. Asserting 'not 200' alone would be a weak test — Claude needs the
    WWW-Authenticate header to re-auth, so the header is asserted too."""
    cap = await _run(_bearer(_make_token(exp_offset_seconds=-60)))

    assert cap.status == 401
    assert cap.headers["www-authenticate"] == WWW_AUTH
    assert cap.inner_called is False


@pytest.mark.asyncio
async def test_invalid_token_on_tools_list_returns_401_and_no_catalogue(trusted_jwks):
    """DISCRIMINATING TEST. tools/list is not dispatched through
    authenticate_request, so before this fix ANY non-empty bearer returned the full
    tool catalogue at 200 — verified live against production. This proves validation
    covers request classes that never reach tool dispatch."""
    cap = await _run(_bearer("not-a-real-token"))

    assert cap.status == 401
    assert cap.headers["www-authenticate"] == WWW_AUTH
    assert cap.inner_called is False, "listing logic must not be reached"
    assert b"organize_thoughts" not in cap.body, "tool catalogue must not leak"


# =============================================================================
# Every malformed-credential class is a 401, never a 500
# =============================================================================

@pytest.mark.asyncio
async def test_bad_signature_is_401(trusted_jwks):
    """Same kid, attacker key — a signature failure, not an unknown-kid failure."""
    cap = await _run(_bearer(_make_token(pem=_ATTACKER_PEM)))
    assert cap.status == 401
    assert cap.inner_called is False


@pytest.mark.asyncio
async def test_wrong_issuer_is_401(trusted_jwks):
    cap = await _run(_bearer(_make_token(iss="https://evil.example/oauth")))
    assert cap.status == 401
    assert cap.inner_called is False


@pytest.mark.asyncio
async def test_wrong_audience_is_401(trusted_jwks):
    cap = await _run(_bearer(_make_token(aud="https://not-this-resource.example/mcp")))
    assert cap.status == 401
    assert cap.inner_called is False


@pytest.mark.asyncio
async def test_unknown_kid_is_401(trusted_jwks):
    trusted_jwks.get_signing_key = MagicMock(side_effect=pyjwt.PyJWTError("Unknown kid"))
    cap = await _run(_bearer(_make_token(kid="never-seen-kid")))
    assert cap.status == 401
    assert cap.inner_called is False


@pytest.mark.asyncio
async def test_absent_header_is_401_preserved():
    """Pre-existing behaviour, must not regress: this is what lets Claude discover
    the AS and start DCR on first connect."""
    cap = await _run([])
    assert cap.status == 401
    assert cap.headers["www-authenticate"] == WWW_AUTH
    assert cap.inner_called is False


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [b"Bearer", b"Bearer ", b"Basic abc123", b"token-with-no-scheme"])
async def test_malformed_header_is_401_never_500(raw):
    """Wrong scheme or Bearer-with-nothing-after. Must be a 401, and must NOT raise."""
    cap = await _run([(b"authorization", raw)])
    assert cap.status == 401
    assert cap.inner_called is False


@pytest.mark.asyncio
async def test_duplicate_authorization_headers_is_401(trusted_jwks):
    """Two credentials on one request is ambiguous. Rejected rather than resolved —
    picking a winner would preserve the ambiguity that enables request smuggling.
    401 not 400: only a 401 carrying the challenge makes Claude re-authenticate."""
    good = _make_token()
    cap = await _run([
        (b"authorization", f"Bearer {good}".encode()),
        (b"authorization", b"Bearer second-token"),
    ])
    assert cap.status == 401
    assert cap.headers["www-authenticate"] == WWW_AUTH
    assert cap.inner_called is False


# =============================================================================
# Server-side failure is NOT an auth failure
# =============================================================================

@pytest.mark.asyncio
async def test_jwks_unavailable_is_503_with_no_challenge(jwks_unavailable):
    """503, deliberately not 401. A 401 would tell Claude to re-authenticate against
    a server that cannot validate anything — a re-auth loop, not a recovery. And no
    WWW-Authenticate: there is nothing to re-auth against."""
    cap = await _run(_bearer(_make_token()))

    assert cap.status == 503
    assert "www-authenticate" not in cap.headers
    assert cap.inner_called is False


# =============================================================================
# The admit half — the failure mode of an over-eager gate
# =============================================================================

@pytest.mark.asyncio
async def test_valid_token_passes_through_unchanged(trusted_jwks):
    """The gate must not reject good tokens. This is the unit-level counterpart of
    the post-deploy valid-token admission gate."""
    cap = await _run(_bearer(_make_token()))

    assert cap.inner_called is True
    assert cap.status == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
async def test_valid_token_passes_on_every_guarded_method(trusted_jwks, method):
    """FastMCP streamable HTTP uses GET (SSE), POST (messages) and DELETE (session
    close). All three are guarded, so all three must admit a valid token."""
    cap = await _run(_bearer(_make_token()), method=method)
    assert cap.inner_called is True


@pytest.mark.asyncio
async def test_non_mcp_path_is_not_guarded(trusted_jwks):
    """Only /mcp is protected — health and discovery must stay reachable."""
    cap = Captured()
    mw = BearerAuthMiddleware(cap.inner_app, WWW_AUTH)
    await mw(_scope([], path="/health", method="GET"), _receive_jsonrpc(), cap.send)
    assert cap.inner_called is True


# =============================================================================
# Wire details Claude depends on
# =============================================================================

@pytest.mark.asyncio
async def test_challenge_responses_set_cache_control_no_store(trusted_jwks):
    """A cached 401 would strand a client that has since re-authenticated."""
    for headers in ([], _bearer("garbage"), _bearer(_make_token(exp_offset_seconds=-60))):
        cap = await _run(headers)
        assert cap.status == 401
        assert cap.headers["cache-control"] == "no-store"


# =============================================================================
# CI GUARD — the insufficient-scope unreachability invariant
# =============================================================================
# A22 has two limbs: 401 for authentication failure, and 403 with
# error="insufficient_scope" for authorization failure. This increment fixes the
# 401 limb at the HTTP boundary. The 403 limb is NOT fixed — insufficient-scope
# still returns a dispatcher-level 200 + isError, which would NOT satisfy A22.
#
# That is acceptable ONLY because the condition is currently unreachable: every
# advertised tool requires the single scope the OAuth flow grants, so a token that
# authenticates always carries sufficient scope. These tests pin that premise. If
# a differentiated scope is ever introduced, they fail loudly and force A22's
# authorization limb to be revisited rather than silently becoming reachable.
#
# Iterates the ADVERTISED set, not all of TOOL_SCOPES — the map still carries a
# `save_board` tombstone for a tool deleted in the auto-persist migration, which is
# not advertised and would false-fire.

def test_every_advertised_tool_requires_only_the_single_granted_scope():
    from mcp_server.mindsort_claude.tools_list_dupl import CLAUDE_ADVERTISED_TOOLS
    from mcp_server.mindsort_claude.config import TOOL_SCOPES

    for tool in sorted(CLAUDE_ADVERTISED_TOOLS):
        assert tool in TOOL_SCOPES, f"advertised but unauthorized: {tool}"
        assert TOOL_SCOPES[tool] == ["clarity.write"], (
            f"{tool} requires {TOOL_SCOPES[tool]}, not ['clarity.write'] — "
            "insufficient-scope is now REACHABLE and A22's 403 limb must be fixed: "
            "dispatcher-level 200+isError does not satisfy it."
        )


def test_oauth_flow_grants_exactly_the_scope_the_tools_require():
    """If SCOPES_SUPPORTED grows, a token can authenticate while lacking the scope a
    tool needs — making the unfixed 403 limb reachable."""
    from mcp_server.mindsort_claude.config import SCOPES_SUPPORTED

    assert SCOPES_SUPPORTED == ["clarity.write"], (
        f"SCOPES_SUPPORTED is {SCOPES_SUPPORTED} — differentiated scopes make "
        "insufficient-scope reachable; revisit A22's authorization limb."
    )


# =============================================================================
# ASSEMBLED-STACK tests — the gap that let a divergence through 21 green tests
# =============================================================================
# Every test above drives BearerAuthMiddleware ALONE. That is why none of them
# caught that the downstream MCPContentTypeAndAcceptFixMiddleware captured the
# Authorization header with its own inline `name == b"authorization"` +
# value.decode("utf-8") — diverging from the gate's select_authorization_header
# (case-insensitive, latin-1) on two axes.
#
# PG-Claude's A22a comment records this exact divergence as the reason one selector
# must serve both layers: "The gate decoded latin-1, the other utf-8 ... a 500 where
# a 401 is required." These tests drive the REAL stack in its real order
# (BearerAuth wraps ContentType wraps app) so the layers are exercised together.

from mcp_server.mindsort_claude.server_dupl import MCPContentTypeAndAcceptFixMiddleware
from mcp_server.clarity.request_context import auth_header_var


async def _run_stack(headers, method="POST"):
    """Real order: BearerAuthMiddleware(MCPContentTypeAndAcceptFixMiddleware(app))."""
    cap = Captured()
    inner = MCPContentTypeAndAcceptFixMiddleware(cap.inner_app, auth_header_var)
    mw = BearerAuthMiddleware(inner, WWW_AUTH)
    await mw(_scope(headers, method=method), _receive_jsonrpc(), cap.send)
    return cap


@pytest.mark.asyncio
async def test_non_utf8_authorization_header_is_401_not_500_through_full_stack():
    """A non-UTF-8 byte must never produce a 500. The gate latin-1 decodes it, then
    validation rejects it (a byte >= 0x80 cannot appear in a base64url JWT), so it
    401s before the capture layer — and the capture layer no longer has a utf-8
    decode that could raise even if it were reached."""
    cap = await _run_stack([(b"authorization", b"Bearer caf\xe9")])

    assert cap.status == 401
    assert cap.inner_called is False


@pytest.mark.asyncio
async def test_capture_layer_sees_the_same_header_the_gate_admitted(trusted_jwks):
    """The divergence with a REAL consequence: if the capture missed a header the
    gate admitted, auth_header_var would be unset and dispatch would answer
    200+isError for a user with a VALID token — the exact A22 failure.

    Observed from INSIDE the request. The capture sets the ContextVar and resets it
    in a `finally`, so reading it after the response has completed correctly yields
    None — asserting on it there would test the teardown, not the capture."""
    token = _make_token()
    seen = {}

    async def observing_app(scope, receive, send):
        seen["auth_header"] = auth_header_var.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    cap = Captured()
    inner = MCPContentTypeAndAcceptFixMiddleware(observing_app, auth_header_var)
    mw = BearerAuthMiddleware(inner, WWW_AUTH)
    await mw(_scope(_bearer(token)), _receive_jsonrpc(), cap.send)

    assert cap.status == 200, "valid token must reach the app"
    assert seen["auth_header"] == f"Bearer {token}", (
        "the capture layer lost, or altered, a header the gate admitted"
    )


@pytest.mark.asyncio
async def test_capture_is_case_insensitive_like_the_gate(trusted_jwks):
    """DISCRIMINATING for the case axis — fails against the pre-fix inline capture.

    The gate matches `name.lower() == b"authorization"`; the old capture matched
    `name == b"authorization"` exactly. A capitalised `Authorization` header would
    therefore be ADMITTED by the gate and MISSED by the capture, leaving
    auth_header_var unset — so dispatch would raise UnauthorizedError and answer
    200+isError for a user with a perfectly VALID token. That is the exact A22
    failure this increment exists to remove, arriving one layer further down.

    ASGI servers lowercase header names, so this is not reachable through uvicorn
    today. It is tested anyway because "cannot happen" is precisely how PG's first
    selector divergence survived — and a masked defect is not an absent one.
    """
    token = _make_token()
    seen = {}

    async def observing_app(scope, receive, send):
        seen["auth_header"] = auth_header_var.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    cap = Captured()
    inner = MCPContentTypeAndAcceptFixMiddleware(observing_app, auth_header_var)
    mw = BearerAuthMiddleware(inner, WWW_AUTH)
    # Capital 'A' — what the old inline `name == b"authorization"` would miss.
    headers = [(b"Authorization", f"Bearer {token}".encode())]
    await mw(_scope(headers), _receive_jsonrpc(), cap.send)

    assert cap.status == 200, "gate must admit a valid token regardless of header case"
    assert seen["auth_header"] == f"Bearer {token}", (
        "capture missed a header the gate admitted — the layers disagree on case"
    )
