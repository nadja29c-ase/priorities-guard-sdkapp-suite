# Increment — OAuth Cleanup: Remove Cross-App Default Scopes + Docstring Hygiene

## Scope and intent

Two small, independent hygiene changes in `backend/core/oauth_provider/`. Both are pre-launch prerequisites to the upcoming cross-device identity reconciliation increment (Increment 78). Ship this as ONE small PR separate from Inc 78.

**This is a surgical cleanup. Do NOT expand scope.** Specifically: do not refactor the OAuth client registration flow, do not touch `register_client.py`, do not touch discovery documents, do not touch any other part of the OAuth provider. If you see code that looks improvable while working in these files, leave it.

---

## Context

### Fact 1 — there is a latent security landmine in `client_service.py`

`create_oauth_client` in `backend/core/oauth_provider/services/client_service.py` has this block:

```python
# Set default scopes (must include all supported scopes)
if scopes is None:
    scopes = ["focused.read", "focused.write", "focused.notify", "clarity.write"]
```

If any caller fails to pass `scopes` explicitly, the fallback issues a client with scopes spanning **three different SDK apps** (Focused + MindSort AI). This is a cross-app privilege escalation waiting to happen.

Today, the only caller (`register_client.py → register_endpoint`) always computes explicit scopes from the route path (`DEFAULT_SCOPES_FOCUSED` / `DEFAULT_SCOPES_PG` / `DEFAULT_SCOPES_MINDSORT`) and passes them. Verified. The fallback is dead code today. It is a landmine for future regressions.

### Fact 2 — `oauth_provider_router.py` docstring is stale

The module docstring lists only `/oauth/focused/*` endpoints. The router actually mounts `/oauth/focused/*`, `/oauth/pg/*`, and `/oauth/mindsort/*` routes (verified: `register_client.py` has three `@router.post` decorators for the same function; `oauth_provider_router.py` additionally includes `mindsort_discovery_router` with prefix `/oauth/mindsort`).

### Why these are bundled in one PR

Both are 5-minute changes in the same area of code. One review, one deploy, one revert surface if anything breaks. Splitting them creates pointless PR overhead.

### Why this blocks Inc 78

It doesn't — Inc 78 could ship without this. But this cleanup is a cheap high-value security fix that should precede any new OAuth-related work. The default-scopes landmine has been flagged as must-fix before launch independently of Inc 78. Doing it first clears the decks.

---

## Files to modify

- `backend/core/oauth_provider/services/client_service.py` — replace fallback with explicit error
- `backend/core/routers/oauth_provider_router.py` — update stale docstring
- `tests/unit/backend/` — add TWO unit tests for `create_oauth_client` (exact path TBD based on existing layout)

## Files NOT to modify

- `backend/core/oauth_provider/register_client.py` — untouched
- `backend/core/oauth_provider/discovery.py` — untouched
- `backend/core/oauth_provider/mindsort_discovery.py` — untouched
- Any other OAuth provider file — untouched
- Any ADR file — untouched (separate deferred item, not in this PR)

---

## Change 1 — Replace default-scopes fallback with explicit error

### File: `backend/core/oauth_provider/services/client_service.py`

**Current code (lines around 58–62):**

```python
    # Set default scopes (must include all supported scopes)
    if scopes is None:
        scopes = ["focused.read", "focused.write", "focused.notify", "clarity.write"]
```

**Replace with:**

```python
    # Scopes must be explicitly provided by the caller.
    # Previously this block fell back to a union of scopes across ALL SDK apps,
    # which is a cross-app privilege escalation landmine. Per-route defaults are
    # computed in register_client.py — no global default is correct here.
    if scopes is None:
        raise ValueError(
            "scopes must be explicitly provided — no global defaults allowed. "
            "Callers should resolve per-route defaults before calling create_oauth_client."
        )
```

### Docstring update in same file

The function's existing docstring describes the `scopes` parameter as optional. Update the `scopes` line of the Args section to make "required in practice" explicit:

**Find:**
```
        scopes: Optional list of scopes (caller should provide explicit scopes)
```

**Replace with:**
```
        scopes: List of scopes. Required in practice — passing None raises ValueError.
                Typing stays Optional to preserve the signature; callers must always
                provide explicit scopes (per-route defaults are computed in
                register_client.py).
```

### Do NOT change the type signature

Keep `scopes: list[str] | None = None`. Changing it to `list[str]` would be a breaking signature change for any code reflecting on the function, and would require changing the function call site too. The runtime `raise ValueError` is sufficient.

---

## Change 2 — Update stale docstring

### File: `backend/core/routers/oauth_provider_router.py`

**Current docstring block (top of file):**

```python
Included Endpoints:
- Discovery: /.well-known/openid-configuration, oauth-protected-resource
- JWKS: /oauth/focused/jwks
- Authorization: /oauth/focused/authorize (OAuth 2.1 + PKCE)
- Consent UI: /oauth/focused/consent
- Token: /oauth/focused/token (authorization_code, refresh_token grants)
- Registration: /oauth/focused/register (RFC 7591 dynamic client registration)
- Revocation: /oauth/focused/revoke (RFC 7009 token revocation)

Status: Consolidated OAuth 2.1 provider for all SDK apps
```

**Replace with:**

```python
Included Endpoints (served for three SDK app route families: focused, pg, mindsort):
- Discovery: /.well-known/openid-configuration, oauth-protected-resource
- JWKS: /oauth/{focused,pg,mindsort}/jwks
- Authorization: /oauth/{focused,pg,mindsort}/authorize (OAuth 2.1 + PKCE)
- Consent UI: /oauth/{focused,pg,mindsort}/consent
- Token: /oauth/{focused,pg,mindsort}/token (authorization_code, refresh_token grants)
- Registration: /oauth/{focused,pg,mindsort}/register (RFC 7591 dynamic client registration)
- Revocation: /oauth/{focused,pg,mindsort}/revoke (RFC 7009 token revocation)
- MindSort-specific discovery: /oauth/mindsort/.well-known/oauth-authorization-server

Status: Consolidated OAuth 2.1 provider for all SDK apps
```

This is a pure comment change. No executable code is affected.

---

## Change 3 — Unit tests (error path + positive path)

Add TWO focused tests to `create_oauth_client`:

1. **Error path** — asserts `ValueError` when `scopes=None`. Protects the landmine fix.
2. **Positive path** — asserts normal client creation still works when explicit scopes are provided. Protects against accidental regression of the happy path while editing this function.

Location: match the existing test layout. The PG test tree is under `tests/unit/backend/` — place the tests next to other `client_service` tests if they exist; otherwise create `tests/unit/backend/test_client_service.py`.

Use whatever `db_session` / fixture pattern is already established in the test suite. Do not introduce new fixture patterns.

### Test 1 — error path

```python
import pytest
from backend.core.oauth_provider.services.client_service import create_oauth_client

@pytest.mark.asyncio
async def test_create_oauth_client_raises_when_scopes_none(db_session):
    """scopes=None must raise — no global default scopes allowed (cross-app privilege landmine)."""
    with pytest.raises(ValueError, match="scopes must be explicitly provided"):
        await create_oauth_client(
            db=db_session,
            client_name="test-client",
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code"],
            scopes=None,
        )
```

### Test 2 — positive path

```python
@pytest.mark.asyncio
async def test_create_oauth_client_succeeds_with_explicit_scopes(db_session):
    """Normal path still works when caller passes explicit scopes."""
    client_id, client_secret = await create_oauth_client(
        db=db_session,
        client_name="test-client",
        redirect_uris=["https://example.com/callback"],
        grant_types=["authorization_code", "refresh_token"],
        scopes=["pg.access"],
    )

    # The `pg-client-` prefix is a documented contract, not an implementation detail.
    # See client_service.py docstring ("Generates: Unique client_id (pg-client-{uuid})")
    # and register_client.py endpoint docstring (same contract). Keep the assertion.
    assert client_id.startswith("pg-client-")
    assert client_secret  # Plain-text secret returned exactly once
    assert len(client_secret) > 0
```

The positive test deliberately checks only the return contract — `client_id` prefix (documented invariant) and that a secret is returned. It does NOT check DB state, encryption details, or other implementation internals. Scope discipline: just enough to catch a regression of the happy path.

**Do NOT add any further tests for this function** (scope validation, encryption, DB persistence edge cases, multiple calls, etc.). Those are explicitly out of scope for this PR. Two tests total.

---

## What happens if a caller hits this in the future

The `raise ValueError` will surface as an HTTP 500 from the `/oauth/{app}/register` endpoint (because `register_client.py` does not catch ValueError explicitly). That is acceptable and correct:

- The only path to `create_oauth_client` is through `register_endpoint`.
- If a future code change accidentally routes around the explicit-scopes logic in `register_endpoint`, a 500 is strictly safer than silently issuing a cross-app-privileged client.
- A 500 is immediately visible in logs and monitoring; a silent privilege escalation is not.

Do NOT add special-case exception handling to convert this to a 400 or anything user-friendly. The assumption is: no end-user ever sees this error because no correct code path triggers it.

---

## Pre-deploy

Read `OPERATIONS_PREDEPLOY.md` before committing.

- No DB migrations in this PR.
- No discovery document changes. Skip the OAuth discovery verification steps.
- Single Alembic head check — should already be satisfied.

Deploy order: no constraints. This PR is self-contained and does not touch MCP servers.

---

## Smoke tests after deploy

The smoke tests verify behavior, not internal log wording. They prove the PR did not regress the normal registration flow.

1. **Trigger a fresh ChatGPT connector registration** — either through the ChatGPT UI connecting to Priority Guardian, or a manual authenticated POST to `/oauth/pg/register` with a valid payload and `scope` set explicitly.
2. **Verify the registration returns normally** — HTTP 200, response body contains `client_id`, `client_secret`, and `scope`.
3. **Verify the returned `scope` is exactly what was requested** — e.g., for `scope: "pg.access"` the response `scope` should be `"pg.access"`, not a cross-app scope union. This is the strongest assertion of the PR: if the fallback were still firing, the returned scope would be the cross-app union.
4. **Verify no 5xx response on the smoke-test registration call itself.** A 500 on the `/oauth/*/register` call would indicate `raise ValueError` is firing — meaning an upstream caller is passing `scopes=None` unexpectedly. Roll back immediately.
5. **Post-deploy, monitor `/oauth/*/register` specifically for 500s.** If any `/oauth/*/register` call returns 500 after deploy, investigate immediately (likely the same root cause as step 4). Unrelated 5xx elsewhere in the system is not a signal for this PR — ignore.

---

## Implementation approach — Copy and Adjust, Never Rewrite

- `client_service.py` — modify ONLY the `if scopes is None:` block (replace body with `raise ValueError(...)`) and the single line of the `scopes:` docstring description inside the Args block. Do not touch any other line in the file. Do not reformat. Do not reorder imports.
- `oauth_provider_router.py` — modify ONLY the "Included Endpoints" block of the module docstring. Do not change the `router.include_router(...)` calls, the imports, the `tags=` argument, or anything else.
- Test file — add ONLY the two test cases specified above. If the test file already exists with other tests, append the new tests; do not reorganize existing tests.

No `_dupl` filename convention applies here — these are edits to existing files, not new files in the shared backend path.

---

## What is explicitly NOT in this PR

- ADR_MCP Server Implementation Standard multi-app OAuth section update — deferred.
- Focused route deprecation or migration — deferred (Option A from the backlog: leave as-is).
- Future-SDK-apps checklist documentation — deferred.
- Any changes to `register_client.py`, discovery files, or MCP server code — deferred or unrelated.
- Any additional "while we're here" improvements — explicitly disallowed.

If Claude Code notices something that seems improvable, it leaves it. Scope discipline on this PR is more valuable than the improvement.
