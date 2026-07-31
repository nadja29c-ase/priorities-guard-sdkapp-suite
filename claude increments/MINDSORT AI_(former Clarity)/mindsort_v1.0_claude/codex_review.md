 Part A — Evidence report

  Working tree SHA 1532b7d9845782689fa3c612bdb69bfb9b1e5f3d, branch main, tracking origin/main. Clean except this briefing
  (untracked). No code changed — Part A is read-only, and I made no Render writes per §0.1(c).
  
  ⚠️  Finding that threatens Part B's deployability — not in the briefing

  The shared backend's Render build command references a file that no longer exists in the repository.

  - Build command: pip install -r requirements_fullbackend.txt
  - That file was deleted in 02e589a, 2026-04-24 — "chore: remove requirements_fullbackend.txt; poetry is sole source of truth"
  - It exists at neither HEAD nor the deployed SHA, is not gitignored, and has no other tracked path
  - Four live services still build with it: shared backend, Celery worker, pg-mcp, clarity-mcp. Only mindsort-claude-mcp was
  migrated (poetry install --no-root --only main)

  The puzzle I could not resolve: the last backend deploy (2026-07-07) succeeded and is live, yet the removal predates it by
  ten weeks. Build logs for that window are no longer retained, so I can't tell whether the build command differed then or
  something else explains it.

  Why this matters to §0.1: the entire premise is "deploy Part B to reduce review-failure probability." If the next backend
  build fails, Part B cannot deploy — and gate conditions 5 (rollback prepared and tested) and 6 (post-deploy checks) are
  unsatisfiable, because rollback also requires a successful build. Reporting, not acting — fixing it means writing Render
  config, which §0.1(c) forbids.

  Steps 1–2 — SHAs and drift
  
  Deployed backend SHA: 0b05a69ab9507ba355596e15cc03a7396a324013 (committed 2026-07-06, deployed manually 2026-07-07, trigger
  manual).
  
  24 days stale by date, but zero drift in substance:
  
  ┌─────────────────────────────────────────────────────────┬─────────────┐
  │                          Check                          │   Result    │
  ├─────────────────────────────────────────────────────────┼─────────────┤
  │ Commits touching backend/ between deployed SHA and HEAD │ 0           │
  ├─────────────────────────────────────────────────────────┼─────────────┤
  │ backend/core/config.py                                  │ identical   │
  ├─────────────────────────────────────────────────────────┼─────────────┤
  │ client_metadata.py                                      │ identical   │
  ├─────────────────────────────────────────────────────────┼─────────────┤
  │ authorize.py                                            │ identical   │
  ├─────────────────────────────────────────────────────────┼─────────────┤
  │ Alembic migrations                                      │ no drift    │
  ├─────────────────────────────────────────────────────────┼─────────────┤
  │ pyproject.toml / poetry.lock / alembic.ini              │ identical   │
  ├─────────────────────────────────────────────────────────┼─────────────┤
  │ alembic heads                                           │ 1 (no fork) │
  └─────────────────────────────────────────────────────────┴─────────────┘

  47 files differ outside backend/ (mcp_server, docs, tests) — carried in the image, not on the backend's runtime path. Gate 
  condition 7 is satisfiable: a Part B deploy would ship only Part B's backend delta.
  
  §0.1(a) — auto-deploy evidence (raw API reading)

  ┌────────────────────────────────────────┬──────────────────────────┬────────────┬─────────────────────┐
  │                Service                 │            ID            │ autoDeploy │       Trigger       │
  ├────────────────────────────────────────┼──────────────────────────┼────────────┼─────────────────────┤
  │ priorities-guard-sdkapp-shared-backend │ srv-d4o3lke3jp1c73f3ppk0 │ no         │ off                 │
  ├────────────────────────────────────────┼──────────────────────────┼────────────┼─────────────────────┤
  │ priority-guardian-claude-mcp           │ srv-d6vbrt9r0fns73c6n080 │ no         │ off                 │
  ├────────────────────────────────────────┼──────────────────────────┼────────────┼─────────────────────┤
  │ priorities-guard-mindsort-claude-mcp   │ srv-d90din3sq97s7399nbl0 │ yes        │ commit, branch main │
  ├────────────────────────────────────────┼──────────────────────────┼────────────┼─────────────────────┤
  │ priorities-guard-celery                │ srv-d4o4vb4hg0os73a3ump0 │ no         │ off                 │
  ├────────────────────────────────────────┼──────────────────────────┼────────────┼─────────────────────┤
  │ priorities-guard-pg-mcp                │ srv-d64ea0khg0os73d588t0 │ no         │ off                 │
  ├────────────────────────────────────────┼──────────────────────────┼────────────┼─────────────────────┤
  │ prioritiy-guard-mindsort-mcp           │ srv-d4vg1c24d50c73814mi0 │ no         │ off                 │
  ├────────────────────────────────────────┼──────────────────────────┼────────────┼─────────────────────┤
  │ priorities-guard-focused-mcp           │ srv-d4o4jr6mcj7s738vjap0 │ yes        │ (suspended)         │
  ├────────────────────────────────────────┼──────────────────────────┼────────────┼─────────────────────┤
  │ priorities-guard-sharpen-mcp           │ srv-d5jrpbqli9vc73bm0kog │ no         │ (suspended)         │
  └────────────────────────────────────────┴──────────────────────────┴────────────┴─────────────────────┘
  
  Part B on main will not deploy. Part C on main deploys instantly — branch-isolate it.
  
  Step 3 — Production discovery

  Both PRM documents (root and /mcp) are identical per server and internally consistent:
  
  - PG-Claude → resource: https://mcp.priority-guard.com/mcp, AS https://www.priority-guard.com, scopes ["pg.access"]
  - MindSort-Claude → resource: https://mindsort-mcp.priority-guard.com/mcp, same AS, scopes ["clarity.write"]
  - AS document → issuer https://www.priority-guard.com, endpoints all under /oauth/pg/*, S256 only,
  token_endpoint_auth_methods_supported: ["none"]

  No hard-stop condition triggered. Since backend/ is identical between deployed SHA and HEAD, production discovery necessarily
  matches what the deployed SHA produces.
  
  Steps 4–5 — Validator call sites and authorize matching
  
  One production call site: register_client.py:124 calling validate_redirect_uris(...) with
  allowed_uris=settings.OAUTH_ALLOWED_REDIRECT_URIS at :126. Everything else is tests (test_normalize_redirect_uri.py,
  test_b2_compliance_unit.py — the latter has ~20 call sites forming the ChatGPT non-regression suite §6.4 needs). Type
  contract confirmed: list[str] at config.py:70, built at :174.

  Step 5 confirmed — authorize.py:528-532 builds normalized_registered from client.redirect_uris (the client's own rows) and
  rejects with invalid_redirect_uri at :535 when normalized_redirect not in normalized_registered. Exact set membership against
  the client's registrations, not the global allowlist. §0.2's two-layer model is correct.

  Step 6 — PyJWT aud semantics: exact string comparison, proven

  mcp_server/clarity/mcp_auth.py:303-316:
  valid_audiences = [MCP_RESOURCE_URL, MCP_SERVER_URL, CLARITY_AUDIENCE]
  payload = jwt.decode(token, signing_key.key, algorithms=["RS256"],
                       issuer=CLARITY_ISSUER, audience=valid_audiences,
                       leeway=TOKEN_EXPIRY_GRACE_SECONDS, options={... "verify_aud": True ...})
  
  PyJWT 2.10.1. Source (api_jwt.py:365-410) normalizes both sides to lists and set-intersects. Empirically confirmed with real
  RS256 tokens:
  
  ┌─────────────────────────┬─────────────────────────────────┐
  │          Case           │             Result              │
  ├─────────────────────────┼─────────────────────────────────┤
  │ exact match             │ ACCEPTED                        │
  ├─────────────────────────┼─────────────────────────────────┤
  │ trailing slash differs  │ rejected (InvalidAudienceError) │
  ├─────────────────────────┼─────────────────────────────────┤
  │ case differs            │ rejected                        │
  ├─────────────────────────┼─────────────────────────────────┤
  │ prefix only             │ rejected                        │
  ├─────────────────────────┼─────────────────────────────────┤
  │ member of accepted list │ ACCEPTED                        │
  └─────────────────────────┴─────────────────────────────────┘

  §7.1's byte-exact, no-canonicalization requirement is correct — a guard tolerating trailing slashes or case would pass
  configs the validator then rejects at runtime.

  Step 7 — JWKS fixture feasibility: yes, pattern exists

  tests/unit/mcp_priority_guardian/test_jwt_grace_period.py:80-87 patches _jwks_cache, mocks fetch_jwks to a no-op and
  get_signing_key to return a test public JWK, signing synthetic tokens with a module-level RSA key and kid: test-key-id.
  Directly reusable for Part E layer 1 against both Claude servers. Part E is not blocked.

  Step 8 — Production DCR log check (30-day window)

  No loopback DCR attempts and no rejections. Across 2026-07-01 → now:

  - 3 × oauth.register.success, all client_name: "Claude" (2026-07-21 pg-c****b5ad; 2026-07-23 pg-c****30bd, pg-c****bd1f),
  each redirect_uris_count: 1
  - Zero localhost / 127.0.0.1 / ::1 in any redirect URI
  - Zero invalid_redirect_uri, zero DCR 400s
  - Every Claude authorize uses https://claude.ai/api/mcp/auth_callback; every ChatGPT one uses
  https://chatgpt.com/connector/oauth/i3aGemPmx9rv

  Notable: in the last ~10 days I see no authorize request carrying resource=https://mcp.priority-guard.com/mcp (PG-Claude's
  resource). Every Claude flow carries MindSort-Claude's resource; every pg.access flow is the ChatGPT connector.

  Which row applies — with attribution uncertainty stated as required: the evidence best fits row 2, "No completed reviewer 
  OAuth flow yet → upside High." Caveats, explicitly: log attribution to a reviewer is not possible (no distinguishing
  user-agent on oauth.* events); pagination returned hasMore: true before 2026-07-21, so I have full coverage only of the last
  ~10 days; and reviewer traffic might not reach this backend at all if review is still at documentation stage. Row 3 ("cannot 
  be shown to be low") is the defensible fallback if you want the conservative reading. Presenting evidence only — no deploy
  recommendation, per §0.1.
  Step 3 — Production discovery

  Both PRM documents (root and /mcp) are identical per server and internally consistent:

  - PG-Claude → resource: https://mcp.priority-guard.com/mcp, AS https://www.priority-guard.com, scopes ["pg.access"]
  - MindSort-Claude → resource: https://mindsort-mcp.priority-guard.com/mcp, same AS, scopes ["clarity.write"]
  - AS document → issuer https://www.priority-guard.com, endpoints all under /oauth/pg/*, S256 only,
  token_endpoint_auth_methods_supported: ["none"]

  No hard-stop condition triggered. Since backend/ is identical between deployed SHA and HEAD, production discovery necessarily
  matches what the deployed SHA produces.

  Steps 4–5 — Validator call sites and authorize matching

  One production call site: register_client.py:124 calling validate_redirect_uris(...) with
  allowed_uris=settings.OAUTH_ALLOWED_REDIRECT_URIS at :126. Everything else is tests (test_normalize_redirect_uri.py,
  test_b2_compliance_unit.py — the latter has ~20 call sites forming the ChatGPT non-regression suite §6.4 needs). Type
  contract confirmed: list[str] at config.py:70, built at :174.

  Partially established. Shared backend: numInstances: 1, plan starter, healthCheckPath: "/health" configured. PG-Claude MCP:
  numInstances: 1, healthCheckPath: "" — none configured. A configured health check is what lets Render gate a cutover, so the
  backend is better positioned for a clean rollover than PG-Claude. I could not verify Render's exact zero-downtime semantics
  for single-instance starter services from here — treat this as suggestive, not established.


  mcp_server/clarity/mcp_auth.py:303-316:
  valid_audiences = [MCP_RESOURCE_URL, MCP_SERVER_URL, CLARITY_AUDIENCE]
  payload = jwt.decode(token, signing_key.key, algorithms=["RS256"],
                       issuer=CLARITY_ISSUER, audience=valid_audiences,
                       leeway=TOKEN_EXPIRY_GRACE_SECONDS, options={... "verify_aud": True ...})

  PyJWT 2.10.1. Source (api_jwt.py:365-410) normalizes both sides to lists and set-intersects. Empirically confirmed with real
  RS256 tokens:

  ┌─────────────────────────┬─────────────────────────────────┐
  │          Case           │             Result              │
  ├─────────────────────────┼─────────────────────────────────┤
  │ exact match             │ ACCEPTED                        │
  ├─────────────────────────┼─────────────────────────────────┤
  │ trailing slash differs  │ rejected (InvalidAudienceError) │
  ├─────────────────────────┼─────────────────────────────────┤
  │ case differs            │ rejected                        │
  ├─────────────────────────┼─────────────────────────────────┤
  │ prefix only             │ rejected                        │
  ├─────────────────────────┼─────────────────────────────────┤
  │ member of accepted list │ ACCEPTED                        │
  └─────────────────────────┴─────────────────────────────────┘

  §7.1's byte-exact, no-canonicalization requirement is correct — a guard tolerating trailing slashes or case would pass
  configs the validator then rejects at runtime.

  Step 7 — JWKS fixture feasibility: yes, pattern exists

  tests/unit/mcp_priority_guardian/test_jwt_grace_period.py:80-87 patches _jwks_cache, mocks fetch_jwks to a no-op and
  get_signing_key to return a test public JWK, signing synthetic tokens with a module-level RSA key and kid: test-key-id.
  Directly reusable for Part E layer 1 against both Claude servers. Part E is not blocked.

  Step 8 — Production DCR log check (30-day window)

  No loopback DCR attempts and no rejections. Across 2026-07-01 → now:

  - 3 × oauth.register.success, all client_name: "Claude" (2026-07-21 pg-c****b5ad; 2026-07-23 pg-c****30bd, pg-c****bd1f),
  each redirect_uris_count: 1
  - Zero localhost / 127.0.0.1 / ::1 in any redirect URI
  - Zero invalid_redirect_uri, zero DCR 400s
  - Every Claude authorize uses https://claude.ai/api/mcp/auth_callback; every ChatGPT one uses
  https://chatgpt.com/connector/oauth/i3aGemPmx9rv

  Notable: in the last ~10 days I see no authorize request carrying resource=https://mcp.priority-guard.com/mcp (PG-Claude's
  resource). Every Claude flow carries MindSort-Claude's resource; every pg.access flow is the ChatGPT connector.

  Which row applies — with attribution uncertainty stated as required: the evidence best fits row 2, "No completed reviewer
  OAuth flow yet → upside High." Caveats, explicitly: log attribution to a reviewer is not possible (no distinguishing
  user-agent on oauth.* events); pagination returned hasMore: true before 2026-07-21, so I have full coverage only of the last
  ~10 days; and reviewer traffic might not reach this backend at all if review is still at documentation stage. Row 3 ("cannot
  be shown to be low") is the defensible fallback if you want the conservative reading. Presenting evidence only — no deploy
  recommendation, per §0.1.

  Step 9 — SQL written, not run (per your instruction, filed as §11 step 1)

  -- aud-shape distribution, scoped by client app. READ-ONLY, aggregate only.
  -- Requires temporarily re-adding an IP to the (now empty) DB allow list.
  SELECT c.client_id_prefix,
         CASE WHEN t.audience = 'https://www.priority-guard.com' THEN 'issuer-shaped'
              WHEN t.audience LIKE 'https://%/mcp'               THEN 'resource-shaped'
              WHEN t.audience IS NULL                            THEN 'null'
              ELSE 'other' END                    AS aud_shape,
         count(*)                                 AS tokens,
         count(*) FILTER (WHERE t.revoked)        AS revoked,
         min(t.created_at)                        AS oldest,
         max(t.created_at)                        AS newest
  FROM oauth_tokens t
  JOIN oauth_clients c ON c.id = t.client_id
  GROUP BY 1, 2
  ORDER BY 1, 3 DESC;
  Column names need confirming against the models before running — I did not verify them against a live schema, since I can't
  reach the database.

  Step 10 — Render rollout behaviour

  Partially established. Shared backend: numInstances: 1, plan starter, healthCheckPath: "/health" configured. PG-Claude MCP:
  numInstances: 1, healthCheckPath: "" — none configured. A configured health check is what lets Render gate a cutover, so the
  backend is better positioned for a clean rollover than PG-Claude. I could not verify Render's exact zero-downtime semantics
  for single-instance starter services from here — treat this as suggestive, not established.

  Other verifications

  - §0.3 preliminary: authorize.py:442 normalizes resource, :487 and :734 write it into the auth context and token. No
  validation call between them. Matches the briefing's claim — but I read the working tree; I'll confirm against git show
  <sha>:<path> before Part E relies on it.
  - All 14 canonical documents exist; ADR_006 is the correct next number.
  - §0.1(b) satisfiable: tests/conftest.py:48 hardcodes postgresql+asyncpg://localhost/priority_guardian_test — not
  env-derived, so tests structurally cannot reach production. Local Postgres is up and that database exists.
  - Services healthy after the DB lockdown — all five return 200; Celery Beat firing through 17:30 UTC including the hourly
  token cleanup; zero DB errors.

  Could not verify

  1. Whether the backend build currently succeeds (build logs expired) — the open risk above.
  2. Reviewer attribution in logs, and DCR history before 2026-07-21.
  3. Render's zero-downtime behaviour for these specific services.
  4. The aud-shape query's column names (no DB access).

  Part A is complete. Nothing proceeds to Part C until you supply the three CLARITY_CLAUDE_* values and the MindSort deployed
  SHA. Before any Part B work, I'd want your read on the build-command finding — it determines whether "deploy Part B" is a
  thing that can happen at all.
