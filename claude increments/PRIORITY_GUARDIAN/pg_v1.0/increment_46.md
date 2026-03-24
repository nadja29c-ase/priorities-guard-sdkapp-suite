Increment 46 — Fix Authorization Server Discovery
Context: pg.priority-guard.com currently serves authorization server metadata that is internally inconsistent from the client's perspective: issuer=www, but token_endpoint/jwks_uri/registration_endpoint=pg. Simultaneously, the protected resource metadata points authorization_servers to pg, directing ChatGPT to fetch AS metadata from pg. This hybrid is the strongest remaining hypothesis for why ChatGPT completes the OAuth flow but aborts before calling /mcp.
www.priority-guard.com is the real Authorization Server. pg.priority-guard.com is the resource server. They must be clearly separated. The fix stops pg from pretending to be the AS.
File: mcp_server/priority_guardian/discovery.py
Three changes, all in the same file:

oauth_protected_resource() — change authorization_servers from [MCP_SERVER_URL] to [OAUTH_ISSUER_BASE]
openid_configuration() — make all endpoints fully consistent with www: authorization_endpoint, token_endpoint, jwks_uri, registration_endpoint must all use OAUTH_ISSUER_BASE, not MCP_SERVER_URL. issuer stays OAUTH_ISSUER_BASE.
oauth_authorization_server() — same as #2.

The resulting documents served from pg must be identical to what www already serves — every endpoint pointing to www. No mixed origins.
Constraints:

No changes to OAUTH_ISSUER, PG_ISSUER, PG_AUDIENCE, or any backend files
No changes to env vars on either service
No changes to OAuth proxy routes on pg (they stay in place unused)
No changes to mcp_auth.py — token validation is unaffected
This increment touches discovery.py only

No automated tests required.
Deployment: MCP server only. Read OPERATIONS_PREDEPLOYMENT.md before committing.
Verify after deploy — check all three endpoints manually:

https://pg.priority-guard.com/.well-known/oauth-authorization-server → issuer=www, all endpoints on www ✓
https://pg.priority-guard.com/.well-known/openid-configuration → same as above ✓
https://pg.priority-guard.com/.well-known/oauth-protected-resource → authorization_servers: ["https://www.priority-guard.com"] ✓
Trigger fresh ChatGPT auth flow → watch for POST /mcp in MCP server logs