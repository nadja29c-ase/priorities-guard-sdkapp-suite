Both of Codex's substantive claims check out against the source. Here is the review with my adjudication.

  Codex's findings

  Correctness
  1. Minor — valid-token pass-through is correct by inspection but under-tested; tests assert only inner_called/status, not that
  scope/receive reach the inner app unchanged.
  2. No confirmed correctness defect in the 401 path.

  Production-readiness
  1. Major — unknown-kid tokens force a JWKS network refetch per request.
  2. Major — not deployed, so the production gates in the briefing are unrun.
  3. Minor — HEAD /mcp bypasses the auth gate and returns 200.

  Compliance
  1. Major — A22 cannot be marked fulfilled; live wire evidence is pre-fix.
  2. Minor — the 403 limb is N/A, not implemented; keep the CI guard.

  Adjudication

  Unknown-kid JWKS refetch — accepted, and worse than Codex framed it. Verified at mcp_server/clarity/mcp_auth.py:270-280 and :98-100:
  on cache miss for a kid, validate_jwt calls fetch_jwks(force=True), and force=True skips both the pre-lock and post-lock
  is_cache_valid() checks — so concurrent requests serialize on the lock and then each performs a real fetch. There is no cooldown or
  negative cache.

  What Codex didn't say: the kid is read at jwt.get_unverified_header(token) (step 1) and the JWKS fetch happens at step 3, before 
  signature verification at step 4. So an unauthenticated attacker needs only a syntactically well-formed JWT with a random kid and a
  garbage signature to drive an outbound fetch. That's an amplification vector, not just a latency concern.

  But: this is pre-existing shared code, unchanged by A22. authenticate_request already routed through it, so a dispatched tool call
  with an unknown kid always did this. What A22 changes is the reachable surface — from "dispatched tool calls" to "every request to
  /mcp, including tools/list and request classes that never dispatch." An amplification of an existing hole, not a new one.

  Per the briefing (Scope OUT: "Any shared clarity/ code") and RULE 0a, I am not fixing this. Flagging it as its own increment — and it
  touches every consumer of the shared validator, not just MindSort-Claude, so it should be scoped that way.

  HEAD /mcp — accurate read, but I'd downgrade it. Confirmed the ordering at server_dupl.py:837-841: HeadMcpMiddleware wraps
  OriginValidationMiddleware wraps BearerAuthMiddleware, so HEAD short-circuits at 200 before the gate. Three things temper it: the
  response body is empty — no catalogue, no information disclosure; the middleware exists for OpenAI's reachability probe and its own
  docstring already says Claude's HEAD behaviour is unconfirmed; and it's the same class of deliberate carve-out as /health, which also
  answers 200 unauthenticated. Codex's "if a Claude client uses HEAD for auth discovery" is speculation, and HEAD is not an MCP method
  — FastMCP returns 405 for it. Pre-existing, unchanged by A22, out of the briefing's scope. Log it.

  Under-tested pass-through — fair, and it's my test. The briefing's test list says "valid token → passes; inner app receives request
  unchanged," and I asserted the first clause but not the second. That's a real gap between spec and test, though not a defect in
  shipped behaviour. Your call whether to harden it now (it would mean amending the commits, so a new hash) or file it.

  The two "not deployed" findings are the same fact I raised before the review, and Codex independently reached the same disposition:
  A22 stays Not fulfilled until post-deploy probes show 401 + WWW-Authenticate + no-store and no catalogue leakage.

  Nothing here blocks the deploy. The decisions are yours: harden the pass-through test before pushing or file it, and whether the
  shared-validator kid issue gets an increment now or later.
