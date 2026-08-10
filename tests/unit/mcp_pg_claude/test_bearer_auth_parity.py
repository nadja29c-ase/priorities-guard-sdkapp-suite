"""P1 — BearerAuthMiddleware parity with the OpenAI reference.

P1-a  one shared Authorization selector; duplicates rejected with 401 + challenge
P1-b  body size guard enforced ON THE STREAM, with bounded buffering and replay

VERIFICATION BOUND, STATED BECAUSE IT CANNOT BE CLOSED. P1-a's duplicate-header
behaviour can only ever be proven HERE, in process. Cloudflare returns 400 to any
request carrying two Authorization headers — isolated by controls on 2026-08-09:
single Basic -> 401, single garbage Bearer -> 401, duplicate X-Test -> 401. So the
wire probe that closed A22a is unavailable: the request never reaches the origin.
"The origin is safe independently of the edge" rests on these tests and their
negative controls, and on nothing else.

Each block carries a NEGATIVE CONTROL, because a test that cannot fail proves
nothing — the lesson from A22a, where the F1 port was checked this way and the
gate itself initially was not.
"""

import base64
import time

import pytest
import jwt as pyjwt
from jwt import PyJWK
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from unittest.mock import patch, MagicMock, AsyncMock

from mcp_server.priority_guardian_claude.server_dupl import (
    BearerAuthMiddleware,
    select_authorization_header,
    _DuplicateAuthorizationError,
)
from mcp_server.priority_guardian_claude.config import MAX_MCP_BODY_SIZE_BYTES


# --------------------------------------------------------------------------- keys
def _int_b64(n: int, ln: int) -> str:
    return base64.urlsafe_b64encode(n.to_bytes(ln, "big")).rstrip(b"=").decode()


_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_pem = _key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
_nums = _key.public_key().public_numbers()
_JWK = PyJWK.from_dict({
    "kty": "RSA", "kid": "test-key-id", "use": "sig", "alg": "RS256",
    "n": _int_b64(_nums.n, 256), "e": _int_b64(_nums.e, 3),
})

from mcp_server.priority_guardian_claude.mcp_auth_dupl import PG_ISSUER, PG_AUDIENCE


def _token(exp_offset: int = 3600) -> str:
    now = int(time.time())
    return pyjwt.encode(
        {"iss": PG_ISSUER, "aud": PG_AUDIENCE, "sub": "u1", "scope": "pg.access",
         "jti": "j1", "iat": now - 600, "nbf": now - 600, "exp": now + exp_offset},
        _pem, algorithm="RS256", headers={"kid": "test-key-id"},
    )


@pytest.fixture
def jwks():
    with patch("mcp_server.priority_guardian_claude.mcp_auth_dupl._jwks_cache") as c:
        c.fetch_jwks = AsyncMock(return_value=None)
        c.get_signing_key = MagicMock(return_value=_JWK)
        yield c


WWW_AUTH = 'Bearer resource_metadata="https://example.test/.well-known/oauth-protected-resource/mcp", scope="pg.access"'


# ----------------------------------------------------------------------- harness
class Captured:
    def __init__(self):
        self.messages = []
        self.inner_called = False
        self.body_seen = None

    async def send(self, m):
        self.messages.append(m)

    async def inner_app(self, scope, receive, send):
        """Drains the body so replay can be ASSERTED, not assumed."""
        self.inner_called = True
        chunks = []
        while True:
            msg = await receive()
            if msg["type"] != "http.request":
                break
            chunks.append(msg.get("body", b""))
            if not msg.get("more_body", False):
                break
        self.body_seen = b"".join(chunks)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    @property
    def status(self):
        return self.messages[0]["status"] if self.messages else None

    @property
    def headers(self):
        return {k.decode().lower(): v.decode() for k, v in self.messages[0]["headers"]}

    @property
    def body(self):
        return b"".join(m.get("body", b"") for m in self.messages
                        if m["type"] == "http.response.body")


def _scope(headers, method="POST"):
    return {"type": "http", "method": method, "path": "/mcp", "headers": headers}


def _receive(body: bytes, chunks: int = 1):
    """Yields `body` in `chunks` pieces, so streamed enforcement is exercised."""
    if not body:
        parts = [b""]
    else:
        size = max(1, len(body) // chunks)
        parts = [body[i:i + size] for i in range(0, len(body), size)]
    idx = 0

    async def receive():
        nonlocal idx
        if idx < len(parts):
            p = parts[idx]
            idx += 1
            return {"type": "http.request", "body": p, "more_body": idx < len(parts)}
        return {"type": "http.disconnect"}

    return receive


async def _run(headers, body=b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}',
               chunks=1, method="POST"):
    cap = Captured()
    mw = BearerAuthMiddleware(cap.inner_app, WWW_AUTH)
    await mw(_scope(headers, method), _receive(body, chunks), cap.send)
    return cap


def _auth(tok):
    return (b"authorization", f"Bearer {tok}".encode())


# ============================================================ P1-a — one selector
def test_p1a_only_one_selector_exists():
    """Static: the divergence was TWO implementations, so the fix is that there is one."""
    import inspect
    from mcp_server.priority_guardian_claude import server_dupl

    src = inspect.getsource(server_dupl)
    # the two old shapes: next()-over-headers, and an in-loop overwrite
    assert 'name == b"authorization"' not in src.replace(
        'if name.lower() == b"authorization"', ""), "a second selector survived"
    assert src.count("def select_authorization_header") == 1


@pytest.mark.parametrize("raw,expected", [
    ([], None),
    ([(b"authorization", b"Bearer abc")], "Bearer abc"),
    ([(b"Authorization", b"Bearer abc")], "Bearer abc"),          # case-insensitive
    ([(b"authorization", b"Bearer caf\xe9")], "Bearer café"),     # latin-1, cannot raise
])
def test_p1a_selector_contract(raw, expected):
    assert select_authorization_header(raw) == expected


def test_p1a_selector_rejects_duplicates_rather_than_choosing():
    """NOT resolved to a winner. Harmonising would fix the divergence and keep the ambiguity."""
    with pytest.raises(_DuplicateAuthorizationError):
        select_authorization_header([
            (b"authorization", b"Bearer a"),
            (b"authorization", b"Bearer b"),
        ])


@pytest.mark.asyncio
@pytest.mark.parametrize("first_valid", [True, False])
async def test_p1a_duplicate_headers_401_both_orders(jwks, first_valid):
    """valid-then-expired AND expired-then-valid must both 401 + challenge.

    Order-independence is the point: under the old code one order was admitted by
    the gate and rejected at dispatch as a 200 isError, and the other produced a
    false 401.
    """
    good, bad = _token(3600), _token(-3600)
    pair = [_auth(good), _auth(bad)] if first_valid else [_auth(bad), _auth(good)]
    cap = await _run(pair)

    assert cap.status == 401
    assert cap.headers.get("www-authenticate") == WWW_AUTH
    assert cap.headers.get("cache-control") == "no-store"
    assert cap.status != 400, "400 would be the single exception to A22-3's 401 rule"
    assert not cap.inner_called


@pytest.mark.asyncio
async def test_p1a_latin1_header_is_401_not_500(jwks):
    """b'Bearer caf\\xe9' passed the old gate and raised UnicodeDecodeError below it."""
    cap = await _run([(b"authorization", b"Bearer caf\xe9")])
    assert cap.status == 401
    assert cap.status != 500
    assert not cap.inner_called


@pytest.mark.asyncio
async def test_p1a_absent_and_single_unchanged(jwks):
    absent = await _run([])
    assert absent.status == 401 and b"Bearer token required" in absent.body

    single = await _run([_auth(_token(3600))])
    assert single.inner_called, "a single valid header must still be admitted"


# ================================================== P1-b — size guard, three cases
@pytest.mark.asyncio
async def test_p1b_case1_oversized_content_length_413_without_reading(jwks):
    """Declared oversize -> 413, and NOT ONE BODY BYTE read."""
    reads = {"n": 0}

    async def counting_receive():
        reads["n"] += 1
        return {"type": "http.request", "body": b"x", "more_body": False}

    cap = Captured()
    mw = BearerAuthMiddleware(cap.inner_app, WWW_AUTH)
    headers = [_auth(_token(3600)),
               (b"content-length", str(MAX_MCP_BODY_SIZE_BYTES + 1).encode())]
    await mw(_scope(headers), counting_receive, cap.send)

    assert cap.status == 413
    assert reads["n"] == 0, "pre-flight must avoid reading the body entirely"
    assert not cap.inner_called


@pytest.mark.asyncio
async def test_p1b_case2_oversized_stream_without_content_length_413(jwks):
    """No Content-Length, chunked oversize -> 413 during the bounded read.

    This is the case that makes the guard real: Content-Length is client-controlled
    and absent under chunked encoding, so a limit enforced on it is not a limit.
    """
    oversize = b"x" * (MAX_MCP_BODY_SIZE_BYTES + 4096)
    cap = await _run([_auth(_token(3600))], body=oversize, chunks=8)

    assert cap.status == 413
    assert not cap.inner_called


@pytest.mark.asyncio
async def test_p1b_case3_normal_body_replayed_exactly(jwks):
    """Asserted by the inner app RECEIVING THE EXACT PAYLOAD, not by absence of error."""
    payload = b'{"jsonrpc":"2.0","id":7,"method":"tools/list","params":{"a":"' + b"z" * 5000 + b'"}}'
    cap = await _run([_auth(_token(3600))], body=payload, chunks=5)

    assert cap.inner_called
    assert cap.body_seen == payload, "replay lost or altered the body"
    assert len(cap.body_seen) == len(payload)


@pytest.mark.asyncio
async def test_p1b_at_limit_boundary_is_admitted(jwks):
    """Exactly at the limit is allowed; one byte over is not."""
    at = b"y" * MAX_MCP_BODY_SIZE_BYTES
    cap = await _run([_auth(_token(3600))], body=at, chunks=4)
    assert cap.inner_called and cap.body_seen == at

    over = b"y" * (MAX_MCP_BODY_SIZE_BYTES + 1)
    cap2 = await _run([_auth(_token(3600))], body=over, chunks=4)
    assert cap2.status == 413


@pytest.mark.asyncio
async def test_p1b_get_and_delete_bypass_body_handling(jwks):
    """No body to guard; must not hang waiting for one."""
    for method in ("GET", "DELETE"):
        cap = Captured()
        mw = BearerAuthMiddleware(cap.inner_app, WWW_AUTH)
        await mw(_scope([_auth(_token(3600))], method), _receive(b""), cap.send)
        assert cap.inner_called, f"{method} was blocked"


@pytest.mark.asyncio
async def test_p1b_client_disconnect_midbody_returns_cleanly(jwks):
    """Disconnect before the body completes must not 500 or hang."""
    async def disconnecting():
        return {"type": "http.disconnect"}

    cap = Captured()
    mw = BearerAuthMiddleware(cap.inner_app, WWW_AUTH)
    await mw(_scope([_auth(_token(3600))]), disconnecting, cap.send)

    assert not cap.inner_called
    assert cap.status is None, "no response should be sent to a disconnected client"


# =============================== P1-a — the SECOND layer, where the 500 actually was
#
# WHY THIS EXISTS SEPARATELY. test_p1a_latin1_header_is_401_not_500 above exercises
# only BearerAuthMiddleware, which ALREADY decoded latin-1 before this increment —
# so it passes with or without the fix and proves nothing about the encoding split.
# The UnicodeDecodeError lived in MCPContentTypeAndAcceptFixMiddleware, which decoded
# utf-8. That gap was found by running the negative control, not by reading the test.

@pytest.mark.asyncio
async def test_p1a_second_layer_survives_latin1_header():
    """b'Bearer caf\\xe9' must not raise in the middleware that sets auth_header_var."""
    from contextvars import ContextVar
    from mcp_server.priority_guardian_claude.server_dupl import (
        MCPContentTypeAndAcceptFixMiddleware,
    )

    var = ContextVar("auth_header_test", default=None)
    seen = {}

    async def inner(scope, receive, send):
        seen["auth"] = var.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    cap = Captured()
    mw = MCPContentTypeAndAcceptFixMiddleware(inner, var)
    scope = _scope([(b"authorization", b"Bearer caf\xe9"),
                    (b"content-type", b"application/json")])

    # Before P1-a this raised UnicodeDecodeError -> Starlette 500.
    await mw(scope, _receive(b"{}"), cap.send)

    assert seen.get("auth") == "Bearer café", "second layer did not decode latin-1"
    assert cap.status == 200


@pytest.mark.asyncio
async def test_p1a_both_layers_select_identically():
    """The contract that was violated: gate and dispatch must see the SAME header."""
    from contextvars import ContextVar
    from mcp_server.priority_guardian_claude.server_dupl import (
        MCPContentTypeAndAcceptFixMiddleware,
    )

    var = ContextVar("auth_header_test2", default=None)
    seen = {}

    async def inner(scope, receive, send):
        seen["auth"] = var.get()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    for raw in (b"Bearer alpha", b"Bearer caf\xe9", b"Basic zzz"):
        cap = Captured()
        mw = MCPContentTypeAndAcceptFixMiddleware(inner, var)
        await mw(_scope([(b"authorization", raw)]), _receive(b"{}"), cap.send)

        gate_choice = select_authorization_header([(b"authorization", raw)])
        assert seen["auth"] == gate_choice, f"layers disagree on {raw!r}"


# ========================= P1-a (amended) — THE ASSEMBLED STACK, not one middleware
#
# WHY THIS EXISTS, and it is the most important comment in this file.
#
# P1-a was reported as closing the encoding split after replacing two Authorization
# decoders with one latin-1 selector. That was necessary and NOT SUFFICIENT. A THIRD
# decoder sat in RequestLoggingMiddleware — the OUTERMOST middleware — building a dict
# of EVERY header with strict utf-8. b"Bearer caf\xe9" raised there and became a 500
# before BearerAuthMiddleware ever ran, so neither of the earlier tests could observe
# it: one drove the gate, one drove the layer below it, NEITHER drove the stack.
#
# Two vacuity bugs in the same assertion, found by two different means. The first by
# running a negative control; the second by adversarial review. A negative control
# proves a test can fail — it cannot prove the test is wired to the right code path.
# Only the assembled stack does that.

def _assemble(inner):
    """The production middleware order, minus lifespan/FastMCP.

    RequestLogging -> HeadMcp -> OriginValidation -> BearerAuth -> ContentTypeFix -> inner
    """
    from contextvars import ContextVar
    from mcp_server.priority_guardian_claude.server_dupl import (
        RequestLoggingMiddleware, HeadMcpMiddleware, OriginValidationMiddleware,
        MCPContentTypeAndAcceptFixMiddleware,
    )
    var = ContextVar("auth_header_stack", default=None)
    app = MCPContentTypeAndAcceptFixMiddleware(inner, var)
    app = BearerAuthMiddleware(app, WWW_AUTH)
    app = OriginValidationMiddleware(app, ["https://claude.ai"])
    app = HeadMcpMiddleware(app)
    app = RequestLoggingMiddleware(app, "pg-claude-test")
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("header,value", [
    (b"authorization", b"Bearer caf\xe9"),
    (b"user-agent",    b"Mozilla/caf\xe9"),
    (b"referer",       b"https://x.test/caf\xe9"),
])
async def test_invalid_utf8_header_never_500s_through_full_stack(jwks, header, value):
    """ANY header with invalid UTF-8 must not crash the request.

    Before the amendment every one of these raised UnicodeDecodeError in the
    outermost middleware — an unauthenticated 500 trigger on a header nobody
    authenticates.
    """
    cap = Captured()
    app = _assemble(cap.inner_app)
    scope = {"type": "http", "method": "POST", "path": "/mcp",
             "headers": [(header, value), (b"origin", b"https://claude.ai")],
             "client": ("1.2.3.4", 0)}

    await app(scope, _receive(b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'), cap.send)

    assert cap.status is not None, "no response produced — the request crashed"
    assert cap.status != 500, f"{header!r} with invalid utf-8 produced a 500"


@pytest.mark.asyncio
async def test_latin1_authorization_is_401_through_full_stack(jwks):
    """The assertion P1-a always claimed, now made where it can actually fail."""
    cap = Captured()
    app = _assemble(cap.inner_app)
    scope = {"type": "http", "method": "POST", "path": "/mcp",
             "headers": [(b"authorization", b"Bearer caf\xe9"),
                         (b"origin", b"https://claude.ai")],
             "client": ("1.2.3.4", 0)}

    await app(scope, _receive(b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}'), cap.send)

    assert cap.status == 401, f"expected 401, got {cap.status}"
    assert cap.status != 500
    assert not cap.inner_called


@pytest.mark.asyncio
async def test_valid_token_still_admitted_through_full_stack(jwks):
    """The amendment must not break the admit path — checked through the real order."""
    cap = Captured()
    app = _assemble(cap.inner_app)
    payload = b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
    scope = {"type": "http", "method": "POST", "path": "/mcp",
             "headers": [_auth(_token(3600)), (b"origin", b"https://claude.ai"),
                         (b"content-type", b"application/json")],
             "client": ("1.2.3.4", 0)}

    await app(scope, _receive(payload, chunks=3), cap.send)

    assert cap.inner_called, "valid token blocked through the assembled stack"
    assert cap.body_seen == payload, "replay through the full stack lost the body"


# ================== P1-b amendment — memory must track BYTES, not CHUNK COUNT
#
# The committed version counted bytes correctly and stored them in a LIST of bytes
# objects. A body delivered in tiny chunks therefore cost one Python object per
# chunk (~33 B overhead each, plus a list pointer) on top of the payload. Measured
# on a 1 MiB limit: 89 MiB peak for a 1-byte-chunked body against a REPORTED bound
# of 2.01 MiB. Six concurrent such requests exhaust a 512 MiB Starter instance.
#
# The reported figure was not merely optimistic, it was false, and no test made it
# falsifiable. This one does.

@pytest.mark.asyncio
async def test_p1b_memory_tracks_bytes_not_chunk_count(jwks, monkeypatch):
    """1-byte chunks must not cost more than the same payload in large chunks."""
    import tracemalloc
    from mcp_server.priority_guardian_claude import config as claude_config

    # Small limit keeps the test fast; the defect is per-chunk overhead, which is
    # scale-invariant. 64 KiB in 1-byte chunks is 65,536 objects under the old code.
    small = 64 * 1024
    monkeypatch.setattr(claude_config, "MAX_MCP_BODY_SIZE_BYTES", small)

    payload = b"x" * small

    # A GENERATOR, not a pre-built list. The first version of this test used the
    # shared _receive() helper, which materialises every chunk up front — so it
    # measured the HARNESS allocating 65,536 one-byte objects, not the middleware.
    # It failed at ~10x and the overhead was entirely the test's own. Measure the
    # thing under test, not the scaffolding around it.
    one = b"x"
    remaining = {"n": small}

    async def drip_receive():
        if remaining["n"] > 0:
            remaining["n"] -= 1
            return {"type": "http.request", "body": one,
                    "more_body": remaining["n"] > 0}
        return {"type": "http.disconnect"}

    cap = Captured()
    mw = BearerAuthMiddleware(cap.inner_app, WWW_AUTH)
    scope = _scope([_auth(_token(3600))])

    tracemalloc.start()
    base = tracemalloc.get_traced_memory()[0]
    await mw(scope, drip_receive, cap.send)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    overhead = peak - base

    assert cap.inner_called and cap.body_seen == payload, "body corrupted"
    # Generous ceiling: 8x the payload. Old code hit ~85x here; new code ~2x.
    assert overhead < small * 8, (
        f"per-chunk overhead is back: {overhead/1024:.0f} KiB for a "
        f"{small/1024:.0f} KiB body — memory is tracking CHUNK COUNT again"
    )


# =============== P1-b amendment — the lifecycle _create_replay_receive exists for
#
# FastMCP's POST path hands `receive` to the SSE response, whose disconnect watcher
# calls receive() AFTER request.body() has consumed the replay. Every earlier test
# stopped at the terminal more_body=False and never called again — so the exact
# reason the forwarding exists had NO coverage, and if forwarding were wrong, tool
# calls would hang. That is P1-b's stated worst case: fails closed for everyone.

@pytest.mark.asyncio
async def test_p1b_receive_after_replay_forwards_to_real_receive(jwks):
    """A call past the replay must reach the ORIGINAL receive, not hang or repeat."""
    payload = b'{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
    post_replay = []

    async def original_receive():
        """Yields the body once, then a disconnect — as a real server would."""
        if not post_replay:
            post_replay.append("body-consumed")
            return {"type": "http.request", "body": payload, "more_body": False}
        post_replay.append("forwarded")
        return {"type": "http.disconnect"}

    seen = []

    async def sse_like_inner(scope, receive, send):
        """Mimics EventSourceResponse: read the body, THEN watch for disconnect."""
        msg = await receive()
        seen.append(("body", msg["type"], msg.get("body")))
        # the call the old harness never made
        watcher = await receive()
        seen.append(("watch", watcher["type"], None))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    cap = Captured()
    mw = BearerAuthMiddleware(sse_like_inner, WWW_AUTH)
    await mw(_scope([_auth(_token(3600))]), original_receive, cap.send)

    assert seen[0] == ("body", "http.request", payload), "replay did not deliver the body"
    assert seen[1][1] == "http.disconnect", (
        f"post-replay receive() returned {seen[1][1]!r} instead of forwarding to the "
        "real receive — a stale terminal message here is what hangs a tool call"
    )
    assert "forwarded" in post_replay, "the original receive was never reached"


# ============================ full stack — mixed-case Origin and duplicate auth
@pytest.mark.asyncio
@pytest.mark.parametrize("origin_name", [b"origin", b"Origin", b"ORIGIN"])
async def test_origin_allowlist_is_case_insensitive_through_full_stack(jwks, origin_name):
    """A disallowed Origin must be refused whatever the header name's casing.

    uvicorn lowercases names per the ASGI spec so this is not exploitable as
    deployed — but the allowlist must not DEPEND on the server normalising for it
    to be enforced at all.
    """
    cap = Captured()
    app = _assemble(cap.inner_app)
    scope = {"type": "http", "method": "POST", "path": "/mcp",
             "headers": [(origin_name, b"https://evil.example"), _auth(_token(3600))],
             "client": ("1.2.3.4", 0)}

    await app(scope, _receive(b'{"jsonrpc":"2.0","id":1}'), cap.send)

    assert cap.status == 403, f"{origin_name!r} bypassed the origin allowlist"
    assert not cap.inner_called


@pytest.mark.asyncio
async def test_duplicate_authorization_401_through_full_stack(jwks):
    """The duplicate case asserted through the assembled chain, not one middleware."""
    cap = Captured()
    app = _assemble(cap.inner_app)
    scope = {"type": "http", "method": "POST", "path": "/mcp",
             "headers": [_auth(_token(3600)), _auth(_token(-3600)),
                         (b"origin", b"https://claude.ai")],
             "client": ("1.2.3.4", 0)}

    await app(scope, _receive(b'{"jsonrpc":"2.0","id":1}'), cap.send)

    assert cap.status == 401
    assert cap.headers.get("www-authenticate") == WWW_AUTH
    assert not cap.inner_called


# ============================= one correlation id per request, not one per log call
#
# The middleware previously minted an id for token validation and a second for the
# body guard, so a 413 and the validation that preceded it could not be joined. On a
# server that DOES ship structured logs — established 2026-08-09 — unjoinable
# records in the middleware that fails closed for everyone is the difference between
# diagnosing an outage and guessing at it.

@pytest.mark.asyncio
async def test_one_correlation_id_per_request(jwks, monkeypatch):
    """Validation and the 413 path must share an id."""
    from mcp_server.priority_guardian_claude import mcp_auth_dupl, config as claude_config

    seen = []
    real = mcp_auth_dupl.validate_jwt

    async def spy(token, correlation_id):
        seen.append(("validate", correlation_id))
        return await real(token, correlation_id)

    monkeypatch.setattr(mcp_auth_dupl, "validate_jwt", spy)
    monkeypatch.setattr(claude_config, "MAX_MCP_BODY_SIZE_BYTES", 128)

    logged = []
    import mcp_server.priority_guardian_claude.server_dupl as SD
    monkeypatch.setattr(
        SD.logger, "warning",
        lambda event, **kw: logged.append((event, kw.get("correlation_id"))),
    )

    cap = Captured()
    mw = BearerAuthMiddleware(cap.inner_app, WWW_AUTH)
    await mw(_scope([_auth(_token(3600))]), _receive(b"z" * 512, chunks=4), cap.send)

    assert cap.status == 413, "expected the oversized path"
    ids = {cid for _, cid in seen} | {cid for _, cid in logged if cid}
    assert len(ids) == 1, (
        f"one request produced {len(ids)} correlation ids ({ids}) — the 413 and the "
        "token validation that preceded it cannot be joined in the logs"
    )
