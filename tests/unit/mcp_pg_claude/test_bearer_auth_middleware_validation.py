"""
A22 deployment gate — BearerAuthMiddleware validates tokens, not just header presence.

The defect this guards against: the middleware tested for the PRESENCE of an
Authorization header. An expired token carries one, so it passed the gate, reached
tool dispatch, and returned CallToolResult(isError=True) — an HTTP 200. Claude does
not honour a WWW-Authenticate header on a 200, so no token refresh was triggered.

Per sources_raw/lazy-authentication.raw.md, the check must happen "before the
JSON-RPC message reaches the MCP SDK. Once a tool handler is running, its return
value is already destined to be wrapped in a 200 response." These tests therefore
assert on the ASGI response the middleware emits, and on whether the inner app was
reached at all — not on any tool result.

Signing pattern follows tests/unit/mcp_priority_guardian/test_bearer_auth_middleware.py.

SCOPE OF PROOF — read before trusting a pass. These tests sign with a locally
generated RSA key and inject the public JWK by patching the module's _jwks_cache.
They prove the middleware CALLS validation and ACTS on its result. They do NOT
prove production JWKS resolution against the real issuer: no network fetch, no real
key rotation, no real issuer/audience pairing is exercised here. A22-4 on host
covers that; this file does not.
"""

import base64
import time
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
import jwt as pyjwt
from jwt import PyJWK
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from mcp_server.priority_guardian_claude.server_dupl import BearerAuthMiddleware


# =============================================================================
# JWT signing helpers
# =============================================================================

def _int_to_base64url(n: int, length: int) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode("ascii")


def _keypair(kid: str):
    """Generate an RSA keypair plus the matching public JWK."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    numbers = private_key.public_key().public_numbers()
    jwk = PyJWK.from_dict({
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _int_to_base64url(numbers.n, 256),
        "e": _int_to_base64url(numbers.e, 3),
    })
    return private_pem, jwk


# The key the server trusts, and an ATTACKER key it does not. Same kid on both:
# that is what makes class 3 a signature failure rather than an unknown-kid failure.
_TRUSTED_PEM, _TRUSTED_JWK = _keypair("test-key-id")
_ATTACKER_PEM, _ = _keypair("test-key-id")

# Sign with the REAL configured issuer/audience rather than patching them. The
# issuer/audience checks then run for real; only the signing key is substituted.
from mcp_server.priority_guardian_claude.mcp_auth_dupl import PG_ISSUER, PG_AUDIENCE

_ISS = PG_ISSUER
_AUD = PG_AUDIENCE


def _make_token(exp_offset_seconds: int = 300, pem: bytes = _TRUSTED_PEM) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {
            "iss": _ISS,
            "aud": _AUD,
            "sub": "test-user-123",
            "scope": "pg.access",
            "jti": "test-jti-456",
            "iat": now - 600,
            "nbf": now - 600,
            "exp": now + exp_offset_seconds,
        },
        pem,
        algorithm="RS256",
        headers={"kid": "test-key-id"},
    )


@pytest.fixture
def trusted_jwks():
    """Serve the trusted public key; no network."""
    with patch("mcp_server.priority_guardian_claude.mcp_auth_dupl._jwks_cache") as cache:
        cache.fetch_jwks = AsyncMock(return_value=None)
        cache.get_signing_key = MagicMock(return_value=_TRUSTED_JWK)
        yield cache


@pytest.fixture
def jwks_unavailable():
    """JWKS fetch fails with no usable cache — what fetch_jwks raises when its
    stale-cache fallback is exhausted. Not a token problem."""
    with patch("mcp_server.priority_guardian_claude.mcp_auth_dupl._jwks_cache") as cache:
        cache.fetch_jwks = AsyncMock(
            side_effect=Exception("JWKS fetch failed and no valid cache available: timeout")
        )
        yield cache


# =============================================================================
# ASGI harness
# =============================================================================

WWW_AUTH = 'Bearer resource_metadata="https://example.test/.well-known/oauth-protected-resource/mcp", scope="pg.access"'


def _scope(headers=None, path="/mcp", method="POST"):
    return {"type": "http", "method": method, "path": path, "headers": headers or []}


def _receive_jsonrpc():
    """A well-formed MCP JSON-RPC body. A22-1's admit half needs this: a malformed
    body would fail downstream for an unrelated reason and could be misread as a pass."""
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
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    @property
    def status(self):
        return self.messages[0]["status"]

    @property
    def headers(self):
        return {k.decode().lower(): v.decode() for k, v in self.messages[0]["headers"]}

    @property
    def body(self):
        return b"".join(m.get("body", b"") for m in self.messages if m["type"] == "http.response.body")


async def _run(headers):
    cap = Captured()
    mw = BearerAuthMiddleware(cap.inner_app, WWW_AUTH)
    await mw(_scope(headers), _receive_jsonrpc(), cap.send)
    return cap


def _bearer(token: str):
    return [(b"authorization", f"Bearer {token}".encode())]


# =============================================================================
# A22-1 — DEPLOYMENT GATE
# =============================================================================

@pytest.mark.asyncio
async def test_a22_1_reject_expired_token(trusted_jwks):
    """Reject half. The routine case: a correctly signed token that has expired."""
    cap = await _run(_bearer(_make_token(exp_offset_seconds=-3600)))

    assert cap.status == 401
    assert cap.headers.get("www-authenticate") == WWW_AUTH
    assert cap.headers.get("cache-control") == "no-store"
    # The defect was precisely a 200 carrying a tool error.
    assert cap.status != 200
    assert not cap.inner_called, "expired token reached the MCP SDK"


@pytest.mark.asyncio
async def test_a22_1_admit_valid_token(trusted_jwks):
    """Admit half. A valid token with a well-formed JSON-RPC body must not be
    rejected BY THIS MIDDLEWARE. Asserted as 'inner app reached', which isolates
    the middleware from everything below it."""
    cap = await _run(_bearer(_make_token(exp_offset_seconds=3600)))

    assert cap.inner_called, "valid token was blocked before reaching the inner app"
    assert cap.status != 401


# =============================================================================
# A22-2 — absent header unchanged
# =============================================================================

@pytest.mark.asyncio
async def test_a22_2_absent_header_unchanged():
    """The path that makes connector creation work. No JWKS fixture: validation
    must not even be attempted, so an unmocked cache proves the branch is untouched."""
    cap = await _run([])

    assert cap.status == 401
    assert cap.headers.get("www-authenticate") == WWW_AUTH
    assert cap.headers.get("cache-control") == "no-store"
    assert b"Bearer token required" in cap.body
    assert not cap.inner_called


# =============================================================================
# A22-3 — malformed headers, three classes, each separately
# =============================================================================

@pytest.mark.asyncio
async def test_a22_3_class1_wrong_scheme():
    """Class 1: wrong auth scheme."""
    cap = await _run([(b"authorization", b"Basic dXNlcjpwYXNzd29yZA==")])

    assert cap.status == 401
    assert cap.status != 500
    assert cap.headers.get("www-authenticate") == WWW_AUTH
    assert not cap.inner_called
    # No credential material echoed back.
    assert b"dXNlcjpwYXNzd29yZA" not in cap.body


@pytest.mark.asyncio
async def test_a22_3_class2_bearer_no_token():
    """Class 2: 'Bearer' with nothing after it."""
    for raw in (b"Bearer", b"Bearer ", b"Bearer   "):
        cap = Captured()
        mw = BearerAuthMiddleware(cap.inner_app, WWW_AUTH)
        await mw(_scope([(b"authorization", raw)]), _receive_jsonrpc(), cap.send)

        assert cap.status == 401, f"{raw!r} did not yield 401"
        assert cap.status != 500
        assert not cap.inner_called


@pytest.mark.asyncio
async def test_a22_3_class3_cryptographically_invalid(trusted_jwks):
    """Class 3: syntactically valid JWT, signed by a key the server does not trust.
    The class most likely to surface an exception out of validate_jwt — an unhandled
    one would be Starlette's 500, which is what this gate exists to prevent."""
    token = _make_token(exp_offset_seconds=3600, pem=_ATTACKER_PEM)
    cap = await _run(_bearer(token))

    assert cap.status == 401
    assert cap.status != 500
    assert cap.headers.get("www-authenticate") == WWW_AUTH
    assert cap.headers.get("cache-control") == "no-store"
    assert not cap.inner_called
    # No token contents or internal detail in the body.
    assert token.encode() not in cap.body
    for leak in (b"signature", b"Traceback", b"kid", b"test-user-123"):
        assert leak not in cap.body, f"response body leaks {leak!r}"


@pytest.mark.asyncio
async def test_a22_3_garbage_token_is_401_not_500(trusted_jwks):
    """Not a JWT at all — get_unverified_header raises DecodeError, an
    InvalidTokenError subclass, so it must land in the 401 branch."""
    cap = await _run(_bearer("not-a-jwt-at-all"))

    assert cap.status == 401
    assert not cap.inner_called


# =============================================================================
# Server-fault split — 503, deliberately not 401
# =============================================================================

@pytest.mark.asyncio
async def test_jwks_unavailable_is_503_not_401(jwks_unavailable):
    """A token problem and a server problem are different answers.

    401 here would tell Claude to re-authenticate against a server that cannot
    validate anything — a re-auth loop rather than a recovery. 500 is also wrong:
    this is a known, named, transient condition. No WWW-Authenticate, because
    there is nothing for the client to re-auth against."""
    cap = await _run(_bearer(_make_token(exp_offset_seconds=3600)))

    assert cap.status == 503
    assert cap.status not in (401, 500)
    assert "www-authenticate" not in cap.headers
    assert cap.headers.get("cache-control") == "no-store"
    assert not cap.inner_called
    assert b"timeout" not in cap.body, "internal fetch detail leaked to the client"


# =============================================================================
# Non-/mcp paths must be unaffected
# =============================================================================

@pytest.mark.asyncio
async def test_discovery_paths_not_gated():
    """OAuth discovery must stay reachable unauthenticated or the connector can
    never be added in the first place."""
    for path in (
        "/.well-known/oauth-protected-resource/mcp",
        "/.well-known/oauth-authorization-server",
        "/health",
    ):
        cap = Captured()
        mw = BearerAuthMiddleware(cap.inner_app, WWW_AUTH)
        await mw(_scope([], path=path), _receive_jsonrpc(), cap.send)

        assert cap.inner_called, f"{path} was gated by BearerAuthMiddleware"
