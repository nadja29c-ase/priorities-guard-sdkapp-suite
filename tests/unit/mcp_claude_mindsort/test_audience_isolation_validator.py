"""
Part E, Layer 1 (§9.1) — audience isolation at the VALIDATOR, both Claude servers.

Question answered: *does the audience check reject before scope enforcement is reached?*

A 401 alone proves nothing. These tests construct tokens carrying the CORRECT app scope
and a WRONG `aud`, then assert that rejection is specifically an audience failure —
`jwt.InvalidAudienceError`, which subclasses `InvalidTokenError` and is re-raised
unmodified by both `validate_jwt` implementations. Because `validate_jwt` raises before
returning claims, and scope enforcement happens downstream in tool dispatch, that single
assertion establishes both halves: rejection at the audience layer, and scope
enforcement never reached.

═══════════════════════════════════════════════════════════════════════════════
WHAT CONFIGURATION THESE TESTS REPRESENT — read before trusting any result here.
═══════════════════════════════════════════════════════════════════════════════
Both servers' accepted-audience lists include an issuer-shaped value BY DEFAULT:

    clarity/mcp_auth.py:303   [MCP_RESOURCE_URL, MCP_SERVER_URL, CLARITY_AUDIENCE]
    clarity/config.py:153     CLARITY_AUDIENCE default = "https://www.priority-guard.com"

    pg_claude/mcp_auth_dupl.py:308  [MCP_RESOURCE_URL, MCP_SERVER_URL, PG_AUDIENCE]
    pg_claude/config.py:125         PG_AUDIENCE default   = "https://www.priority-guard.com"

Run against those defaults, an issuer-`aud` token is ACCEPTED by both — which would make
MindSort-Claude look like it has PG-Claude's §11 defect, and would make PG-Claude's
characterization test pass for the wrong reason. That is a vacuous ENVIRONMENT rather
than a vacuous assertion, and the false finding would propagate into §11's scoping.

So these tests set TARGET-SHAPED audience config EXPLICITLY, by patching the module
globals the validator actually reads.

⚠️ THESE ARE TARGET-SHAPED, NOT PRODUCTION-SHAPED. An earlier revision called them
"production-shaped", which was wrong and is now known to be wrong. The deployed value,
read 2026-07-31:

    CLARITY_CLAUDE_AUDIENCE = https://www.priority-guard.com    <-- the ISSUER
    PG_CLAUDE_AUDIENCE      = (per §11; PG's default is likewise issuer-shaped)

So in PRODUCTION, MindSort-Claude accepts issuer-audience tokens — the very case the
MindSort tests below assert is rejected. They assert the DESIRED posture under the config
§11 will establish, not the current one.

These tests therefore establish:

    what each validator ACCEPTS GIVEN THIS CONFIG        <-- proven
    what production currently does                       <-- NO. Production accepts the
                                                             issuer on BOTH Claude servers

Keep those claims apart when reporting. The gap between them is §11's entire scope.

Patching, not re-importing: `mcp_auth_dupl` rebinds `clarity.mcp_auth` globals at import
time (REBOUND_GLOBALS), so a reimport contaminates later tests. Isolation is via explicit
patching plus the documented restore fixture — §9.4.
"""

import datetime

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Deterministic signing material (§9.5: deterministic keys, no network)
# ---------------------------------------------------------------------------
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PRIVATE_PEM = _KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
)
_PUBLIC_PEM = _KEY.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
)

ISSUER = "https://www.priority-guard.com"

# Production-shaped resource identifiers, stated explicitly rather than inherited
MINDSORT_RESOURCE = "https://mindsort-mcp.priority-guard.com/mcp"
MINDSORT_ORIGIN = "https://mindsort-mcp.priority-guard.com"
PG_RESOURCE = "https://mcp.priority-guard.com/mcp"
PG_ORIGIN = "https://mcp.priority-guard.com"
THIRD_PARTY = "https://evil.example.com/mcp"


def _make_token(aud, scope, sub="user-123"):
    """Sign a token with the given audience and scope. Everything else valid."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return pyjwt.encode(
        {
            "iss": ISSUER,
            "aud": aud,
            "sub": sub,
            "scope": scope,
            "jti": "test-jti-0001",
            "iat": now,
            "exp": now + datetime.timedelta(hours=1),
        },
        _PRIVATE_PEM,
        algorithm="RS256",
        headers={"kid": "test-key-id"},
    )


class _SigningKey:
    """Mimics PyJWKClient's signing-key object, which exposes .key."""

    def __init__(self, key):
        self.key = key


# Must match mcp_auth_dupl.REBOUND_GLOBALS exactly — same hardcoded tuple as
# test_scaffold.py's _FIXTURE_REBOUND_GLOBALS, and for the same reason.
#
# WHY HARDCODED RATHER THAN IMPORTED — the obvious fix does not work, and the next
# person will try it: importing REBOUND_GLOBALS from mcp_auth_dupl would execute the
# shim, which rebinds clarity.mcp_auth's globals at import time. That is precisely the
# contamination this fixture exists to undo, so the import would cause the problem it is
# meant to guard against. A hardcoded copy is forced, not lazy.
#
# Drift between this tuple and the shim is guarded by
# test_scaffold.py::test_fixture_rebound_list_matches_shim, which reads the shim in a
# SUBPROCESS to avoid the same pollution. (That test is currently red for an unrelated
# pre-existing reason — it ast.literal_eval's subprocess stdout that structlog pollutes.
# Backlog 16 territory; noted so the guard's state is not assumed.)
_FIXTURE_REBOUND_GLOBALS = (
    "CLARITY_JWKS_URL",
    "CLARITY_ISSUER",
    "CLARITY_AUDIENCE",
    "MCP_SERVER_URL",
    "MCP_RESOURCE_URL",
    "TOOL_SCOPES",
    "TOKEN_EXPIRY_GRACE_SECONDS",
    "JWKS_CACHE_TTL_SECONDS",
    "JWKS_MAX_STALE_SECONDS",
    "JWKS_FETCH_TIMEOUT_SECONDS",
)


@pytest.fixture
def restore_mcp_auth_globals():
    """
    Restore clarity.mcp_auth globals after each test (§9.4 isolation requirement).

    `mcp_server/mindsort_claude/mcp_auth_dupl.py` is a SHIM that rebinds module-level
    globals in `mcp_server.clarity.mcp_auth` at import time. Any session importing it —
    directly or transitively via server_dupl — contaminates later tests that import
    clarity.mcp_auth.

    Saves ALL TEN globals the shim mutates, matching test_scaffold.py and
    test_discovery.py. An earlier revision saved only the four this file patches, which
    was harmless in isolation but wrong in principle: the fixture carries the documented
    name, so it implies the documented coverage. Adding a patch of TOOL_SCOPES later
    would have silently escaped it.

    Defined locally rather than shared: fixtures do not cross module boundaries without a
    conftest, and adding one would restructure files outside this increment's scope (§10).
    """
    import mcp_server.clarity.mcp_auth as m

    saved = {
        name: getattr(m, name)
        for name in _FIXTURE_REBOUND_GLOBALS
        if hasattr(m, name)
    }
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(m, name, value)


@pytest.fixture
def mindsort_validator(restore_mcp_auth_globals):
    """
    MindSort-Claude's validator with TARGET-SHAPED audience config.

    NOT production-shaped: production sets CLARITY_CLAUDE_AUDIENCE to the ISSUER
    (read 2026-07-31). This fixture models the posture §11 will establish.

    Depends on restore_mcp_auth_globals (§9.4) because clarity.mcp_auth's globals are
    rebindable by the shim; the fixture restores them after each test.
    """
    import mcp_server.clarity.mcp_auth as m

    with patch.object(m, "MCP_RESOURCE_URL", MINDSORT_RESOURCE), \
         patch.object(m, "MCP_SERVER_URL", MINDSORT_ORIGIN), \
         patch.object(m, "CLARITY_AUDIENCE", MINDSORT_RESOURCE), \
         patch.object(m, "CLARITY_ISSUER", ISSUER), \
         patch.object(m, "_jwks_cache") as cache:
        cache.fetch_jwks = AsyncMock(return_value=None)
        cache.get_signing_key = MagicMock(return_value=_SigningKey(_PUBLIC_PEM))
        yield m


@pytest.fixture
def pg_validator():
    """
    PG-Claude's validator with TARGET-SHAPED audience config.

    NOT production-shaped, for the same reason as the MindSort fixture.

    No restore fixture needed: mcp_auth_dupl is a standalone module with its own JWKS
    cache and validate_jwt. It carries no rebinding hazard (§9.4 says so explicitly —
    do not impose the constraint where it does not apply).
    """
    import mcp_server.priority_guardian_claude.mcp_auth_dupl as m

    with patch.object(m, "MCP_RESOURCE_URL", PG_RESOURCE), \
         patch.object(m, "MCP_SERVER_URL", PG_ORIGIN), \
         patch.object(m, "PG_AUDIENCE", PG_RESOURCE), \
         patch.object(m, "PG_ISSUER", ISSUER), \
         patch.object(m, "_jwks_cache") as cache:
        cache.fetch_jwks = AsyncMock(return_value=None)
        cache.get_signing_key = MagicMock(return_value=_SigningKey(_PUBLIC_PEM))
        yield m


# ===========================================================================
# Positive controls — MUST come first conceptually
# ===========================================================================

@pytest.mark.asyncio
async def test_mindsort_accepts_its_own_resource_audience(mindsort_validator):
    """
    Bug this catches: A BROKEN HARNESS MAKING EVERY REJECTION MEANINGLESS. If the JWKS
    mock, the signing key or the issuer were wrong, every token would fail and all three
    rejection tests below would pass for reasons unrelated to audience. This proves the
    fixture can produce a SUCCESS, so the rejections are attributable to `aud`.
    """
    token = _make_token(aud=MINDSORT_RESOURCE, scope="clarity.write")
    claims = await mindsort_validator.validate_jwt(token, correlation_id="test")

    assert claims["user_id"] == "user-123"
    assert "clarity.write" in claims["scopes"]


@pytest.mark.asyncio
async def test_pg_accepts_its_own_resource_audience(pg_validator):
    """
    Bug this catches: the same broken-harness failure on the PG side. Without this, the
    PG rejection tests and the §11 characterization test could both be passing because
    the fixture never validates anything at all.
    """
    token = _make_token(aud=PG_RESOURCE, scope="pg.access")
    claims = await pg_validator.validate_jwt(token, correlation_id="test")

    assert claims["user_id"] == "user-123"
    assert "pg.access" in claims["scopes"]


# ===========================================================================
# §9.1 — wrong audience, CORRECT scope, per server
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_aud,label", [
    (ISSUER, "authorization-server issuer"),
    (PG_RESOURCE, "the OTHER Claude app's resource URL"),
    (THIRD_PARTY, "an unrelated third-party URL"),
])
async def test_mindsort_rejects_wrong_audience_at_the_audience_layer(
    mindsort_validator, wrong_aud, label
):
    """
    Bug this catches: audience validation being effectively absent, with SCOPE doing the
    isolation work. The token carries the CORRECT scope for MindSort (clarity.write), so
    a scope check cannot reject it — only the audience check can. Asserting
    InvalidAudienceError specifically (not merely "it raised") proves rejection happened
    at the audience layer, and because validate_jwt raises before returning claims, it
    also proves scope enforcement was never reached.

    The issuer case is the one that matters most — and its status changed on 2026-07-31.
    MindSort-Claude's DEPLOYED audience is the issuer, so in production it DOES share
    PG-Claude's §11 defect. This test asserts the TARGET posture, not the current one.
    """
    token = _make_token(aud=wrong_aud, scope="clarity.write")

    with pytest.raises(pyjwt.InvalidAudienceError):
        await mindsort_validator.validate_jwt(token, correlation_id="test")


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_aud,label", [
    (MINDSORT_RESOURCE, "the OTHER Claude app's resource URL"),
    (THIRD_PARTY, "an unrelated third-party URL"),
])
async def test_pg_rejects_wrong_audience_at_the_audience_layer(
    pg_validator, wrong_aud, label
):
    """
    Bug this catches: PG-Claude accepting any audience at all. Note the issuer case is
    deliberately EXCLUDED here and handled by the characterization test below — under
    production-shaped config PG rejects it, but its DEPLOYED config is unverified, which
    is the whole of §11.
    """
    token = _make_token(aud=wrong_aud, scope="pg.access")

    with pytest.raises(pyjwt.InvalidAudienceError):
        await pg_validator.validate_jwt(token, correlation_id="test")


# ===========================================================================
# §9.3 — the PG-Claude characterization test
# ===========================================================================

@pytest.fixture
def pg_validator_default_audience():
    """
    PG-Claude's validator with its REAL CODE DEFAULT audience — deliberately NOT patched.

    PG_AUDIENCE defaults to the issuer (`pg_claude/config.py:125`), which is the §11
    defect being characterized. Patching it to a production shape here would make the
    characterization test unable to see the defect at all — which is precisely the
    mistake an earlier revision of this file made.
    """
    import mcp_server.priority_guardian_claude.mcp_auth_dupl as m

    with patch.object(m, "MCP_RESOURCE_URL", PG_RESOURCE), \
         patch.object(m, "MCP_SERVER_URL", PG_ORIGIN), \
         patch.object(m, "PG_ISSUER", ISSUER), \
         patch.object(m, "_jwks_cache") as cache:
        # PG_AUDIENCE deliberately left at its module default (the issuer)
        cache.fetch_jwks = AsyncMock(return_value=None)
        cache.get_signing_key = MagicMock(return_value=_SigningKey(_PUBLIC_PEM))
        yield m


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason=(
        "§11 characterization of the PG-Claude resource-audience defect. This test "
        "asserts the DESIRED behaviour — that an issuer-aud token is rejected. Under "
        "PG's code default (PG_CLAUDE_AUDIENCE = the issuer, config.py:125) it is "
        "ACCEPTED, so the assertion fails and this xfails. When §11 lands, or if the "
        "deployed config sets a resource-shaped audience, it will XPASS — and "
        "strict=True turns that into a suite failure, forcing the marker to be removed "
        "rather than left as a permanently permissive security test. "
        "SCOPE LIMIT: this characterizes the CODE DEFAULT. It does NOT establish what "
        "production does — the deployed PG_CLAUDE_AUDIENCE has never been read (§3 "
        "required input; §11 owns it). Marker removal is part of §11's definition of "
        "done."
    ),
)
async def test_pg_rejects_issuer_audience(pg_validator_default_audience):
    """
    Bug this catches: a silent change in PG-Claude's audience posture, in EITHER
    direction. strict=True means an unexpected pass fails the suite, so the moment PG
    stops accepting issuer-aud tokens this fires and demands the marker be removed —
    rather than quietly recording "known behaviour" forever.

    Asserts the REASON, not merely the outcome: InvalidAudienceError specifically, so a
    rejection caused by a broken fixture, a bad signature or a wrong issuer would not
    satisfy it.

    Verified by mutation to actually discriminate: adding the issuer to PG's accepted
    audiences and removing it produce different results here.
    """
    token = _make_token(aud=ISSUER, scope="pg.access")

    with pytest.raises(pyjwt.InvalidAudienceError):
        await pg_validator_default_audience.validate_jwt(token, correlation_id="test")


# ===========================================================================
# The dev-default trap, asserted so it cannot silently return
# ===========================================================================

def test_dev_defaults_are_issuer_shaped_on_both_servers():
    """
    Bug this catches: A FUTURE READER TRUSTING A RESULT PRODUCED UNDER DEV DEFAULTS.
    Both servers' audience defaults are issuer-shaped, so a test that does NOT patch
    them proves the opposite of what it appears to. This asserts the trap still exists,
    so that if someone later removes the explicit patching above believing it redundant,
    this test documents why it is not.
    """
    import mcp_server.clarity.config as clarity_config
    import mcp_server.priority_guardian_claude.config as pg_config

    assert clarity_config.CLARITY_AUDIENCE == ISSUER, (
        "clarity's dev default is no longer issuer-shaped — re-evaluate whether the "
        "explicit patching in this file is still required"
    )
    assert pg_config.PG_AUDIENCE == ISSUER, (
        "PG-Claude's dev default is no longer issuer-shaped — re-evaluate the same"
    )
