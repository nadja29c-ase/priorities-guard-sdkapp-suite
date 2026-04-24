Claude Code Briefing — Increment B2-7: Full HTTP-layer MCP auth compliance (401 + 403)
Goal
Bring PG into full MCP authorization spec compliance at the HTTP layer:

HTTP 401 + WWW-Authenticate for missing, malformed, or invalid JWTs on /mcp endpoints
HTTP 403 + WWW-Authenticate (error="insufficient_scope") for valid JWTs that lack the required scopes for the requested tool

After this increment, PG's MCP server will satisfy:

MCP spec 2025-06-18 §2: "Invalid or expired tokens MUST receive a HTTP 401 response" and "Servers MUST return appropriate HTTP status codes for authorization errors"
OpenAI Apps SDK auth docs: "If verification fails, respond with 401 Unauthorized and a WWW-Authenticate header that points back to your protected-resource metadata"

Scope
In scope:

Extend existing BearerAuthMiddleware in mcp_server/priority_guardian/server.py to:

Validate JWT signature, iss, aud, exp at the HTTP layer → HTTP 401 on failure
Parse JSON-RPC body for tools/call requests, extract tool name, enforce required scopes → HTTP 403 on scope failure


Unit tests for both 401 and 403 paths
Integration tests that exercise both paths end-to-end across POST, GET, and DELETE

Out of scope — do NOT touch:

handlers/tools.py — the existing _meta["mcp/www_authenticate"] mechanism stays. Once middleware enforces auth, the dispatcher's auth call in practice becomes a fallback for any path that bypasses middleware (direct calls, tests). OpenAI docs say the _meta mechanism is required to trigger the tool-level OAuth UI, so keeping it is correct even when HTTP 401/403 also fires.
mcp_auth.py functions (validate_jwt, authenticate_request, enforce_tool_scope, error builders) — reuse them
Any tool handler
Backend OAuth provider
Discovery endpoints
MindSort/Clarity server (separate increment B2-7c, after its submission resolves)

Architectural decision
Validate JWT and enforce scopes at the ASGI middleware layer before FastMCP processes the request. For scope enforcement, parse the JSON-RPC request body to extract the tool name, then look up required scopes in TOOL_REGISTRY.
Why this approach over alternatives:

Response buffering + status rewriting (rejected): adds latency to every tool call, fragile with streaming responses, duplicates logic already in mcp_auth.py
Dispatcher raises exception → middleware catches (rejected): FastMCP serializes JSON-RPC errors internally before middleware sees them; by the time the response reaches middleware, it's already 200 OK
Parse request body in middleware (chosen): request bodies are small, parsing is deterministic, clean HTTP response without buffering output

The same middleware handles both 401 (token invalid) and 403 (scope insufficient) because both require the same machinery: JWT extraction + validation.
Files to modify

mcp_server/priority_guardian/server.py — extend BearerAuthMiddleware
tests/unit/mcp_priority_guardian/test_pg_mcp_auth.py — add middleware tests
tests/integration/ — add integration tests for 401 and 403 paths

Implementation constraints
Middleware behavior
Scope of middleware (which requests it inspects):

POST /mcp, GET /mcp, DELETE /mcp — matching existing BearerAuthMiddleware scope
All other paths pass through untouched — discovery, /health, /, OAuth proxy routes

Authentication and authorization policy:

JWT validation (steps 1–3 below) applies to all in-scope requests
Scope enforcement (step 4 below) applies only to JSON-RPC requests where method == "tools/call"
Do not enforce scope on any other JSON-RPC method; the middleware's job is auth + scope-for-tool-calls, nothing more

On POST /mcp, the middleware runs this decision sequence:

Body size guard (pre-flight): Check Content-Length header. If present and > 1 MB, or if streaming body exceeds 1 MB during buffering, return HTTP 413 Payload Too Large with body {"error": "payload_too_large", "error_description": "Request body exceeds maximum size"} and do not pass to inner app. Legitimate MCP tool-call bodies are a few KB at most; this is a hard reject, not a bypass. Log auth.middleware.rejected with reason=body_too_large and size_bytes.
If Authorization header missing → HTTP 401, reason=missing_header
If Authorization header present but not Bearer <token> → HTTP 401, reason=invalid_format
Call validate_jwt(token, correlation_id):

Raises jwt.ExpiredSignatureError → HTTP 401, reason=token_expired
Raises jwt.InvalidTokenError or other → HTTP 401, reason=invalid_token
Returns validated claims → continue


Peek at request body (JSON-RPC parse):

Read body, parse as JSON
If not JSON, or missing method field, or method != "tools/call" → let the request through unchanged (JWT already validated in step 3; no scope check needed)
If method == "tools/call":

Extract params.name as the tool name
Look up TOOL_REGISTRY[tool_name].required_scopes
If tool not in registry → let the request through (FastMCP will return "unknown tool" via the dispatcher — not a 403 concern)
If required_scopes is empty → let the request through (no scope enforcement needed)
If token's scopes do not include all required scopes → HTTP 403, reason=insufficient_scope
Otherwise → let the request through




Request passes to inner app with unmodified scope and body (body must be re-playable — see below)

On GET /mcp and DELETE /mcp:
Steps 0–3 only. No body parsing (no tool call). GET /mcp opens an SSE stream, DELETE /mcp closes a session — neither has a tool-call body.
Body replay requirement
ASGI receive is a generator. Reading the body consumes it. To let the request continue to FastMCP with the body intact, the middleware must:

Buffer the full body from receive() calls, tracking cumulative size
If cumulative size exceeds 1 MB during buffering, stop and return HTTP 413 (see step 0 above)
Construct a new receive callable that replays the buffered body
Pass the replay receive to the inner app

Standard ASGI pattern. Empty bodies must replay correctly (some probes send zero-byte bodies). The replayed message must include more_body: False on the final chunk.
WWW-Authenticate header format
Match the format already used in build_unauthorized_meta() / build_forbidden_meta() in mcp_auth.py. Use the existing _MCP_ORIGIN constant for the resource_metadata URL.
For 401 responses:
Bearer resource_metadata="<_MCP_ORIGIN>/.well-known/oauth-protected-resource", error="invalid_token", error_description="<description>"
error_description:

Missing header → "Authentication required"
Invalid format → "Invalid Authorization header format"
Expired → "Token expired"
Other invalid → "Token validation failed"

For 403 responses:
Bearer resource_metadata="<_MCP_ORIGIN>/.well-known/oauth-protected-resource", error="insufficient_scope", error_description="Insufficient permissions", scope="<space-separated-required-scopes>"
The scope parameter is optional per RFC 6750 but helpful — it tells the client what scopes would be needed. Include the required scopes for the tool that triggered the 403.
Response body
401:
json{"error": "unauthorized", "error_description": "<matching description>"}
403:
json{"error": "insufficient_scope", "error_description": "Insufficient permissions for tool '<tool_name>'", "required_scopes": ["scope1", "scope2"]}
413:
json{"error": "payload_too_large", "error_description": "Request body exceeds maximum size"}
Headers for all: content-type: application/json, cache-control: no-store.
Middleware ordering (unchanged)
Current stack (outermost to innermost):

RequestLoggingMiddleware
HeadMcpMiddleware
LifespanMiddleware
BearerAuthMiddleware ← extend this
MCPContentTypeAndAcceptFixMiddleware
fastmcp_app

Do not change the order. Extended BearerAuthMiddleware must still run before MCPContentTypeAndAcceptFixMiddleware so rejected requests never reach the content-type/auth-capture layer.
Important: BearerAuthMiddleware must NOT set the auth_header_var context var. That remains MCPContentTypeAndAcceptFixMiddleware's responsibility. Preserve the separation of concerns.
Reuse existing code

extract_bearer_token() from mcp_auth.py — header parsing
validate_jwt() from mcp_auth.py — JWT validation
check_scopes() from mcp_auth.py — scope subset check
extract_or_generate_correlation_id(None) — correlation ID generation
_MCP_ORIGIN from mcp_auth.py — resource_metadata URL
TOOL_REGISTRY from tools/ — look up required scopes (late import inside the middleware method, matching the pattern enforce_tool_scope() already uses to avoid circular imports)

Things that must NOT break

Discovery endpoints (/.well-known/*) reachable unauthenticated
Health endpoints (/, /health) reachable unauthenticated
OAuth proxy routes (/oauth/*) reachable unauthenticated
HEAD /mcp probe behavior intact (HeadMcpMiddleware short-circuits before auth)
JSON-RPC methods other than tools/call pass through after JWT validation without scope enforcement
Tools with empty required_scopes must pass through without scope enforcement
Malformed JSON-RPC bodies must pass through to FastMCP (let FastMCP return the protocol error — middleware's job is auth, not syntax)
Empty-body requests (e.g., GET /mcp SSE initiation) must replay correctly to inner app
Tool-handler auth path (_meta["mcp/www_authenticate"]) still functional as a fallback

Logging
Every rejection from the middleware emits one structured log at WARNING:

event: auth.middleware.rejected
method: HTTP method
path: /mcp
status: 401, 403, or 413
reason: one of missing_header, invalid_format, token_expired, invalid_token, validation_error, insufficient_scope, body_too_large
correlation_id: generated for this rejection
For insufficient_scope: additionally tool_name, required_scopes, actual_scopes
For body_too_large: additionally size_bytes

Do NOT log tokens, any portion of tokens, or request body content beyond the tool name.
validate_jwt emits its own jwt.validation.* logs internally — do not suppress.
Testing
Unit tests — tests/unit/mcp_priority_guardian/test_pg_mcp_auth.py
Each test constructs a minimal ASGI scope dict and invokes the middleware directly with a mocked inner app. For JWT cases, sign test tokens following the existing pattern in this file. For body-parsing cases, pass a receive callable that emits a mock JSON-RPC body.
401 cases:

No Authorization header → 401, WWW-Authenticate with error="invalid_token", inner app not called, log reason=missing_header
Header not Bearer ... → 401, reason=invalid_format
Bearer <malformed> → 401, reason=invalid_token
Bearer <valid-but-expired> → 401, reason=token_expired
Bearer <valid-but-wrong-iss> → 401, reason=invalid_token
Bearer <valid-but-wrong-aud> → 401, reason=invalid_token
Path /.well-known/oauth-protected-resource → passes through without validation
Path /health → passes through without validation

403 cases:
9. Bearer <valid> + body {"method": "tools/call", "params": {"name": "create_priority"}} + token has required_scopes → inner app called, no rejection log
10. Bearer <valid> + body {"method": "tools/call", "params": {"name": "create_priority"}} + token missing required scope → 403, WWW-Authenticate with error="insufficient_scope", scope="<required>", reason=insufficient_scope, log includes tool_name=create_priority, required_scopes, actual_scopes
11. Bearer <valid> + body {"method": "tools/call", "params": {"name": "nonexistent_tool"}} → inner app called (FastMCP handles unknown tool)
12. Bearer <valid> + body {"method": "initialize"} → inner app called, no scope check attempted
13. Bearer <valid> + body {"method": "tools/list"} → inner app called, no scope check attempted
14. Bearer <valid> + malformed JSON body → inner app called (FastMCP handles protocol error)
15. Bearer <valid> + body exceeds size cap (1 MB) → HTTP 413, inner app not called, log reason=body_too_large with size_bytes
16. Bearer <valid> + valid body → body correctly replayed to inner app with more_body: False on final chunk (assert by capturing the receive callable's output in the inner app mock)
17. Bearer <valid> + empty body → inner app called, replayed body is empty, more_body: False set correctly
Integration tests — tests/integration/
Spin up the real app via create_app() and hit it with an ASGI test client. These tests verify middleware behavior in the real stack — they do not test tool execution semantics.

POST /mcp without Authorization → 401 with WWW-Authenticate: Bearer ..., error="invalid_token"
POST /mcp with Bearer invalid → 401
POST /mcp with Bearer <signed-but-expired> → 401 with error="invalid_token" in challenge
POST /mcp with Bearer <valid-but-missing-scope> + tools/call body → 403 with error="insufficient_scope" in challenge, required scope listed
POST /mcp with Bearer <valid-with-correct-scope> + tools/call body → response is not 401 and not 403 (pass-through assertion only; do not assert on tool behavior, payload, or inner app state — that is not this increment's concern)
POST /mcp with Bearer <valid> + initialize body → not 401 and not 403 (pass-through, no scope check)
POST /mcp with body > 1 MB → 413, inner app not called
GET /mcp without Authorization → 401 with WWW-Authenticate (proves middleware enforces auth on SSE stream initiation path, not just POST)
DELETE /mcp without Authorization → 401 with WWW-Authenticate (proves middleware enforces auth on session-close path)
HEAD /mcp without Authorization → 200 (HeadMcpMiddleware short-circuits before BearerAuthMiddleware)
GET /.well-known/oauth-protected-resource → 200 (middleware doesn't interfere with discovery)

Pre-deploy
Read doc/OPERATIONS_PREDEPLOY.md before committing.

No Alembic migrations (code-only change)
Run the OAuth discovery sanity check after deploy to confirm nothing downstream broke
No env var changes

Post-deploy verification
On production PG (pg.priority-guard.com):

curl -X POST https://pg.priority-guard.com/mcp -H "Content-Type: application/json" -d '{}' → expect 401 with WWW-Authenticate header
curl -X POST https://pg.priority-guard.com/mcp -H "Authorization: Bearer invalid" → expect 401
Reconnect PG in ChatGPT → full OAuth flow must complete
Execute a real tool call → must succeed
To verify 403: use a dev-issued token with no scopes against a scoped tool → expect 403. If staging is available, verify there first.
To verify 413: curl -X POST ... -d "$(python -c 'print("x" * 2000000)')" → expect 413
Check Render logs for auth.middleware.rejected events with status=401 for unauthenticated probes
Confirm no unexpected 403 appears for legitimate traffic (if it does, scope assignment is broken — investigate immediately)

Rollback
Pure additive middleware change, no data or config. If ChatGPT breaks: revert server.py and redeploy. No DB migration, no env vars.
Acceptance criteria

 All 17 unit test cases pass
 All integration test cases pass (POST, GET, DELETE auth failure paths all covered)
 POST/GET/DELETE /mcp with missing/invalid/expired JWT returns HTTP 401 + WWW-Authenticate (integration-tested for all three methods; verified on PG production for POST)
 POST /mcp tools/call with valid JWT but insufficient scope returns HTTP 403 + WWW-Authenticate with error="insufficient_scope" on PG production
 POST /mcp with body > 1 MB returns HTTP 413 (no scope-enforcement bypass exists)
 Valid JWT with correct scope passes through to inner app (no 401, no 403)
 JSON-RPC methods other than tools/call pass through after JWT validation without scope enforcement
 Discovery, health, OAuth proxy, HEAD /mcp all functional unchanged
 Tool-handler _meta path still functional (existing tests pass)
 ChatGPT connector flow works end-to-end for PG
 auth.middleware.rejected logs include correct fields; no tokens logged
 No backend changes, no env var changes

Non-goals for this increment

MindSort/Clarity — deferred to B2-7c (post-submission). The middleware pattern from this increment will be copy-adapted to MindSort after its current OpenAI submission resolves.

