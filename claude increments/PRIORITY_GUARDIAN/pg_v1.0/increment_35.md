Valuable. All three points are real. Fold them in:

Increment: OAuth B2-5 + B2-8 Compliance Fix
Context
Two verified OAuth compliance gaps must be closed before OpenAI store submission. Both are in the shared backend OAuth provider, which serves all SDK apps in the suite. Changes affect Clarity and Focused equally — this is not PG-specific.
Read OPERATIONS.md before deployment and check for additional pre-deploy tasks.

Gap 1 — B2-5: resource parameter not echoed into JWT aud claim
What the spec requires:
ChatGPT sends resource=<mcp_server_url> on both the /authorize and /token requests. The authorization server must accept it on both, carry it through the code exchange and refresh grant, echo it into the JWT aud claim, and validate consistency between the two requests.
Current state:

authorize.py: resource= not in function signature — not accepted, not stored
authorization_service.py: no resource field in Redis auth context
OAuthAuthorizationCode model: no resource column
OAuthAccessToken model: no resource column
token_endpoint.py: resource= not accepted
token_service.py / jwt/utils.py: aud hardcoded to settings.OAUTH_ISSUER
mcp_auth.py (PG): validates aud against PG_AUDIENCE = OAUTH_ISSUER — works today, breaks once aud becomes MCP server URL

What needs to change:

authorize.py — accept optional resource query parameter. Store in auth context. If absent, no error — fallback behavior exists for non-ChatGPT clients and legacy flows.
authorization_service.py — include resource field in the Redis auth context dict.
OAuthAuthorizationCode DB model + Alembic migration — add nullable resource column (VARCHAR). Must survive code exchange.
OAuthAccessToken DB model + same migration — add nullable resource column (VARCHAR). During exchange_authorization_code(), copy resource to the new OAuthAccessToken row per the resolution rules in point 6. This is required so the refresh grant path can re-apply the correct audience without access to the original auth code.
token_endpoint.py — accept optional resource form parameter.
token_service.py / exchange_authorization_code() — enforce the following resource resolution rules before token issuance, in this order:

auth_code.resource is set, /token omits resource → use auth_code.resource as aud (downgrade protection — cannot remove)
auth_code.resource is set, /token sends matching resource → use auth_code.resource as aud
auth_code.resource is set, /token sends different resource → return 400 invalid_request (cannot change)
auth_code.resource is NULL, /token sends resource → accept it, use as aud, store on OAuthAccessToken.resource
auth_code.resource is NULL, /token omits resource → fall back to settings.OAUTH_ISSUER as aud


token_service.py / exchange_refresh_token() — read resource from the existing OAuthAccessToken row and pass it to create_access_token(). This is the only source of truth for resource during refresh — the original auth code is no longer available.
jwt/utils.py / create_access_token() — accept optional resource parameter, use as aud when provided, fall back to settings.OAUTH_ISSUER when absent.
mcp_auth.py per app — update aud validation to accept both the app's own configured MCP server URL and OAUTH_ISSUER as valid audience values. Each app accepts its own URL only — PG accepts PG_MCP_SERVER_URL, Clarity accepts its own configured URL, Focused accepts its own. Strict exact string equality only — no prefix matching, no wildcards, no "starts with" logic. Both values must be accepted during transition (tokens issued before this fix carry the old aud).
Check mcp_server/clarity/mcp_auth.py and mcp_server/focused/mcp_auth.py — if they perform aud validation, apply the same dual-audience acceptance with exact equality against their respective configured MCP server URLs.


Gap 2 — B2-8: Redirect URI allowlist not enforced in DCR
What the spec requires:
Both of these URIs must be pre-allowlisted and are the only URIs the authorization server should accept from OAuth provider clients:

https://chatgpt.com/connector_platform_oauth_redirect
https://platform.openai.com/apps-manage/oauth

Current state:
validate_redirect_uris() in client_metadata.py only checks HTTPS. Any HTTPS URI is accepted and stored. An attacker can register arbitrary redirect targets.
What needs to change:

client_metadata.py / validate_redirect_uris() — add allowlist parameter. Reject any URI not in the allowlist with a clear error. Exact string matches only — no subdomains, no wildcards, no regex.
backend/core/config.py — add OAUTH_ALLOWED_REDIRECT_URIS as a list config variable with the two ChatGPT URIs as defaults. Must be overridable via environment for future environments.
register_client.py — pass the configured allowlist into validate_redirect_uris().
If existing tests use localhost redirect URIs for DCR, add a dev-mode bypass scoped to IS_DEV=true only. Do not add this unless tests require it — check first before implementing.


Files to modify
backend/core/oauth_provider/authorize.py
backend/core/oauth_provider/services/authorization_service.py
backend/core/oauth_provider/models.py
backend/alembic/versions/<new_migration>.py
backend/core/oauth_provider/token_endpoint.py
backend/core/oauth_provider/services/token_service.py
backend/core/oauth_provider/jwt/utils.py
backend/core/oauth_provider/validators/client_metadata.py
backend/core/config.py
backend/core/oauth_provider/register_client.py
mcp_server/priority_guardian/mcp_auth.py
mcp_server/clarity/mcp_auth.py    (verify first — only if aud validation exists)
mcp_server/focused/mcp_auth.py    (verify first — only if aud validation exists)

Unit Tests
File: tests/unit/oauth_provider/test_b2_compliance_unit.py
B2-5:

resource stored correctly in auth context when provided
resource absent → context has resource=None, no error
create_access_token() with resource provided → JWT aud equals resource value
create_access_token() with resource=None → JWT aud equals OAUTH_ISSUER
create_access_token() called during refresh with resource on OAuthAccessToken → JWT aud equals that resource value
Token exchange: auth_code.resource set, /token omits resource → aud = auth_code.resource
Token exchange: auth_code.resource set, /token sends matching resource → aud = auth_code.resource
Token exchange: auth_code.resource set, /token sends different resource → 400 invalid_request
Token exchange: auth_code.resource NULL, /token sends resource → aud = token resource value, stored on OAuthAccessToken
Token exchange: auth_code.resource NULL, /token omits resource → aud = OAUTH_ISSUER
validate_jwt() accepts token where aud = app's own MCP server URL (exact match)
validate_jwt() accepts token where aud = OAUTH_ISSUER (exact match, backward compat)
validate_jwt() rejects token where aud is neither — exact equality enforced
validate_jwt() rejects token where aud = a different app's MCP server URL

B2-8:

validate_redirect_uris() with https://chatgpt.com/connector_platform_oauth_redirect → valid
validate_redirect_uris() with https://platform.openai.com/apps-manage/oauth → valid
validate_redirect_uris() with both URIs in one registration → valid
validate_redirect_uris() with arbitrary HTTPS URI → rejected
validate_redirect_uris() with HTTP URI → rejected
validate_redirect_uris() with empty list → rejected
Custom allowlist passed in → only those URIs accepted
Subdomain of allowed URI (e.g. https://sub.chatgpt.com/...) → rejected


Integration Tests
File: tests/integration/oauth_provider/test_b2_compliance_integration.py
B2-5:

Full authorize(resource) → token exchange(resource): JWT aud = resource value, OAuthAccessToken.resource = same value
Full authorize(resource) → token exchange(no resource): JWT aud = authorize resource (downgrade protection), OAuthAccessToken.resource = authorize resource
Full authorize(no resource) → token exchange(resource): JWT aud = token resource, OAuthAccessToken.resource = token resource
Full authorize(no resource) → token exchange(no resource): JWT aud = OAUTH_ISSUER
Token exchange: /token resource mismatches auth code resource → 400 invalid_request
Full authorize(resource) → token exchange → refresh: all three issued JWTs have aud = original resource value
Full authorize(no resource) → token exchange(resource) → refresh: refresh JWT aud = token-introduced resource value
Token with aud = app's MCP server URL accepted by mcp_auth.py authenticate_request()
Token with aud = OAUTH_ISSUER (legacy) still accepted by mcp_auth.py
Token with aud = a different app's MCP server URL rejected by mcp_auth.py

B2-8:

DCR POST to /oauth/pg/register with https://chatgpt.com/connector_platform_oauth_redirect → 200
DCR POST to /oauth/pg/register with https://platform.openai.com/apps-manage/oauth → 200
DCR POST to /oauth/pg/register with arbitrary HTTPS URI → 400
DCR POST to /oauth/focused/register with allowed URI → 200
DCR POST to /oauth/focused/register with disallowed URI → 400

DB integrity (run before deployment):

oauth_authorization_codes table has resource column after migration
oauth_access_tokens table has resource column after migration
Both columns are nullable — insert with resource=NULL succeeds on both tables
Both columns accept URL string value
Existing rows unaffected after migration


Acceptance Criteria

 resource= accepted (not required) on both /authorize and /token
 All five resource resolution rules enforced in exchange_authorization_code() per the table in point 6
 resource copied from auth code to OAuthAccessToken on code exchange (or token-introduced value stored when auth code has none)
 Refresh grant re-issues JWT with aud = OAuthAccessToken.resource when set
 Each app's mcp_auth.py accepts its own MCP server URL and OAUTH_ISSUER as valid aud, exact equality only, rejects other apps' URLs
 DCR rejects any redirect URI not in configured allowlist, exact matches only
 Both ChatGPT redirect URIs configured and accepted
 All existing OAuth integration tests pass
 DB migration passes integrity tests before deployment
