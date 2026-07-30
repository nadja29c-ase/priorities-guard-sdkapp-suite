"""
Integration tests for RFC 8252 loopback redirect URIs (Part B, §14).

The unit tests prove the validator's logic. These prove the ENDPOINT: that a loopback
URI accepted at DCR is persisted verbatim and then accepted by /authorize's
set-membership check against the client's own registered URIs.

That gap is the one that has already bitten once. The ::1 defect was invisible to
unit-level reasoning about _normalize_redirect_uri in isolation — it only appears when
DCR and authorize are exercised as a pair, which is what these tests do.

Run across ALL THREE register routes per §6.4: the validator is shared, so a regression
would surface on any of them.
"""

import pytest
from httpx import AsyncClient


EPHEMERAL_LOOPBACK = "http://127.0.0.1:53821/oauth/callback"
REGISTER_ROUTES = ["/oauth/focused/register", "/oauth/pg/register", "/oauth/mindsort/register"]


async def _register(client: AsyncClient, route: str, redirect_uri: str, name: str):
    return await client.post(
        route,
        json={"client_name": name, "redirect_uris": [redirect_uri]},
    )


@pytest.mark.asyncio
async def test_rate_limiting_is_not_silently_hiding_this_suite(client: AsyncClient, fake_redis_client):
    """
    Bug this catches: SILENT GREEN. Every other test in this file skips on HTTP 429, so
    if rate limiting fired consistently the suite would report success having verified
    nothing at all. This canary deliberately does NOT skip: if a plain valid registration
    cannot get through, the suite fails loudly instead of passing vacuously.
    """
    response = await _register(
        client, "/oauth/mindsort/register", EPHEMERAL_LOOPBACK, "PartB-RateLimitCanary"
    )
    assert response.status_code != 429, (
        "registration is being rate limited — every other test in this file skips on "
        "429, so their green result would be meaningless"
    )
    assert response.status_code == 200, f"{response.status_code}: {response.text[:300]}"


# ============================================================================
# DCR acceptance — the defect Part B fixes
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("route", REGISTER_ROUTES)
async def test_ephemeral_loopback_registers_on_every_route(client: AsyncClient, fake_redis_client, route):
    """
    Bug this catches: the production defect itself — an ephemeral-port loopback URI
    rejected at DCR, observed against production on 2026-07-30 as HTTP 400
    "redirect_uri not in allowlist". Claude Code and MCP Inspector bind a random port,
    so a reviewer could not register at all.

    Run per-route because the validator is shared: a regression on the pg or focused
    route would be invisible if only mindsort were tested.
    """
    response = await _register(client, route, EPHEMERAL_LOOPBACK, "PartB-Loopback")
    if response.status_code == 429:
        pytest.skip("Rate limited")

    assert response.status_code == 200, f"{route}: {response.status_code} {response.text}"


@pytest.mark.asyncio
async def test_registered_loopback_uri_is_persisted_verbatim(client: AsyncClient, fake_redis_client):
    """
    Bug this catches: the validate/persist divergence closed in b8d4bef. The validator
    sees urlsplit's stripped view while register_client persists the RAW string, so a
    URI could be validated as one thing and stored as another. Asserting the round trip
    at the endpoint proves the stored value is the value that was checked.
    """
    response = await _register(client, "/oauth/mindsort/register", EPHEMERAL_LOOPBACK, "PartB-Verbatim")
    if response.status_code == 429:
        pytest.skip("Rate limited")

    assert response.status_code == 200
    assert response.json()["redirect_uris"] == [EPHEMERAL_LOOPBACK]


# ============================================================================
# DCR rejection — 400, never 500
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("redirect_uri,why", [
    ("http://localhost.evil.com:8080/oauth/callback", "attacker host with a localhost prefix"),
    ("http://127.0.0.1.evil.com/callback", "attacker host with an IP-literal prefix"),
    ("http://[::1]:41234/callback", "IPv6 excluded — authorize cannot match it"),
    ("http://local\thost:53821/oauth/callback", "tab inside the hostname"),
])
async def test_hostile_loopback_variants_rejected(client: AsyncClient, fake_redis_client, redirect_uri, why):
    """
    Bug this catches: substring/prefix matching on the host instead of exact comparison
    against the parsed hostname, which would register attacker-controlled callbacks; and
    regression of the ::1 and whitespace decisions, both of which are deliberate.
    """
    response = await _register(client, "/oauth/mindsort/register", redirect_uri, "PartB-Hostile")
    if response.status_code == 429:
        pytest.skip("Rate limited")

    assert response.status_code == 400, f"{why}: expected 400, got {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("redirect_uri", [
    "http://localhost:abc/oauth/callback",
    "http://localhost:99999/oauth/callback",
])
async def test_malformed_port_returns_400_not_500(client: AsyncClient, fake_redis_client, redirect_uri):
    """
    Bug this catches: urlsplit's .port raising ValueError on a malformed port. Unhandled,
    a bad registration request becomes a 500 — an availability and error-contract defect,
    not merely a validation one. The unit test proves no exception escapes the validator;
    this proves the ENDPOINT returns a clean 400.
    """
    response = await _register(client, "/oauth/mindsort/register", redirect_uri, "PartB-BadPort")
    if response.status_code == 429:
        pytest.skip("Rate limited")

    assert response.status_code == 400, f"expected 400, got {response.status_code}"
    assert response.status_code != 500


# ============================================================================
# DCR -> authorize, the pair. This is the section that matters.
# ============================================================================

@pytest.mark.asyncio
async def test_registered_loopback_uri_is_accepted_at_authorize(client: AsyncClient, fake_redis_client):
    """
    Bug this catches: DCR/authorize DIVERGENCE — a URI registrable but not authorizable.
    This is the ::1 class of defect, and unit-level checks against
    _normalize_redirect_uri could not see it: they tested normalization in isolation,
    not the endpoint's set-membership against client.redirect_uris.

    ASSERTS 200 + the rendered consent page, NOT the absence of an error string.
    An earlier version asserted `"invalid_redirect_uri" not in body` — which could never
    fail: that string appears only in authorize.py's structured LOG (:520, :535), while
    the HTTP bodies are "Invalid redirect_uri format" (:525) and "redirect_uri not
    registered for this client" (:539). The test would have gone green through exactly
    the divergence it exists to detect. 200 + consent HTML is unambiguous: the client was
    just registered with clarity.write, the requested scope is a subset, and PKCE is
    S256, so nothing else returns 200 here.
    """
    reg = await _register(client, "/oauth/mindsort/register", EPHEMERAL_LOOPBACK, "PartB-Authz")
    if reg.status_code == 429:
        pytest.skip("Rate limited")
    assert reg.status_code == 200
    client_id = reg.json()["client_id"]

    response = await client.get(
        "/oauth/mindsort/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": EPHEMERAL_LOOPBACK,
            "response_type": "code",
            "scope": "clarity.write",
            "state": "partb-state",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
        },
    )

    assert response.status_code == 200, (
        f"loopback URI accepted at DCR was rejected at authorize "
        f"({response.status_code}): {response.text[:400]}"
    )
    assert "Authorize MindSort AI" in response.text, (
        "expected the rendered consent page; got a 200 without it"
    )


@pytest.mark.asyncio
async def test_unregistered_loopback_uri_rejected_at_authorize(client: AsyncClient, fake_redis_client):
    """
    Bug this catches: the loopback rule leaking from DCR into AUTHORIZE. Authorize must
    match against THIS client's registered URIs (§0.2's exact layer), not against the
    platform allowlist — so a different valid loopback port, never registered by this
    client, must be refused. If this passes, authorize is matching by rule rather than by
    registration, which would let any client redirect to any loopback port.
    """
    reg = await _register(client, "/oauth/mindsort/register", EPHEMERAL_LOOPBACK, "PartB-Unreg")
    if reg.status_code == 429:
        pytest.skip("Rate limited")
    assert reg.status_code == 200
    client_id = reg.json()["client_id"]

    response = await client.get(
        "/oauth/mindsort/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": "http://127.0.0.1:9999/oauth/callback",  # valid shape, NOT registered
            "response_type": "code",
            "scope": "clarity.write",
            "state": "partb-state",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
        },
    )

    assert response.status_code != 500, response.text
    assert response.status_code == 400, (
        f"an unregistered loopback URI must be refused at authorize, got "
        f"{response.status_code}: {response.text[:400]}"
    )


@pytest.mark.asyncio
async def test_existing_platform_callbacks_still_register(client: AsyncClient, fake_redis_client):
    """
    Bug this catches: §6.4 non-regression at the ENDPOINT — Part B widening DCR in a way
    that disturbs an existing platform callback. The OpenAI reviewer callback is the
    most damaging one to lose, and two published live apps depend on the ChatGPT prefix
    rule continuing to accept dynamic connector ids.
    """
    for uri in [
        "https://chatgpt.com/connector/oauth/PARTB123",
        "https://chatgpt.com/connector_platform_oauth_redirect",
        "https://platform.openai.com/apps-manage/oauth",
        "https://claude.ai/api/mcp/auth_callback",
    ]:
        response = await _register(client, "/oauth/pg/register", uri, "PartB-Platform")
        if response.status_code == 429:
            pytest.skip("Rate limited")
        assert response.status_code == 200, f"{uri} no longer registers: {response.text}"
