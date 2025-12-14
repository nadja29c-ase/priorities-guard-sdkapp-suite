Increment 7D — MCP Token Validation + Tool-Level Scope Enforcement
Final Briefing (with Backend Migration Safety)

1. Goal
Lock down the Focused MCP server so that every tool call:
is authenticated via ChatGPT OAuth JWT (access token),
is authorized via per-tool scopes,
carries a validated user_id and correlation_id into the backend,
fails closed on any ambiguity (invalid token, missing scope, broken JWKS),
is compliant with OAuth 2.0 Bearer Token Usage (RFC 6750).
This increment is backend- & MCP-only. No changes in Google Calendar side.

2. Token Validation Requirements
Implement a reusable token validator in the MCP server (e.g. mcp_auth.py). It must:
2.1 Authorization Header

Read headers from MCP request metadata (_meta or equivalent).

Normalize all header keys to lowercase.
Extract:
authorization header

Expected format: Bearer <access_token>

Reject if:
header missing,
not starting with Bearer ,
token string is empty.
On failure: return 401 Unauthorized (see error format below).

2.2 JWKS Fetch & Caching
JWKS URL: https://www.priority-guard.com/oauth/focused/jwks

Use in-memory cache only (MCP remains stateless).

Cache TTL: 24 hours.

Max stale age: 7 days:
If cache is older than 7 days → treat as invalid, force refetch.
If refetch fails and cache is too old → reject tokens (fail closed).

Retry on unknown kid:
Decode step 1:
Parse JWT header, extract kid.
Look up key in cached JWKS.
If key not found:
Refetch JWKS once.
Retry key lookup and decode once.
If still not found → 401 invalid_token.

JWKS fetch timeout: ≤ 5 seconds.

2.3 JWT Verification Rules

Using the correct public key (resolved via kid), validate:
Algorithm: RS256

iss (issuer) must be:
 https://www.priority-guard.com/oauth/focused


aud (audience) must be:
 https://www.priority-guard.com/mcp/focused
exp (expiry):
Token must not be expired.

Additionally: reject tokens expiring in < 30 seconds from validation time (buffer).
nbf (if present) must not be in the future.

Extract from claims:
sub → user_id
scope → list of scopes (space-separated string in claim)
jti → token ID
azp → authorized party (client_id)

2.4 azp Validation

The azp claim MUST match the expected ChatGPT client_id for Focused.
That expected value must come from config (e.g. env var, settings file).
If azp mismatches or is missing → 401 invalid_token.

3. Scope Enforcement (Per Tool)
Scopes are defined as:
Tool
Required scope
check_calendar
focused.read
run_focus_mode
focused.write
watch_calendar
focused.write
notify_user
focused.notify

Rules:
Parse scope claim into a set of strings.
For each tool, ALL required scopes must be present.
If token is valid but scopes are insufficient → 403 insufficient_scope.

4. WWW-Authenticate (RFC 6750 Compliance)
All 401 and 403 responses MUST include a WWW-Authenticate header string in the error data.
For 401 (invalid token):
Header value:

 Bearer realm="https://www.priority-guard.com/oauth/focused", error="invalid_token", error_description="<reason>"

For 403 (insufficient scope):
Header value:

 Bearer realm="https://www.priority-guard.com/oauth/focused", error="insufficient_scope", scope="<required_scopes_space_separated>"

These strings must be included in the MCP error data as www_authenticate.

5. MCP Error Format (JSON-RPC Compatible)
When rejecting a tool call, MCP must return errors in this shape (structure, not exact text):

5.1 Unauthorized (401)
{
  "error": {
    "code": -32001,
    "message": "Unauthorized",
    "data": {
      "error": "invalid_token",
      "error_description": "Token expired",
      "www_authenticate": "Bearer realm=\"https://www.priority-guard.com/oauth/focused\", error=\"invalid_token\", error_description=\"Token expired\""
    }
  }
}

5.2 Forbidden (403 – insufficient scope)
{
  "error": {
    "code": -32002,
    "message": "Forbidden",
    "data": {
      "error": "insufficient_scope",
      "error_description": "Required ['focused.write'], got ['focused.read']",
      "required_scopes": ["focused.write"],
      "actual_scopes": ["focused.read"],
      "www_authenticate": "Bearer realm=\"https://www.priority-guard.com/oauth/focused\", error=\"insufficient_scope\", scope=\"focused.write\""
    }
  }
}

No token strings must be present in any error or logs.

6. Correlation ID Rules (7C Integration)

For every tool call:
Try to read correlation_id from _meta.correlation_id.
If missing, generate a new UUIDv4.
If present but malformed → ignore and generate new UUIDv4.

This correlation_id must be:
included in all MCP logs, sent to backend via X-Correlation-ID header on each REST call.
No tool call or backend call is allowed to proceed without a valid correlation_id.

7. User Identity Propagation

After successful token validation:
user_id = claims["sub"]

For each tool:
Use this user_id for logging.
Send user_id to backend via header: X-User-ID: <user_id>.
Do not read user_id from tool parameters.

8. Backend Migration Safety (CRITICAL)
We must avoid breaking existing backend behavior when 7D goes live.

8.1 Phase 1 (Increment 7D – THIS RELEASE)

MCP:
Validate token.
Extract user_id.

Send headers:
X-User-ID: <user_id>
X-Correlation-ID: <correlation_id>

Backend:
Must be updated to:
Read X-User-ID header and use it as primary source of user_id.
Still accept existing user_id sources (e.g. query param) as fallback for any older callers.

Log a warning if:

header is missing, or
header value and query param differ.
Do NOT remove or break the old query-param-based path in 7D.

8.2 Phase 2 (Future Increment – Backend Hardening)

Backend:
Continue reading X-User-ID header.
Keep reading query param only as fallback.
Gradually remove clients that rely on query param.
Log warnings when query param is used.


8.3 Phase 3 (Future Increment – Cleanup)

Backend:
Remove reading user_id from query params entirely.
Rely only on X-User-ID header (coming from MCP).
This is not part of 7D and must be a separate increment.

9. Manifest Changes (Security Schemes)
In manifest.json, each tool must declare OAuth scopes:
Example:
{
  "name": "check_calendar",
  "title": "Scan Calendar for Focus Blocks",
  "securitySchemes": [
    {
      "type": "oauth2",
      "scopes": ["focused.read"]
    }
  ]
}

Apply equivalent entries for:
run_focus_mode → ["focused.write"]
watch_calendar → ["focused.write"]
notify_user → ["focused.notify"]



10. File Changes (High-Level)

Under backend/apps/focused/:
mcp_auth.py (NEW)
JWT validation logic
JWKS fetch + caching
header extraction
error builders for Unauthorized / Forbidden
mcp_server.py (MODIFY)


For each tool:
extract headers
validate token
enforce scopes
obtain user_id + correlation_id
call backend with X-User-ID & X-Correlation-ID
manifest.json (MODIFY)
Add securitySchemes with required scopes.
logic.py / backend router (MODIFY)


Read X-User-ID (primary).
Still support old user_id query param (fallback).

Log warnings on mismatch / missing headers.
tests/
test_mcp_auth.py (unit tests for validator)
test_mcp_security.py (integration: tools + headers + error behavior)



11. Testing Requirements (High-Level)

Claude must at minimum cover:
Valid token, correct scopes → tool succeeds.
Missing Authorization header → 401 with proper WWW-Authenticate.
Invalid format (no Bearer) → 401.
Expired token → 401 + invalid_token + WWW-Authenticate.
Token expiring in <30s → rejected as 401.
Invalid signature / wrong issuer / wrong audience → 401.
Insufficient scope → 403 + insufficient_scope + required vs actual scopes in data.

Unknown kid:
First attempt fails with cached JWKS.
JWKS refetch,
Second attempt succeeds if new JWKS contains kid.
JWKS cache older than 7 days → force refetch.


Correlation ID:
When provided in _meta → propagated to logs and backend.
When missing → generated and propagated.

Backend migration:
- X-User-ID header set → backend uses this.
- If both header and query param present:
- header wins, mismatch triggers warning log.


12. Critical Implementation Rules for Claude (Do Not Deviate)
- Never log raw tokens or parts of them.
- Always validate iss, aud, exp, nbf, azp.
- Always enforce scopes before running tool logic.
- Always attach WWW-Authenticate for 401/403.
- Always pass X-User-ID and X-Correlation-ID to backend.
- MCP remains stateless: no DB/Redis calls from MCP.
- JWKS caching is in-memory only, with max 7-day stale limit + retry-on-unknown-kid.



