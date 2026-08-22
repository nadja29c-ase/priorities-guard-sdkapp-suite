Increment Briefing — A22 authentication fix, MindSort-Claude (canonical)
Objective

Move JWT validation to the HTTP-boundary middleware so invalid/expired/malformed bearer tokens are rejected with 401 + WWW-Authenticate before MCP dispatch or listing. Valid tokens pass through unchanged.

Problem (source-verified)

MindSort's BearerAuthMiddleware (mcp_server/mindsort_claude/server_dupl.py) checks only header presence. An expired token carries a header, passes the gate, reaches dispatch; authenticate_request (shared clarity/mcp_auth.py) catches jwt.ExpiredSignatureError → UnauthorizedError → dispatcher returns HTTP 200 + isError:true with build_unauthorized_meta() (OpenAI-convention mcp/www_authenticate Claude doesn't read). User sees "Authentication required" as text, no Connect button. A22 (DOC-CONSTRAINT ⚠️SILENT).

Approach — Copy and Adjust, Never Rewrite

Port PG-Claude's validating BearerAuthMiddleware (its "A22a" work). Source: mcp_server/priority_guardian_claude/server_dupl.py, verified this session to contain await validate_jwt(...) with except jwt.PyJWTError → 401, except Exception → 503. Do not redesign.

Source-verification checks (do these first, fold results into the work)
CHECK A — tools/list exposure: confirm from source whether MindSort's tools/list (list_tools handler) is currently guarded only by the presence-only middleware and does NOT pass through authenticate_request. If so, an invalid token can currently reach tools/list and return the catalogue at 200 — the exposure the invalid-token tools/list test (below) closes. If tools/list has some other guard, adjust the test's framing accordingly. Do not assert "catalogue leak closed" without confirming the pre-fix exposure exists.
CHECK B — advertised tool set: open mcp_server/mindsort_claude/tools_list_dupl.py; identify the authoritative Claude-advertisement constant (e.g. CLAUDE_ADVERTISED_TOOLS or the allowlist list_tools_for_claude builds from). Determine which tools are actually advertised and whether save_board is an unadvertised scope-map tombstone. The CI guard (below) scopes to this real set — do not hardcode a count.
CHECK C — import path: confirm the exact PG import for extract_bearer_token/validate_jwt and mirror against mcp_server.mindsort_claude.mcp_auth_dupl.
CHECK D — deploy predecessor: confirm MindSort config has NO MAX_MCP_BODY_SIZE_BYTES dependency introduced (auth-only port doesn't need it; flag if PG's block references it and you're extracting around it).
Scope

In: authentication — token validity (signature, expiry, issuer, audience, JWKS, malformed/duplicate header) at middleware, 401 before dispatch/listing.

OUT (do not include):

413/body-size guard. PG's middleware interleaves the P1-b body-buffer/replay with the valid-token pass-through. The valid-token outcome must be reconstructed: replace PG's entire tail from the MAX_MCP_BODY_SIZE_BYTES import onward with a single await self.app(scope, receive, send). Do NOT port _BodyTooLargeError, _send_413, _create_replay_receive, the bytearray buffering, or the Content-Length preflight. If MindSort lacks a body-size limit, that is a separate future increment — log, don't bundle.
Tool-scope authorization. Stays dispatcher-level. Unchanged — see the N/A note below.
Audience-config anomaly (CLARITY_AUDIENCE issuer-shaped in prod, their §11, affects both Claude connectors). Separate, out of scope.
Any shared clarity/ code. build_unauthorized_meta() is correct for OpenAI; on Claude it becomes unreachable once middleware 401s first. No OpenAI behavior change.
Insufficient-scope: currently N/A, not "correct"

Insufficient-scope handling remains unchanged (dispatcher-level 200+isError). That response shape would NOT satisfy A22 if the condition became reachable — A22 distinguishes 401 auth-failure from 403 insufficient_scope, and 200+isError triggers no Claude auth UX. It is currently N/A for MindSort-Claude because every advertised tool and the OAuth flow use the single clarity.write scope (verified: TOOL_SCOPES all ["clarity.write"]; SCOPES_SUPPORTED == ["clarity.write"], backend-mirrored, test_clarity_scope.py-pinned). If differentiated scopes are ever introduced, this path becomes reachable and A22 must be revisited for the authorization limb.

Changes

1. mindsort_claude/mcp_auth_dupl.py: add extract_bearer_token, validate_jwt to the from mcp_server.clarity.mcp_auth import (...) block. NOT in REBOUND_GLOBALS (that's config-values only). Confirm the AST/drift meta-test still passes.

2. mindsort_claude/server_dupl.py: replace presence-only BearerAuthMiddleware with PG's validating version, porting select_authorization_header, _DuplicateAuthorizationError, _send_challenge. Outcomes: no/bad-format/invalid/expired/duplicate → 401+WWW-Authenticate; JWKS-down → 503 no challenge; valid → pass through (reconstructed plain await self.app(...), per Scope §1). Adjust imports priority_guardian_claude.* → mindsort_claude.*; reuse MindSort's WWW_AUTHENTICATE_VALUE (scope="clarity.write"). Update _send_challenge's docstring: PG's says scope="pg.access" — change to clarity.write (stale-comment guard). Preserve MindSort's existing middleware order (no LifespanMiddleware).

Tests

Unit (assembled stack — drive the real middleware, not the function alone):

expired token → 401 + WWW-Authenticate present/correct; dispatch not reached. (Weak-test trap: "not 200" without asserting the header — Claude needs it to re-auth.)
invalid JWT + tools/list → 401 + correct WWW-Authenticate; NO tool catalogue returned; listing logic not reached. (The discriminating test — proves validation covers un-dispatched request classes. Framing conditional on CHECK A confirming the pre-fix exposure.)
invalid-signature / wrong-issuer / wrong-audience / unknown-kid → 401.
absent header → 401 (preserved).
malformed header (Bearer empty / wrong scheme) → 401, never 500.
duplicate Authorization headers → 401.
JWKS-unavailable → 503, no challenge.
valid token → passes; inner app receives request unchanged.
Pin Cache-Control: no-store on the 401 challenge responses (PG's _send_challenge sets it; PG's wire verification pinned it).

CI guard (unreachability invariant — import the source of truth, don't duplicate names):

Import the authoritative Claude-advertisement constant identified in CHECK B. For every advertised tool, assert TOOL_SCOPES[tool] == ["clarity.write"]. Assert SCOPES_SUPPORTED == ["clarity.write"]. Do NOT iterate all TOOL_SCOPES entries (would false-fire on the save_board tombstone). Fails loudly if a newly advertised tool carries a different scope or SCOPES_SUPPORTED grows — forcing A22's authz limb to be revisited. This encodes "insufficient-scope currently unreachable."
Production-readiness gates (the architectural change puts JWKS validation on every protected request — false rejection and latency are the primary risks)
Verify validate_jwt uses the existing _jwks_cache fast path and does not perform a network JWKS fetch per request (source shows cache-hit path; confirm in deployment).
Record cache-hit validation latency; observe cold-cache / JWKS-fetch behavior.
Verify transient JWKS failure → 503, no re-auth loop.
Post-deploy valid-token wire/host test: reconnect normally; initialize + tools/list succeed; representative tool calls succeed. (Catches the over-eager-middleware failure: rejecting good tokens.)
Rollback if valid users are rejected or auth latency materially regresses.
Deploy

Server change, no WIDGET_VERSION bump. Redeploy MindSort-Claude MCP on Render; confirm deployed SHA in Events/Deploys. Read doc/OPERATIONS_PREDEPLOY.md first; include auth + guard tests in the pre-deploy run.

Assessment reconciliation (timing matters)
Now (fix undeployed): A22 = Not fulfilled. Note: "presence-only gate; reachable via expired-token-after-failed-refresh → 200+isError → no prompt; PG fixed as A22a; fix is verified auth-only port; insufficient-scope N/A under single-scope, CI-pinned; not review-reachable; ⚠️SILENT."
After deploy + valid-token gate passes: A22 401-limb → Fulfilled; 403 insufficient-scope limb documented N/A until differentiated scopes exist. Do NOT pre-mark Fulfilled before the post-deploy gate passes (committed ≠ live).
Also this session: M10 → Partly (confirm main.css:44), M4/M6 contested-note.
Report back

Commit hash; CHECK A–D results; meta-test result after re-export; confirmation the 413 path was NOT ported and the valid-token pass-through was reconstructed; _send_challenge docstring updated; production-gate observations (latency, valid-token admission, 503 behavior); what was NOT verified.

That's the canonical, production-ready version. The four ChatGPT edits are in (invalid-token tools/list test, advertised-scoped CI guard, production/JWKS/latency/rollback gates, N/A-not-"correct" wording), plus your import-the-allowlist refinement, plus the two source-verification checks (A: tools/list exposure, B: advertised set) folded in as work-items rather than blockers, plus the two things my deeper PG read surfaced (reconstruct the valid-token pass-through since the 413 is entangled not appended; fix the pg.access docstring).

It's not submission-gating — ships after or parallel to submission — and it's now specified for correctness, compliance, and production-readiness in context, not just correctness. Hand this version to Claude Code.