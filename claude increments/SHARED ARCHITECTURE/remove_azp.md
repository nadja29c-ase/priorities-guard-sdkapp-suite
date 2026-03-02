# Claude Code Briefing: Remove `azp` Claim Validation — All Authenticated MCP Servers

## Context

### What is `azp`?
The `azp` (authorized party) claim in a JWT identifies which OAuth client requested the token. Our MCP servers currently validate that `azp` matches a hardcoded `CHATGPT_CLIENT_ID_*` environment variable. If a token arrives with a different client_id in the `azp` claim, the server rejects it with a 401.

### Why remove it?
OpenAI uses **dynamic client registration** (RFC 7591). Each time ChatGPT connects to an MCP server, it MAY register a new client_id via `POST /oauth/register`. This means:

- The developer's dev-mode connection gets one client_id
- The OpenAI reviewer's infrastructure gets a different client_id
- A production user reconnecting after a disconnect may get yet another client_id

Hardcoding a single expected client_id in `CHATGPT_CLIENT_ID_*` is fundamentally incompatible with dynamic client registration. It works in dev because you only have one client, but will fail when any other client connects — including OpenAI's review infrastructure.

### What remains after removal?
JWT validation remains strong. The following checks are UNCHANGED:
- **RS256 signature verification** (via JWKS)
- **Issuer validation** (`iss` claim)
- **Audience validation** (`aud` claim)
- **Expiry validation** (`exp` claim with grace period)
- **Not-before validation** (`nbf` claim)
- **Required claims enforcement** (`exp`, `iss`, `aud`, `sub`, `scope`, `jti`)
- **Per-tool scope enforcement** (e.g., `clarity.write`, `pg.access`, `focused.read`)

These are the security controls that matter. The `azp` check was defense-in-depth that conflicts with how OAuth dynamic registration works.

### Compliance
- **Not an OpenAI requirement.** The compliance master checklist has zero mention of `azp` validation.
- **Not in the MCP spec.** MCP delegates auth to OAuth 2.1 which supports dynamic registration.
- **Unpack shipped without it.** Unpack has no auth at all and was approved. Authenticated apps need valid JWT + scopes, not `azp` pinning.

## Scope

Remove `azp` claim validation from these three MCP servers:

1. **Clarity** — `mcp_server/clarity/mcp_auth.py` + `mcp_server/clarity/config.py`
2. **Priority Guardian** — `mcp_server/priority_guardian/mcp_auth.py` + `mcp_server/priority_guardian/config.py`
3. **Focused** — `mcp_server/focused/mcp_auth.py` + `mcp_server/focused/config.py`

Focused is frozen but shares the same codebase and config pattern. Fix it now to prevent the same issue if it's ever unpaused.

## Changes Required

### Per server (Clarity, PG, Focused):

#### config.py
- **Remove** the `CHATGPT_CLIENT_ID_*` environment variable definition entirely
- **Remove** the import of `CHATGPT_CLIENT_ID_*` if it exists elsewhere
- Do NOT remove any other config variables

#### mcp_auth.py
- **Remove** the import of `CHATGPT_CLIENT_ID_*` from config
- **Remove** the `azp` validation block in `validate_jwt()` (Step 5 in all three servers). This is the block that compares `azp` against `CHATGPT_CLIENT_ID_*` and raises `jwt.InvalidTokenError` on mismatch.
- **Remove** `"azp"` from the `"require"` list in `jwt.decode()` options. The `azp` claim should no longer be required in the JWT payload.
- **Keep** extracting `azp` from the payload for logging purposes. The `azp` value is still useful in `jwt.validation.success` and `auth.success` log lines for debugging which client_id made a request.
- **Keep** returning `azp` in the validated claims dict — downstream code may log it.

### What NOT to change
- Do not modify scope enforcement logic
- Do not modify JWKS caching
- Do not modify the `authenticate_request()` function signature or return type
- Do not modify any tool handlers
- Do not modify discovery endpoints
- Do not remove the `azp` field from log entries or return dicts — it's still useful for observability
- Do not touch Render environment variables yet (that's a deploy step, not a code step)

## Specific Code Locations

### Clarity (`mcp_server/clarity/`)

**config.py** — Remove lines ~82-90:
```python
# The CHATGPT_CLIENT_ID_CLARITY variable definition and its conditional ENV logic
```

**mcp_auth.py** — In `validate_jwt()`:
- Remove `CHATGPT_CLIENT_ID_CLARITY` from imports (line ~10 area)
- Remove `"azp"` from the `"require"` list in `jwt.decode()` options
- Remove the entire Step 5 azp validation block (~15 lines)
- Keep: `azp = payload.get("azp")` and all subsequent logging/return of `azp`

### Priority Guardian (`mcp_server/priority_guardian/`)

**config.py** — Remove lines ~68-71:
```python
CHATGPT_CLIENT_ID_PG = get_env(
    "CHATGPT_CLIENT_ID_PG",
    required=True
)
```

**mcp_auth.py** — In `validate_jwt()`:
- Remove `CHATGPT_CLIENT_ID_PG` from imports
- Remove `"azp"` from the `"require"` list in `jwt.decode()` options
- Remove the entire Step 6 azp validation block
- Keep: `azp = payload.get("azp")` and all logging/return of `azp`

**Note:** PG has an additional expiry grace period check (Step 5) that Clarity doesn't have. Do NOT touch that. The azp block is Step 6 in PG.

### Focused (`mcp_server/focused/`)

**config.py** — Remove `CHATGPT_CLIENT_ID_FOCUSED` definition (~lines 68-71, same pattern as PG).

**mcp_auth.py** — Same pattern as PG. Remove import, remove `"azp"` from require list, remove azp validation block, keep azp in logging.

## Unit Tests

For each of the three servers, add or update tests in the existing test directory:

### Tests to ADD:
1. **JWT with unknown azp passes validation** — Create a valid JWT (correct signature, issuer, audience, scopes, expiry) but with `azp` set to a random/unknown client_id (e.g., `"pg-client-unknown-test-id"`). Assert that `validate_jwt()` returns successfully and includes the unknown `azp` in the result.
2. **JWT without azp claim passes validation** — Create a valid JWT without the `azp` claim at all. Assert that `validate_jwt()` returns successfully with `azp=None` in the result.

### Tests to VERIFY still pass:
3. **JWT with expired token still fails** — Unchanged behavior.
4. **JWT with wrong issuer still fails** — Unchanged behavior.
5. **JWT with wrong audience still fails** — Unchanged behavior.
6. **JWT with invalid signature still fails** — Unchanged behavior.
7. **Scope enforcement still works** — Tool with insufficient scopes still rejected.

### Test approach:
- Use `unittest.mock.patch` to mock JWKS fetching
- Generate test JWTs with `PyJWT` using a test RSA key pair
- Do NOT make network calls in unit tests

## Integration Tests

Not required. This change removes a validation check — it doesn't add new external dependencies or data flows. The unit tests with mocked JWKS are sufficient to verify the behavior change.

## Post-Deploy: Environment Variable Cleanup

After deploying the code changes, the `CHATGPT_CLIENT_ID_*` environment variables in Render become dead config. They can be removed from Render's environment settings for each service at any time — the code will no longer reference them. This is an operational cleanup step, not a code change.

## Files to Modify

| Server | Files | Change |
|--------|-------|--------|
| Clarity | `mcp_server/clarity/config.py` | Remove `CHATGPT_CLIENT_ID_CLARITY` |
| Clarity | `mcp_server/clarity/mcp_auth.py` | Remove azp import, require, and validation block |
| PG | `mcp_server/priority_guardian/config.py` | Remove `CHATGPT_CLIENT_ID_PG` |
| PG | `mcp_server/priority_guardian/mcp_auth.py` | Remove azp import, require, and validation block |
| Focused | `mcp_server/focused/config.py` | Remove `CHATGPT_CLIENT_ID_FOCUSED` |
| Focused | `mcp_server/focused/mcp_auth.py` | Remove azp import, require, and validation block |

## Priority

**MEDIUM** — Not confirmed as the rejection cause, but a ticking time bomb for any multi-client scenario (review, reconnection, multiple users). Should ship alongside or immediately after the health endpoint change.