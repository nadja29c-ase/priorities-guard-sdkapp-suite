# Increment 34: Scope Enforcement Fix & Auth Test Hardening

## Context

Security audit of the Priority Guardian MCP server identified two bugs and two test gaps that must be addressed before submission readiness.

**Bugs (must fix):**
1. `TOOL_SCOPES` in `config.py` is missing 7 of 17 registered tools → those tools bypass scope enforcement at runtime
2. `test_tool_registry.py` expects 11 tools but registry has 17 → false confidence in test suite

**Test gaps (must close):**
3. JWT grace period check makes PyJWT leeway dead code → no tests document or verify this interaction
4. MCP discovery endpoint URL consistency is untested → misconfigured env vars silently break ChatGPT OAuth

---

## Bug 1: TOOL_SCOPES Missing 7 Entries (Security Gap)

### Problem

`mcp_server/priority_guardian/config.py` defines `TOOL_SCOPES` — the dict used by `enforce_tool_scope()` in `mcp_auth.py` at runtime. When a tool name is NOT in `TOOL_SCOPES`, the function returns without checking scopes (lines 387-393 in `mcp_auth.py`):

```python
required_scopes = TOOL_SCOPES.get(tool_name, [])
if not required_scopes:
    logger.warning("scope.enforcement.no_requirements", ...)
    return  # ← No scope check happens
```

**TOOL_SCOPES has 10 entries. TOOL_REGISTRY has 17 tools.** These 7 tools bypass scope enforcement entirely:

| Tool | Visibility | In TOOL_REGISTRY | In TOOL_SCOPES |
|---|---|---|---|
| `get_weekly_report` | public | ✅ | ❌ |
| `get_patterns` | public | ✅ | ❌ |
| `onboarding_calendar_setup` | public | ✅ | ❌ |
| `inspect_adapt` | public | ✅ | ❌ |
| `add_goal` | private/widget | ✅ | ❌ |
| `update_goal` | private/widget | ✅ | ❌ |
| `delete_goal` | private/widget | ✅ | ❌ |

All 7 have `required_scopes=["pg.access"]` on their `ToolDefinition` — but that field is only used for **discovery metadata** in `list_tools()`, not for runtime enforcement. Two sources of truth, one stale.

### Root cause

`TOOL_SCOPES` in config.py and `ToolDefinition.required_scopes` on each tool are independent declarations that must be kept in sync manually. They drifted as new tools were added in increments 18-28.

### Fix: Single source of truth

Remove `TOOL_SCOPES` from `config.py`. Change `enforce_tool_scope` in `mcp_auth.py` to read required scopes from the TOOL_REGISTRY via `get_tool()`, making `ToolDefinition.required_scopes` the single authoritative source for both discovery AND enforcement.

**Changes to `mcp_auth.py`:**

1. Remove `TOOL_SCOPES` from the config import line (line 37)
2. Update `enforce_tool_scope` to use a **late import** of `get_tool` inside the function body (defensive against future circular imports):

Updated logic for `enforce_tool_scope`:
- Late import: `from mcp_server.priority_guardian.tools import get_tool`
- Call `get_tool(tool_name)` to get the ToolDefinition
- If tool not found: **fail closed** — raise `UnauthorizedError("invalid_token", "Token validation failed")` (not silent return). Do NOT use `InsufficientScopeError` — it's not a scope problem, it's an unknown tool. `UnauthorizedError` maps to 401, avoids revealing tool existence, and uses the same error type the caller already handles. The dispatcher handles unknown tools before auth runs, but if this is somehow reached, deny access.
- If `tool_def.required_scopes` is empty: log warning and return (same as current behavior for tools that genuinely need no scopes — none exist today, but forward-compatible)
- Otherwise: check scopes as before using `check_scopes()`

**Changes to `config.py`:**

Remove the entire `TOOL_SCOPES` dict and its comment block (lines defining the "Scope Definitions" section).

### Constraint: No token content in logs

The updated `enforce_tool_scope` must not log raw token scopes beyond what the current implementation already logs. Specifically: logging `required=required_scopes` and `actual=list(token_scopes)` in the insufficient case is acceptable (scope names, not tokens). Do not add any logging of token strings, JWTs, or bearer values.

### What NOT to change

- No `ToolDefinition.required_scopes` changes on any tool
- No changes to `list_tools()`
- No changes to `handlers/tools.py` (dispatcher)
- No changes to any tool handler

---

## Bug 2: Stale test_tool_registry.py

### Problem

`tests/unit/priority_guardian/test_tool_registry.py` was written when the registry had 11 tools. The registry now has 17 tools (6 public + 11 private). Two specific failures:

1. `test_all_expected_tools_present` — hardcoded expected set is missing 6 tool names
2. `test_returns_list_of_mcp_tools` — asserts `len(tools) == 11`

Note: TOOL_SCOPES was missing 7 entries (Bug 1), but this test file was missing 6 tool names — different drift, different count. The test already included `get_weekly_report` which was absent from TOOL_SCOPES.

### Fix

Update `test_all_expected_tools_present` — add the 6 missing tool names to the expected set:
- `get_patterns`
- `onboarding_calendar_setup`
- `inspect_adapt`
- `add_goal`
- `update_goal`
- `delete_goal`

Update `test_returns_list_of_mcp_tools` — change `assert len(tools) == 11` to `assert len(tools) == 17`.

Update comments to reflect actual counts:
- 6 public: `create_priority`, `get_priorities`, `get_weekly_report`, `get_patterns`, `onboarding_calendar_setup`, `inspect_adapt`
- 11 private: `connect_google_calendar`, `disconnect_google_calendar`, `add_priority`, `update_priority`, `delete_priority`, `add_deliverable`, `update_deliverable`, `delete_deliverable`, `add_goal`, `update_goal`, `delete_goal`
- Total: 17

---

## Test Gap 3: JWT Grace Period Behavior

### What's happening

`validate_jwt()` in `mcp_auth.py` has two token expiry checks:

1. **PyJWT leeway** (line ~280): `jwt.decode(..., leeway=TOKEN_EXPIRY_GRACE_SECONDS)` — accepts tokens that expired up to 30s **ago** (clock skew tolerance)
2. **Manual check** (lines ~288-295): rejects tokens where `exp - current_time < TOKEN_EXPIRY_GRACE_SECONDS` — rejects tokens expiring within 30s **from now** (proactive rejection)

These interact in a way that makes leeway dead code:

| Token state | PyJWT (leeway=30) | Manual check (exp-now < 30) | Final |
|---|---|---|---|
| 60s from expiry | ✅ accept | ✅ pass (60 ≥ 30) | ✅ accepted |
| 25s from expiry | ✅ accept (not expired) | ❌ reject (25 < 30) | ❌ rejected |
| Expired 5s ago | ✅ accept (within leeway) | ❌ reject (-5 < 30) | ❌ rejected |
| Expired 35s ago | ❌ reject (beyond leeway) | N/A | ❌ rejected |

Row 3 is the conflict: PyJWT accepts a recently-expired token via leeway, then the manual check rejects it because `exp - now` is negative (which is `< 30`). The leeway parameter has zero practical effect.

### Policy decision: keep leeway, remove manual check

The manual proactive rejection is non-standard and makes leeway dead code. Standard behavior is to trust the token until it expires and let the client handle refresh. Clock skew tolerance (leeway) is the standard mechanism.

### Fix

Remove the manual grace period check from `validate_jwt()` — specifically the "Step 5: Additional expiry grace period check" block (lines ~288-295):

```python
# Remove this entire block:
exp = payload.get("exp")
if exp and (exp - current_time) < TOKEN_EXPIRY_GRACE_SECONDS:
    logger.warning(
        "jwt.validation.expiring_soon",
        correlation_id=correlation_id,
        seconds_until_expiry=int(exp - current_time)
    )
    raise jwt.ExpiredSignatureError(
        f"Token expires in less than {TOKEN_EXPIRY_GRACE_SECONDS} seconds"
    )
```

Keep the `leeway=TOKEN_EXPIRY_GRACE_SECONDS` parameter in `jwt.decode()` — it correctly handles clock skew.

Renumber "Step 6" comment to "Step 5".

### What NOT to change

- Do NOT change `TOKEN_EXPIRY_GRACE_SECONDS` config value
- Do NOT change the `leeway` parameter in `jwt.decode()`
- Do NOT change any other validation step in `validate_jwt`

---

## Test Gap 4: MCP Discovery URL Consistency

### Problem

If someone misconfigures `PG_OAUTH_ISSUER_URL` or `PG_MCP_SERVER_URL`, ChatGPT OAuth silently fails. No test verifies that discovery endpoints return URLs derived from the configured values.

---

## New Tests

All new test files go in `tests/unit/mcp_priority_guardian/` — this is where MCP server infrastructure tests live (alongside `test_pg_mcp_auth.py`, `test_health_endpoints.py`, `test_head_mcp.py`).

### File: `tests/unit/mcp_priority_guardian/test_scope_enforcement_completeness.py` (new)

**Unit Tests:**

1. **test_every_registered_tool_has_required_scopes** — import `TOOL_REGISTRY`, iterate all entries, assert each `tool.required_scopes` is a non-empty list. Also assert every scope in `tool.required_scopes` exists in `config.SCOPES_SUPPORTED` — this catches typos or undefined scopes on tool definitions.

2. **test_enforce_tool_scope_resolves_every_registered_tool** — for each tool name in `TOOL_REGISTRY`, call `enforce_tool_scope(tool_name, {"pg.access"}, "test-corr")`. Assert no exception raised. Confirms every tool is reachable through the single-source path. (Requires Bug 1 fix to pass.)

3. **test_enforce_tool_scope_rejects_insufficient_scopes** — call `enforce_tool_scope("get_patterns", {"wrong.scope"}, "test-corr")`. Assert `InsufficientScopeError` raised with correct `required_scopes`.

4. **test_enforce_tool_scope_unknown_tool_fails_closed** — call `enforce_tool_scope("nonexistent_tool", {"pg.access"}, "test-corr")`. Assert `UnauthorizedError` raised (not `InsufficientScopeError` — unknown tool is an auth failure, not a scope failure). (Requires Bug 1 fix — old behavior silently returned.)

5. **test_enforce_tool_scope_does_not_log_token_values** — call `enforce_tool_scope` with insufficient scopes, capture log output, verify no raw token strings appear (scope names like "pg.access" are acceptable).

### File: `tests/unit/mcp_priority_guardian/test_jwt_grace_period.py` (new)

All tests mock the **module-level `_jwks_cache` object** in `mcp_server.priority_guardian.mcp_auth` and use a test RSA key pair generated at module level. JWTs are signed with the private key. The mock must patch `_jwks_cache.fetch_jwks()` (to no-op) and `_jwks_cache.get_signing_key(kid)` (to return the test public key as a `PyJWK`). This matches exactly how `validate_jwt()` calls the cache — patching anything else will pass locally but fail in CI.

1. **test_token_25_seconds_from_expiry_accepted** — JWT with `exp = now + 25`. After fix: accepted. (Before fix: rejected by manual check.)

2. **test_token_expired_5_seconds_ago_accepted_via_leeway** — JWT with `exp = now - 5`. With `TOKEN_EXPIRY_GRACE_SECONDS=30`, leeway accepts it. After fix: accepted. (Before fix: rejected by manual check.)

3. **test_token_expired_beyond_leeway_rejected** — JWT with `exp = now - 60`. Rejected by PyJWT (beyond 30s leeway). Raises `ExpiredSignatureError`.

4. **test_token_60_seconds_from_expiry_accepted** — JWT with `exp = now + 60`. Accepted (well within bounds). Baseline sanity check.

### File: `tests/unit/mcp_priority_guardian/test_discovery_consistency.py` (new)

These tests import discovery functions and config values directly — no HTTP calls, no mocking needed.

1. **test_openid_configuration_urls_derive_from_oauth_issuer_url** — call `openid_configuration()`, verify `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `registration_endpoint` all start with `config.OAUTH_ISSUER_URL`.

2. **test_oauth_authorization_server_urls_derive_from_oauth_issuer_url** — same check for `oauth_authorization_server()`.

3. **test_oauth_protected_resource_uses_mcp_server_url** — call `oauth_protected_resource()`, verify `resource` equals `config.MCP_SERVER_URL` and `authorization_servers` contains `config.OAUTH_ISSUER_URL`.

4. **test_discovery_scopes_match_config** — all three discovery functions return `scopes_supported` equal to `config.SCOPES_SUPPORTED`.

5. **test_code_challenge_methods_include_s256** — `openid_configuration()` and `oauth_authorization_server()` both include `"S256"` in `code_challenge_methods_supported`.

These tests don't require changes to `discovery.py`. They catch future drift when config values or discovery logic diverge.

---

## Acceptance Criteria

- [ ] `TOOL_SCOPES` dict removed from `config.py`
- [ ] `TOOL_SCOPES` import removed from `mcp_auth.py`
- [ ] `enforce_tool_scope` uses late import of `get_tool` from TOOL_REGISTRY
- [ ] `enforce_tool_scope` fails closed on unknown tools (raises `UnauthorizedError`)
- [ ] Manual JWT grace period check removed from `validate_jwt()`
- [ ] `test_tool_registry.py` updated: expected set has 17 tools (6 public + 11 private)
- [ ] New `test_scope_enforcement_completeness.py` — all 5 tests pass
- [ ] New `test_jwt_grace_period.py` — all 4 tests pass
- [ ] New `test_discovery_consistency.py` — all 5 tests pass
- [ ] Full test suite passes (`pytest` from project root)
- [ ] No changes to tool handlers, dispatcher, or discovery functions

## Files to Modify

| File | Change |
|---|---|
| `mcp_server/priority_guardian/config.py` | Remove `TOOL_SCOPES` dict |
| `mcp_server/priority_guardian/mcp_auth.py` | Remove `TOOL_SCOPES` import; update `enforce_tool_scope` with late import + fail-closed; remove manual grace period check |
| `tests/unit/priority_guardian/test_tool_registry.py` | Update expected tool set (17) and count assertions |

## Files to Create

| File | Purpose |
|---|---|
| `tests/unit/mcp_priority_guardian/test_scope_enforcement_completeness.py` | Scope enforcement guard tests (5 tests) |
| `tests/unit/mcp_priority_guardian/test_jwt_grace_period.py` | JWT expiry behavior tests (4 tests) |
| `tests/unit/mcp_priority_guardian/test_discovery_consistency.py` | Discovery URL consistency tests (5 tests) |

## Files NOT to Touch

- `mcp_server/priority_guardian/tools/*.py` — no tool definition changes
- `mcp_server/priority_guardian/handlers/tools.py` — dispatcher unchanged
- `mcp_server/priority_guardian/discovery.py` — discovery functions unchanged
- `mcp_server/priority_guardian/server.py` — server unchanged
- `backend/` — no backend changes
