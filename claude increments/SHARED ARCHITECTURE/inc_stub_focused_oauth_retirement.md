# Increment (STUB / backlog): Remove Focused from the OAuth surface

**Status:** Tracked, NOT scheduled. Separate from inc_08. Do NOT bundle into inc_08 (consent scope classification) — bundling expands inc_08's blast radius and makes failures ambiguous (classification bug vs. removal bug). Sequence AFTER inc_08 v2 deploys + verifies, because inc_08 v2 deliberately keeps `focused.` as legacy-compatible and its non-regression tests depend on the focused branch + focused fixtures existing.

**Decision context:** Focused is deprecated and will never go live (confirmed). Its OAuth surface is unnecessary noise. This increment removes ONLY the OAuth surface. It does NOT delete Focused's data/tables/app/MCP server — Focused-the-product is retained, just removed from OAuth.

## Scope (OAuth surface only)
- `/oauth/focused/*` route decorators in `authorize.py`, `register_client.py`, `consent_ui.py`.
- `ROUTE_SCOPE_REGISTRY["focused"]` entry in `register_client.py`.
- `focused.*` classification branch in `authorize.py` (after inc_08: the `_APP_BY_PREFIX` focused entry) — once removed, `focused.*` classifies as unknown → rejected, which is correct for a non-live app.
- Focused scope descriptions (`SCOPE_DESCRIPTIONS_EN/DE` focused.* entries) in `authorize.py`.
- The `oauth_consent_{lang}.html` Focused consent template reference (decide: delete template, or leave the file unreferenced).
- Focused OAuth tests + the `focused`-as-generic-fixture usage in `tests/unit/oauth_provider/test_increment_17_consent.py` (re-point those fixtures to pg/mindsort — they are NOT about Focused; do not just delete the coverage).

## Explicitly OUT (do NOT touch here)
- `backend/apps/focused/` (focused_config.py etc.)
- `mcp_server/focused/` (server, discovery, mcp_auth, config)
- Alembic migrations `392814db8293_add_focused_user_keywords_table.py`, `94adbd6c7fd3_add_focused_focus_sessions_table.py` and the `focused_user_keywords` / `focused_focus_sessions` tables — these are DATA with a documented 72h GDPR retention policy; dropping them is a SEPARATE, destructive, GDPR-sensitive decision, not part of OAuth-surface removal.
- `core_consents` rows with `app_name="focused"` — leave as historical audit records.
- The four focused test trees (`tests/E2E_tests/focused`, `tests/integration/focused`, `tests/integration/mcp_focused`, `tests/unit/mcp_focused`) — not part of OAuth removal.

## Pre-removal verification (must do FIRST — not yet done)
- **Confirm no live Focused deployment/client.** The Focused MCP server (`mcp_server/focused/discovery.py`) still advertises the focused OAuth routes via its discovery. Removing the backend routes is safe ONLY if nothing live connects to Focused. Confirm: (a) Focused MCP server not deployed on Render, (b) no `core_connections` rows of `connection_type='oauth_provider'` with focused-prefixed scopes that represent a live client. If a live focused client exists, removal would 404 its auth — decide before proceeding.
- Grep for imports/usages of the focused OAuth routes/registry entry outside the focused trees.

## Notes
- Shared-backend change → predeploy ritual + both-platform live consent check (PG + MindSort still render correctly after focused removal).
- Coupling caveat: route removal is isolated in PRACTICE because Focused is dead, not because it is structurally decoupled (the focused MCP discovery still references the routes). If Focused were ever revived, its OAuth would need re-adding. Acceptable tradeoff for a deprecated app; state it, don't paper over it.
- Related: a fuller "retire Focused entirely" program (drop tables, remove app + MCP server + test trees, GDPR data handling) is a larger multi-increment effort beyond this OAuth-surface stub.
