"""
Part E, Layer 2 (§9.2) — the (resource, scope) issuance matrix.

Question answered: *which `(resource, scope)` combinations will the Authorization Server
actually mint, and what `aud` lands in the resulting token?*

Layer 1 established what each validator ACCEPTS. This establishes what the AS will
ISSUE — and that is what converts a validator property into an exploitability
assessment. A validator that rejects a wrong audience is irrelevant if the AS will
happily mint a token whose audience is right for the wrong app.

WHY EXHAUSTIVE RATHER THAN ILLUSTRATIVE. `resource` is accepted from the client at
/authorize and never validated against the client's scopes, its app, or any allowlist —
verified at committed SHA 0b05a69 (authorize.py:377 -> _normalize at :442 -> written to
the auth context at :487 and the token at :734, with no check in between). So `aud` is
client-controlled, and the only question is which combinations survive the other checks.
Two illustrative cases cannot answer that; six can.

ROWS 5 AND 6 ARE THE POINT. They establish whether `classify_scopes` and the client's
registered-scope check prevent cross-binding upstream, or whether the AS mints the token
and only the resource server's scope check stops it. §11 needs that answer either way —
it is the difference between "defence in depth" and "one control away from cross-app
access".

Environment per §9.5: isolated test database (tests/conftest.py:48 hardcodes
postgresql+asyncpg://localhost/priority_guardian_test — not env-derived, so it
structurally cannot reach production), deterministic fixtures, no network egress,
consent driven programmatically through real application code.

"Real flow" means real application code paths under test. It does NOT mean live
production behaviour, and nothing here establishes what production is configured to do.
"""

import base64
import hashlib
import os
import re
import time

import jwt as pyjwt
import pytest
from httpx import AsyncClient


PG_RESOURCE = "https://mcp.priority-guard.com/mcp"
MINDSORT_RESOURCE = "https://mindsort-mcp.priority-guard.com/mcp"

# Read the CONFIGURED issuer rather than hardcoding the production one. An earlier
# revision asserted "https://www.priority-guard.com" and failed in the test environment,
# where OAUTH_ISSUER is http://localhost:8000 — asserting a production value against a
# dev-configured system, which is the same environment mistake Layer 1 guards against,
# in reverse. What rows 1-2 prove is the Rule 5 FALLBACK BEHAVIOUR (final_resource=None
# -> aud=OAUTH_ISSUER), not any particular issuer string.
from backend.core.config import settings

ISSUER = settings.OAUTH_ISSUER
REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"


def _pkce():
    verifier = base64.urlsafe_b64encode(os.urandom(40)).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    return verifier, challenge


async def _mint(client: AsyncClient, route: str, scope: str, resource):
    """
    Drive DCR -> authorize -> consent -> token and return a structured outcome.

    Returns a dict describing how far the flow got and, if a token was issued, its
    decoded `aud` and `scope`. Never raises on a rejected flow — a refusal is a RESULT,
    not an error, and recording which step refused is the substance of the matrix.
    """
    verifier, challenge = _pkce()
    outcome = {"minted": False, "stopped_at": None, "aud": None, "scope": None, "detail": None}

    reg = await client.post(
        route + "/register",
        json={
            "client_name": f"matrix-{int(time.time() * 1000)}",
            "redirect_uris": [REDIRECT_URI],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "scope": scope,
        },
    )
    if reg.status_code == 429:
        pytest.skip("Rate limited")
    if reg.status_code not in (200, 201):
        outcome.update(stopped_at="register", detail=f"{reg.status_code}: {reg.text[:200]}")
        return outcome
    client_id = reg.json()["client_id"]

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": scope,
        "state": "matrix-state",
        "login_hint": f"matrix_user_{int(time.time() * 1000)}",
    }
    if resource is not None:
        params["resource"] = resource

    authz = await client.get(route + "/authorize", params=params)
    if authz.status_code != 200:
        outcome.update(stopped_at="authorize", detail=f"{authz.status_code}: {authz.text[:200]}")
        return outcome

    match = re.search(r'name="auth_context_id"\s+value="([^"]+)"', authz.text)
    if not match:
        outcome.update(stopped_at="consent_render", detail="auth_context_id not in consent HTML")
        return outcome

    consent = await client.post(
        route + "/consent",
        data={"auth_context_id": match.group(1), "action": "allow"},
        follow_redirects=False,
    )
    if consent.status_code != 302:
        outcome.update(stopped_at="consent", detail=f"{consent.status_code}: {consent.text[:200]}")
        return outcome

    code_match = re.search(r"[?&]code=([^&]+)", consent.headers.get("location", ""))
    if not code_match:
        outcome.update(stopped_at="code", detail=consent.headers.get("location", "")[:200])
        return outcome

    token_resp = await client.post(
        route + "/token",
        data={
            "grant_type": "authorization_code",
            "code": code_match.group(1),
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier,
        },
    )
    if token_resp.status_code != 200:
        outcome.update(stopped_at="token", detail=f"{token_resp.status_code}: {token_resp.text[:200]}")
        return outcome

    access = token_resp.json()["access_token"]
    claims = pyjwt.decode(access, options={"verify_signature": False, "verify_aud": False})
    outcome.update(
        minted=True,
        aud=claims.get("aud"),
        scope=claims.get("scope"),
    )
    return outcome


# ===========================================================================
# Rows 1-2 — resource OMITTED
# ===========================================================================

@pytest.mark.asyncio
async def test_row1_no_resource_pg_scope_mints_issuer_audience(client, fake_redis_client):
    """
    Row 1 — resource omitted, scope pg.access.

    Bug this catches: silent removal of the Rule 5 fallback, or a change making an
    omitted `resource` an error. Either would alter the audience posture without any
    test noticing. token_service.py:174-176 documents the fallback: neither the auth code
    nor the token request carries a resource, so final_resource is None and
    create_access_token uses OAUTH_ISSUER.

    Establishes: an issuer-audience token carrying PG scope IS mintable — which is the
    §11 defect's supply side.
    """
    r = await _mint(client, "/oauth/pg", scope="pg.access", resource=None)

    assert r["minted"], f"expected a token, stopped at {r['stopped_at']}: {r['detail']}"
    assert r["aud"] == ISSUER, f"expected issuer fallback, got aud={r['aud']!r}"


@pytest.mark.asyncio
async def test_row2_no_resource_mindsort_scope_mints_issuer_audience(client, fake_redis_client):
    """
    Row 2 — resource omitted, scope clarity.write.

    Bug this catches: the fallback behaving differently per route, which would mean the
    audience posture is not uniform across apps and §11's fix would need to be per-app.
    """
    r = await _mint(client, "/oauth/mindsort", scope="clarity.write", resource=None)

    assert r["minted"], f"expected a token, stopped at {r['stopped_at']}: {r['detail']}"
    assert r["aud"] == ISSUER, f"expected issuer fallback, got aud={r['aud']!r}"


# ===========================================================================
# Rows 3-4 — correct baselines
# ===========================================================================

@pytest.mark.asyncio
async def test_row3_pg_resource_pg_scope_is_correctly_bound(client, fake_redis_client):
    """
    Row 3 — the correct PG path.

    Bug this catches: the resource parameter being dropped or rewritten between
    /authorize and the minted token. If this fails, every other row is uninterpretable —
    it is the positive control for the whole matrix.
    """
    r = await _mint(client, "/oauth/pg", scope="pg.access", resource=PG_RESOURCE)

    assert r["minted"], f"expected a token, stopped at {r['stopped_at']}: {r['detail']}"
    assert r["aud"] == PG_RESOURCE
    assert "pg.access" in (r["scope"] or "")


@pytest.mark.asyncio
async def test_row4_mindsort_resource_mindsort_scope_is_correctly_bound(client, fake_redis_client):
    """
    Row 4 — the correct MindSort path. Positive control for the MindSort route.

    Bug this catches: the mindsort route mishandling `resource`, which would make rows 2
    and 6 unreadable.
    """
    r = await _mint(client, "/oauth/mindsort", scope="clarity.write", resource=MINDSORT_RESOURCE)

    assert r["minted"], f"expected a token, stopped at {r['stopped_at']}: {r['detail']}"
    assert r["aud"] == MINDSORT_RESOURCE
    assert "clarity.write" in (r["scope"] or "")


# ===========================================================================
# Rows 5-6 — CROSS-BINDING. The rows §11 actually needs.
# ===========================================================================

@pytest.mark.asyncio
async def test_row5_mindsort_scope_with_pg_resource(client, fake_redis_client):
    """
    Row 5 — a client registered for clarity.write requests resource=<PG resource URL>.

    THE QUESTION: does the AS refuse, or does it mint a token whose audience PG-Claude
    accepts while carrying only MindSort scope?

    Bug this catches: a future change that starts validating `resource` against the
    client's scopes, or stops. Either way the matrix must move, and a silent move is
    exactly what §11 must not inherit. The assertion records the CURRENT behaviour
    precisely rather than asserting a hoped-for one.

    Interpretation, whichever way it lands:
      - refused  -> `classify_scopes` or the registered-scope check prevents cross-binding
                    upstream; audience is defended by two controls
      - minted   -> the AS will mint cross-bound tokens and ONLY the resource server's
                    per-tool scope check stops the request. That is the "one control away"
                    finding, and it is what §11 exists to close.
    """
    r = await _mint(client, "/oauth/mindsort", scope="clarity.write", resource=PG_RESOURCE)

    # PINNED, not merely recorded. An earlier revision made these assertions conditional
    # on r["minted"], so the test would still pass once §11 makes the AS refuse
    # cross-binding — it documented the behaviour without defending it. Layer 1 uses
    # xfail(strict=True) precisely so a behaviour change fails loudly; this is the same
    # class of finding and gets the same treatment. §11 changes this deliberately, so
    # updating this test is part of §11's definition of done.
    assert r["minted"], (
        "The AS refused to mint a cross-bound token. If §11 has landed this is EXPECTED "
        "— update this test as part of its definition of done. If §11 has NOT landed, "
        f"the isolation posture changed silently. stopped_at={r['stopped_at']}: {r['detail']}"
    )
    assert r["aud"] == PG_RESOURCE, (
        "cross-bound token minted but with an unexpected audience — the matrix's "
        f"assumption about resource->aud propagation is wrong: aud={r['aud']!r}"
    )
    assert "pg.access" not in (r["scope"] or ""), (
        "ESCALATION: the AS granted PG scope to a client that registered for "
        f"clarity.write. scope={r['scope']!r}"
    )


@pytest.mark.asyncio
async def test_row6_pg_scope_with_mindsort_resource(client, fake_redis_client):
    """
    Row 6 — cross-binding in reverse: a pg.access client requests the MindSort resource.

    Bug this catches: asymmetric handling between the two routes. If row 5 is refused and
    row 6 is minted (or vice versa), the isolation posture differs per app and §11's fix
    cannot be uniform — which would be invisible without testing both directions.
    """
    r = await _mint(client, "/oauth/pg", scope="pg.access", resource=MINDSORT_RESOURCE)

    # PINNED — see the note on row 5.
    assert r["minted"], (
        "The AS refused to mint a cross-bound token in the reverse direction. Expected "
        "only if §11 has landed; otherwise the posture changed silently. "
        f"stopped_at={r['stopped_at']}: {r['detail']}"
    )
    assert r["aud"] == MINDSORT_RESOURCE, (
        f"cross-bound token minted with unexpected audience: aud={r['aud']!r}"
    )
    assert "clarity.write" not in (r["scope"] or ""), (
        "ESCALATION: the AS granted MindSort scope to a client that registered for "
        f"pg.access. scope={r['scope']!r}"
    )


# ===========================================================================
# The matrix itself — recorded, not merely asserted
# ===========================================================================

@pytest.mark.asyncio
async def test_full_issuance_matrix_recorded(client, fake_redis_client, capsys):
    """
    Runs all six rows and prints the matrix, so the §17 report can quote observed
    behaviour rather than restating expectations.

    Bug this catches: the individual row tests passing while the OVERALL posture is
    misread. Six independent assertions do not compose into a picture; this prints one.
    It also fails if every row refuses, which would mean the harness is broken rather
    than the AS being strict — the same broken-fixture hazard the Layer 1 positive
    controls guard against.
    """
    rows = [
        ("1", "/oauth/pg", "pg.access", None),
        ("2", "/oauth/mindsort", "clarity.write", None),
        ("3", "/oauth/pg", "pg.access", PG_RESOURCE),
        ("4", "/oauth/mindsort", "clarity.write", MINDSORT_RESOURCE),
        ("5", "/oauth/mindsort", "clarity.write", PG_RESOURCE),
        ("6", "/oauth/pg", "pg.access", MINDSORT_RESOURCE),
    ]

    results = []
    for num, route, scope, resource in rows:
        r = await _mint(client, route, scope=scope, resource=resource)
        results.append((num, route, scope, resource, r))

    lines = ["", "=" * 100, "PART E LAYER 2 — (resource, scope) ISSUANCE MATRIX", "=" * 100]
    for num, route, scope, resource, r in results:
        verdict = "MINTED" if r["minted"] else f"REFUSED@{r['stopped_at']}"
        lines.append(
            f"  row {num} | {route:<18} | scope={scope:<14} | "
            f"resource={str(resource):<45} | {verdict:<18} | aud={r['aud']!r}"
        )
    lines.append("=" * 100)
    print("\n".join(lines))

    assert any(r["minted"] for *_, r in results), (
        "no row minted a token — the harness is broken, not the AS strict"
    )
