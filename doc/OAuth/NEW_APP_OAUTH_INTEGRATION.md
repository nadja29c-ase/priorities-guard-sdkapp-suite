# New App OAuth Integration — Routing Playbook

**Type:** Routing document. It owns exactly ONE normative rule of its own: the
briefing rule in Step 3 (it exists nowhere else). Everything else on this page is a
NON-AUTHORITATIVE summary with a pointer — the linked canonical doc is authoritative,
and on any mismatch the canonical doc wins and the summary line here gets fixed.
If you find yourself writing a new requirement INTO this file, stop — it belongs in
the canonical doc, linked from here. Fix broken links on sight (living-artifact rule).

**Use when:** integrating any new SDK app with OAuth, or writing any briefing that
touches OAuth, discovery, or platform integration. Briefings MUST cite which branch
of the decision tree below the increment sits on.

**Last verified against codebase:** 2026-07-04

---

## Step 0 — Routing summary of system invariants (non-authoritative — ADR_005 is authoritative)

- ONE Authorization Server, ONE issuer: `https://www.priority-guard.com`. Current system
  invariant — superseding it requires a new ADR plus a token/consent migration plan,
  not an increment. Never a second AS within the current architecture.
- Discovery shape is PLATFORM-COUPLED BY DESIGN. Never consolidate shapes across the
  platform boundary. → `doc/ADR/ADR_005_platform_oauth_discovery_contracts.md`
- Any change to a discovery module or its config requires reproducing the affected
  platform's full live connect flow (delete-and-re-add) before merge. → ADR_005
- AS-side protocol requirements (grants, PKCE, tokens, TLS, rate limits)
  → `doc/OAuth/OAuth_Hard_Requirements.md`

## Step 1 — Which platform?

### Branch A: ChatGPT SDK app
- Discovery shape: **path-qualified AS mount** on www (`/oauth/<app>` with its own
  `.well-known` sub-mount). Reference implementation: MindSort-OpenAI
  (`backend/core/oauth_provider/mindsort_discovery.py` + `mcp_server/clarity/discovery.py`).
  → ADR_005, Shape #2
- NOTE: PG-OpenAI's mixed-origin proxy shape (Shape #1) is LEGACY, load-bearing for
  that app only — NOT the template for new apps. → ADR_005 rejected-alternatives.
- A new app needs its own backend `.well-known` sub-mount; only `/oauth/mindsort`
  exists today (`/oauth/pg` has none). → ADR_005
- Platform compliance: `doc/compliance_master_<version>.md` + `doc/openai_uiux_<version>.md`
- Platform quirks on record: `doc/OAuth/platform_quirk_*.md` — read before assuming
  client behavior.

### Branch B: Claude SDK app
- Discovery shape: **root-issuer** (`authorization_servers = [root www]`, no path).
  Reference implementation: `mcp_server/mindsort_claude/discovery_dupl.py`.
  → ADR_005, Shape #3
- Platform compliance: `doc/Claude_Compliance/claude_connectors_compliance_master.md`
  (callbacks, PKCE S256 advertisement, PRM, 401 + `WWW-Authenticate` with
  `resource_metadata`, DCR/CIMD scaling)
- Structural split OpenAI↔Claude (`_dupl` convention, what is shared vs platform-specific):
  `doc/Claude_Compliance/structural_guideline_claude_vs_openai.md`

## Step 2 — Integration checklist (each line is a pointer, not a requirement)

1. **Config module** — Copy and Adjust, Never Rewrite; references differ by branch:
   - **Branch B (Claude):** copy `mcp_server/mindsort_claude/config.py` — the fully
     hardened reference (ENV known-set + fail-fast, `_is_production_env`, issuer
     `rstrip` + ROOT-shape guard, same-origin guard, localhost guard).
   - **Branch A (ChatGPT):** take discovery SHAPE/VALUES from `mcp_server/clarity/config.py`
     (path-qualified `OAUTH_ISSUER_URL`), but take the GUARD PATTERN from the Branch B
     reference, adjusted to Branch A semantics (the issuer URL there is deliberately
     path-qualified, so the shape guard differs — do not copy the root-shape guard as-is).
     KNOWN GAP (2026-07-04): `clarity/config.py` is only partially hardened — no
     known-ENV fail-fast, and its production tuples omit the `prod` alias. Do NOT copy
     it as a guard template; parity back-port is on the post-submission backlog.
2. **DCR route + scope registry entry** (`/oauth/<app>/register`, closed `resource`/`aud`
   allowlist) → `doc/ADR/ADR_003_oauth_provider_route_scope_mapping.md`
3. **Scopes** — every tool has a non-empty scope entry in the app's enforcement source
   (registry field OR `TOOL_SCOPES` dict — they differ per app; check which one the
   app's auth actually reads). Extend
   `tests/unit/oauth_discovery/test_tool_scope_invariants.py` for the new app.
4. **Audience list** — the app's `valid_audiences` must cover the `aud` values production
   tokens actually carry (backend mints `aud = resource-param-or-issuer`). Reference:
   PG-Claude's three-value list in `mcp_server/priority_guardian_claude/mcp_auth_dupl.py`.
5. **Discovery contract tests** — add the new app's shape to
   `tests/unit/oauth_discovery/test_oauth_discovery_contracts.py` AND a
   `PRODUCTION_SERVERS` entry in
   `tests/integration/oauth_discovery/test_live_discovery_chain.py` (live suite:
   `pytest -m live`).
6. **Canonical URLs** — add the app to `doc/CANONICAL_MCP_URLS.md` BEFORE hardcoding any
   URL anywhere. Update that doc from the Render dashboard, never from memory.
7. **Operations** — `doc/OPERATIONS_PREDEPLOY.md` before any commit/deploy;
   `doc/OPERATIONS_PRESUBMISSION.md` before submission.

## Step 3 — Briefing rule

Every OAuth-touching briefing states: (a) which branch (A/B) and shape the increment
sits on, (b) which checklist items it touches, (c) the canonical docs read fresh for it.
