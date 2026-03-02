# Increment 36: Test Hardening — Additive Tests Only

## Context

This increment adds tests for six gaps identified in the security/test audit. **No production code changes.** All tests validate existing behavior.

This covers shared backend and MCP server. Tests are distributed across existing test directories following established conventions.

---

## Gap #5: `oauth_protected_resource/mcp` Not Tested at MCP Server Level

### What

The MCP server mounts discovery routes at both root and `/mcp` suffix:
- `/.well-known/oauth-protected-resource` (root)
- `/.well-known/oauth-protected-resource/mcp` (suffixed)

ChatGPT specifically hits the `/mcp` suffixed path. No integration test verifies this returns valid JSON.

### Where

File: `tests/integration/mcp_pg/test_discovery_endpoints_integration.py` (new)

### Tests (3)

1. **test_oauth_protected_resource_mcp_returns_valid_json** — GET `/.well-known/oauth-protected-resource/mcp` returns 200 with JSON containing `resource`, `authorization_servers`, `scopes_supported`. Also assert `content-type` header starts with `application/json`.

2. **test_openid_configuration_mcp_returns_valid_json** — GET `/.well-known/openid-configuration/mcp` returns 200 with JSON containing `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `code_challenge_methods_supported`. Also assert `content-type` header starts with `application/json`.

3. **test_oauth_authorization_server_mcp_returns_valid_json** — GET `/.well-known/oauth-authorization-server/mcp` returns 200 with JSON containing `issuer`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`. Also assert `content-type` header starts with `application/json`.

### Technical notes

- Use the same fixture pattern as `test_head_mcp_integration.py`: `create_app()` with `patch.dict("os.environ", {"ENV": "dev"})`, `httpx.ASGITransport`.
- Assert on required field presence and type (string, list), not on specific values (values are tested in `test_discovery_consistency.py` unit tests).

---

## Gap #7: Cross-Layer Scope Consistency (Backend ↔ MCP Server)

### What

The backend's `backend/core/oauth_provider/discovery.py` exports `SCOPES_SUPPORTED` which includes `pg.access`. The MCP server's `mcp_server/priority_guardian/config.py` exports its own `SCOPES_SUPPORTED` containing `["pg.access"]`. If someone removes `pg.access` from the backend's list, no test catches the mismatch. The MCP server would request a scope the backend doesn't advertise.

### Where

File: `tests/unit/core/test_cross_layer_scope_consistency.py` (new)

### Tests (2)

1. **test_backend_scopes_include_all_mcp_pg_scopes** — Import `SCOPES_SUPPORTED` from `backend.core.oauth_provider.discovery` and from `mcp_server.priority_guardian.config`. Assert every scope in MCP config's `SCOPES_SUPPORTED` exists in backend's `SCOPES_SUPPORTED`.

2. **test_consent_scope_descriptions_cover_all_mcp_pg_scopes** — Import `SCOPE_DESCRIPTIONS_EN` and `SCOPE_DESCRIPTIONS_DE` from `backend.core.oauth_provider.authorize`. Import `SCOPES_SUPPORTED` from `mcp_server.priority_guardian.config`. Assert every PG scope has a description in both languages.

### Technical notes

- These are pure import + assertion tests. No fixtures, no mocking, no DB, no HTTP.
- If imports fail due to module-level side effects (e.g., `settings` loading), use `importlib` or mock the settings import.

---

## Gap #9: HEAD /mcp CORS Origin Matching Edge Cases

### What

`HeadMcpMiddleware` checks if the request's `Origin` header is in `allowed_origins`. If it matches, it returns the matched origin. If not, it returns `*`. No test verifies the non-matching case or the no-Origin case explicitly.

Existing tests in `test_head_mcp_integration.py` test dev mode where `allowed_origins` includes localhost. They don't test production-like behavior with restricted origins.

### Where

File: `tests/unit/mcp_priority_guardian/test_head_mcp_cors_edge_cases.py` (new)

### Tests (4)

Instantiate `HeadMcpMiddleware` directly with a mock inner app (async callable that does nothing). This avoids creating the full MCP app.

1. **test_matching_origin_returns_origin** — Create middleware with `allowed_origins=["https://chatgpt.com"]`. Send HEAD /mcp with `Origin: https://chatgpt.com`. Assert `access-control-allow-origin` header is `https://chatgpt.com`.

2. **test_non_matching_origin_returns_wildcard** — Create middleware with `allowed_origins=["https://chatgpt.com"]`. Send HEAD /mcp with `Origin: https://evil.com`. Assert `access-control-allow-origin` header is `*`.

3. **test_no_origin_header_returns_wildcard** — Create middleware with `allowed_origins=["https://chatgpt.com"]`. Send HEAD /mcp without Origin header. Assert `access-control-allow-origin` header is `*`.

4. **test_empty_allowed_origins_returns_wildcard** — Create middleware with `allowed_origins=[]` or `allowed_origins=None`. Send HEAD /mcp with `Origin: https://chatgpt.com`. Assert `access-control-allow-origin` header is `*`.

### Technical notes

- Test the middleware class directly, not through the full app stack. This isolates CORS logic.
- Build ASGI scope manually: `{"type": "http", "method": "HEAD", "path": "/mcp", "headers": [...]}`.
- The mock inner app should never be called (middleware short-circuits HEAD /mcp). **Assert the inner app was NOT called** in every test — this verifies the short-circuit, not just the response.
- Capture the response by providing a mock `send` callable that records the headers.

---

## Gap #10: `exchange_refresh_token` with Expired Refresh Token (Integration)

### What

Unit tests exist for `token_validators.validate_token_not_expired()`, but no integration test creates an actual `OAuthAccessToken` row with an expired `refresh_token_expires_at`, then hits the token endpoint and verifies the 400 response.

### Where

File: `tests/integration/oauth_provider/test_oauth_token_endpoint_integration.py` (existing — add test)

### Tests (1)

Add to existing test file, reusing its fixtures (`test_user`, `test_oauth_client`, `generate_pkce_pair`, etc.):

1. **test_refresh_token_expired_in_db_returns_invalid_grant** — Create an `OAuthAccessToken` row with `refresh_token_expires_at` set to 1 hour in the past. POST to `/oauth/pg/token` with `grant_type=refresh_token` and the matching refresh token. Assert response is 400 with `error=invalid_grant` and description contains "expired".

### Technical notes

- Follow the existing pattern in the file — see tests 2.3 (`test_refresh_expired_token`) if it exists. If a similar test already exists, this gap may already be covered (verify before adding).
- The key is that `refresh_token_expires_at` is set in the DB row, not mocked. This proves the full stack (endpoint → service → validator → DB) works.

---

## Gap #11: `_normalize_redirect_uri` Localhost Port Handling

### What

`_normalize_redirect_uri` in `authorize.py` strips port for the localhost detection check (`host = parsed.netloc.lower().split(":")[0]`) but preserves port in the normalized URI. This means `http://localhost:3000/callback` is correctly allowed (because localhost is detected) and the normalized URI keeps `:3000` (so the redirect goes to the right port). This is correct behavior but untested.

### Where

File: `tests/unit/core/test_normalize_redirect_uri.py` (new)

### Tests (5)

Import `_normalize_redirect_uri` from `backend.core.oauth_provider.authorize`.

1. **test_localhost_with_port_allowed** — Input: `http://localhost:3000/callback`. Assert returns `http://localhost:3000/callback` (HTTP allowed, port preserved).

2. **test_localhost_without_port_allowed** — Input: `http://localhost/callback`. Assert returns `http://localhost/callback`.

3. **test_127_0_0_1_with_port_allowed** — Input: `http://127.0.0.1:5173/callback`. Assert returns `http://127.0.0.1:5173/callback`.

4. **test_non_localhost_http_rejected** — Input: `http://example.com/callback`. Assert returns `None` (HTTP not allowed for non-localhost).

5. **test_query_and_fragment_rejected** — Input: `https://example.com/callback?foo=bar`. Assert returns `None`. Input: `https://example.com/callback#frag`. Assert returns `None`.

### Technical notes

- Pure function tests. No fixtures, no mocking, no DB, no HTTP.
- The function is private (`_normalize_redirect_uri`) but imported directly for testing — this is acceptable for security-relevant validation logic.

---

## Gap #12: `exchange_code` Retry with Jitter

### What

`exchange_code` in `google_oauth.py` implements exponential backoff with `random.uniform(0, 1)` jitter on retries. No test verifies that a transient failure (e.g., 500) is retried and succeeds on the second attempt.

### Where

File: `tests/unit/core/test_google_oauth_retry.py` (new)

### Tests (3)

1. **test_exchange_code_retries_on_500_then_succeeds** — Mock `http_client.post` to return 500 on first call, then 200 with valid token data on second call. Patch `asyncio.sleep` to no-op (so test doesn't actually wait). Assert the function returns a valid token dict. Assert `http_client.post` was called exactly 2 times.

2. **test_exchange_code_fails_after_max_retries** — Mock `http_client.post` to always return 500 (with a JSON body `{"error": "server_error", "error_description": "Internal error"}`). Patch `asyncio.sleep` to no-op. Assert `ValueError` is raised after 3 attempts. Assert `http_client.post` was called exactly 3 times.

3. **test_exchange_code_no_retry_on_400_invalid_grant** — Mock `http_client.post` to return 400 with `{"error": "invalid_grant", "error_description": "Code expired"}`. Assert `ValueError` is raised immediately. Assert `http_client.post` was called exactly 1 time (no retry for client errors).

### Technical notes

- Use `httpx.Response` objects with proper status codes and JSON bodies. Use `unittest.mock.AsyncMock` for `http_client.post` with `side_effect` list.
- Patch `asyncio.sleep` at `backend.core.google_oauth.asyncio.sleep` (the module-level import) to prevent actual delays.
- Patch `random.uniform` at `backend.core.google_oauth.random.uniform` to return a fixed value (e.g., 0.5) for deterministic delay calculation, or just let it run (jitter doesn't affect correctness).
- The `exchange_code` function expects `httpx.HTTPStatusError` for non-200 responses. The mock must raise `httpx.HTTPStatusError` with a proper `response` object, not just return a response with a bad status code. Check the function's error handling path — it catches `httpx.HTTPStatusError`, so the mock's `.post()` must call `response.raise_for_status()` or the mock itself must raise the exception. Alternatively, use `httpx.Response` with `raise_for_status()` — but `AsyncMock` for `http_client.post` returning an `httpx.Response` won't auto-raise. **Safest approach**: use `side_effect` to directly raise `httpx.HTTPStatusError` with a constructed response object for error cases, and return a normal `httpx.Response` for the success case.

---

## Summary

| Gap | File | New/Existing | Test Count |
|-----|------|-------------|-----------|
| #5 | `tests/integration/mcp_pg/test_discovery_endpoints_integration.py` | New | 3 |
| #7 | `tests/unit/core/test_cross_layer_scope_consistency.py` | New | 2 |
| #9 | `tests/unit/mcp_priority_guardian/test_head_mcp_cors_edge_cases.py` | New | 4 |
| #10 | `tests/integration/oauth_provider/test_oauth_token_endpoint_integration.py` | Existing | 1 |
| #11 | `tests/unit/core/test_normalize_redirect_uri.py` | New | 5 |
| #12 | `tests/unit/core/test_google_oauth_retry.py` | New | 3 |
| **Total** | | | **18** |

## Acceptance Criteria

- [ ] All 18 tests pass
- [ ] No production code modified
- [ ] Full existing test suite still passes
- [ ] New test files have module-level docstrings describing what they cover
- [ ] No test introduces external dependencies (no network calls, no real Redis, no real DB for unit tests)

## Files to Create

- `tests/integration/mcp_pg/test_discovery_endpoints_integration.py`
- `tests/unit/core/test_cross_layer_scope_consistency.py`
- `tests/unit/mcp_priority_guardian/test_head_mcp_cors_edge_cases.py`
- `tests/unit/core/test_normalize_redirect_uri.py`
- `tests/unit/core/test_google_oauth_retry.py`

## Files to Modify

- `tests/integration/oauth_provider/test_oauth_token_endpoint_integration.py` (add 1 test)

## Files NOT to Touch

- Any production code
- Any existing test logic (only additive)
