Increment 50 — Scope Cleanup: Remove Dead App Scopes from Backend AS Discovery
Context
The shared AS (www.priority-guard.com) advertises 5 scopes in SCOPES_SUPPORTED. Focused is deprecated, Clarity was rejected. Only PG is active. The MCP server already advertises only ["pg.access"]. This removes the dead scopes from the backend AS discovery document to eliminate reviewer confusion. No logic changes.
Files to change
1. backend/core/oauth_provider/discovery.py
Change SCOPES_SUPPORTED from:
pythonSCOPES_SUPPORTED = sorted([
    "clarity.write",
    "focused.notify",
    "focused.read",
    "focused.write",
    "pg.access",
])
to:
pythonSCOPES_SUPPORTED = ["pg.access"]
Update the module docstring — remove the bullet lines referencing focused.* and clarity.*. Replace with a single line: # Supports scopes for Priority Guardian (pg.access).
Files to delete

tests/unit/oauth_provider/test_clarity_scope.py
tests/integration/oauth_provider/test_clarity_scope_integration.py

Both test dead functionality (Clarity is rejected, Focused deprecated). test_clarity_scope.py also references clarity.read which was never in SCOPES_SUPPORTED — already inconsistent.
Files to check (read before deciding whether to touch)
tests/integration/oauth_provider/test_increment_13_integration.py and tests/unit/oauth_provider/test_increment_13_unit.py — read them and check if they assert specific scopes are in scopes_supported. If yes, update only those assertions to expect ["pg.access"]. If they don't touch scopes_supported, leave untouched.
Files NOT to touch

authorize.py — scope descriptions and template branch stay as-is
register_client.py — DEFAULT_SCOPES_FOCUSED and all route logic stays as-is
consent_ui.py — no changes
All HTML templates — no changes
All Focused/Clarity backend routes — no changes
No DB changes, no migrations

Verification
bashpytest tests/unit/core/test_cross_layer_scope_consistency.py -v
pytest tests/unit/oauth_provider/ -v
pytest tests/integration/oauth_provider/ -v
pytest tests/integration/mcp_pg/test_discovery_endpoints_integration.py -v
All tests pass. The two deleted test files are gone.
Pre-deploy check
Read OPERATIONS_PREDEPLOY.md before committing. After deploy:
bashcurl https://www.priority-guard.com/.well-known/oauth-authorization-server | jq .scopes_supported
# Expected: ["pg.access"]