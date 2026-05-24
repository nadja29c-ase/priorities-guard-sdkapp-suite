Increment 07: Clarity OAuth Production Hardening (FINAL)
Context

Increment 04 implemented OAuth integration. Increment 05 added persistence. OAuth is functional, but production readiness requires fail-closed guarantees, automated security verification, and deployment hardening.

This increment focuses on closing real security gaps and preventing configuration-level OAuth failures before real users.

Blocking Items (before real users)
1. Verify Unknown Tool Fails Closed (SECURITY)

⚠️ Important reframing
We must verify fail-closed behavior at the handler/dispatcher boundary, not assume a gap based on a helper function.

Required behavior

Unknown tool requests must:

fail closed

return an error

never reach a tool handler

never trigger persistence

Step 1: Regression test (required)

File: tests/unit/mcp/clarity/test_dispatcher.py (or equivalent)

Add a test that exercises the full request path:

@pytest.mark.asyncio
async def test_unknown_tool_fails_closed_at_dispatcher():
    """Unknown tools must fail closed before execution."""
    response = await call_tool(
        name="nonexistent_tool",
        arguments={},
        token=valid_token_with_clarity_write,
    )

    assert response.is_error


Only if this test fails do we modify auth logic.

Step 2: Auth-layer hardening (only if needed)

File: mcp_server/clarity/mcp_auth.py

If enforce_tool_scope() is reachable for unknown tools, fix it.

Current logic:

if tool_name not in TOOL_SCOPES:
    return


Replace with:

if tool_name not in TOOL_SCOPES:
    raise UnauthorizedError(f"Unknown tool: {tool_name}")


❗ Do not use InsufficientScopeError here.
Unknown tool ≠ insufficient scope. This is a protocol error, not an authorization-scope mismatch.

2. Defense-in-Depth Auth Test (NON-BLOCKING BUT REQUIRED)

File: tests/unit/mcp/clarity/test_auth.py

Ensure JWT validation is never called if token extraction fails.

@pytest.mark.asyncio
async def test_validate_jwt_not_called_when_token_extraction_fails():
    """If no bearer token, validate_jwt should never be called."""
    with patch("mcp_server.clarity.mcp_auth.validate_jwt") as mock_validate:
        with pytest.raises(UnauthorizedError):
            await authenticate_request("cluster_raw_thoughts", {})
        mock_validate.assert_not_called()


Purpose:

prevents future refactors from reintroducing fail-open behavior

enforces correct auth short-circuiting

3. OAuth System Integration Test (BLOCKING)

🔴 This is required for “production-ready OAuth.”

Manual ChatGPT testing is not sufficient.

Add one automated system/integration test that verifies:

JWKS is fetched from CLARITY_JWKS_URL

a token signed by those keys validates

incorrect claims fail

Test must assert failures for:

wrong iss

wrong aud

wrong azp

missing clarity.write scope

This test can:

spin up the backend OAuth provider in test mode, or

use a locally issued token signed with test keys

Goal: prevent silent production breakage due to issuer/audience/JWKS misconfiguration.

4. Backend Internal-Secret Enforcement Test (BLOCKING)

Persistence endpoints are protected by INTERNAL_API_SECRET. This trust boundary must be locked with tests.

File: backend integration tests (e.g. tests/integration/clarity/test_internal_auth.py)

Required cases (when ENV=production and secret is set):

Missing X-Internal-Secret → 403

Wrong secret → 403

Correct secret → 201

This protects the persistence API from spoofed requests and is security-critical.

5. Production Environment Variables

Document required env vars for Railway:

Variable	Example Value	Required
CHATGPT_CLIENT_ID_CLARITY	from ChatGPT dev console	Yes
CLARITY_MCP_SERVER_URL	https://clarity-mcp.railway.app	Yes
CLARITY_OAUTH_ISSUER_URL	https://www.priority-guard.com/oauth/pg	Yes
CLARITY_JWKS_URL	https://www.priority-guard.com/oauth/pg/jwks	Yes
CLARITY_ISSUER	https://www.priority-guard.com	Yes
CLARITY_AUDIENCE	https://www.priority-guard.com	Yes
CLARITY_BACKEND_URL	https://backend.railway.app	Yes
INTERNAL_API_SECRET	generated secret	Yes
ENV	production	Yes

File to create: mcp_server/clarity/ENV_TEMPLATE.md

6. ChatGPT Connector Registration

Manual step — required before launch

Open ChatGPT developer console

Register Clarity connector

Configure OAuth to use Priority Guardian OAuth provider

Copy client_id → set as CHATGPT_CLIENT_ID_CLARITY

Document in: mcp_server/clarity/DEPLOYMENT.md

Tests Summary
Unit Tests

Dispatcher-level unknown tool fail-closed test

validate_jwt short-circuit test

Integration / System Tests

OAuth JWKS + claim validation test

Backend INTERNAL_API_SECRET enforcement test

Success Criteria (Final)

✅ Unknown tool requests provably fail closed at handler boundary

✅ Auth short-circuits before JWT validation when token missing

✅ OAuth validation verified via automated JWKS/claims test

✅ Backend persistence protected by enforced internal secret

✅ Production env vars documented

✅ Connector registered and documented

✅ All tests pass in CI

Files to Create / Modify
MODIFY:
  mcp_server/clarity/mcp_auth.py (only if dispatcher test proves gap)
  tests/unit/mcp/clarity/test_auth.py
  tests/unit/mcp/clarity/test_dispatcher.py (or equivalent)

CREATE:
  tests/integration/oauth/test_oauth_validation.py
  tests/integration/clarity/test_internal_auth.py
  mcp_server/clarity/ENV_TEMPLATE.md
  mcp_server/clarity/DEPLOYMENT.md

Out of Scope (Explicitly Deferred)

CORS restriction

Token refresh behavior

Rate limiting

Path-qualified issuer