Both suggestions are valid. Let me check one thing before updating:Used filesystem integration, ran a commandUsed filesystem integration, ran a commandCritical finding: settings in the backend has no MCP_SERVER_URL. The MCP server URL lives in mcp_server/priority_guardian/config.py, not in the backend config. The backend doesn't know its own MCP server's URL.Read Text FileRead Text FileNow the situation is clear. The backend has no MCP_SERVER_URL in settings. The correct fix is to add PG_MCP_SERVER_URL to the backend's Settings and use it to construct the header. Here's the updated final briefing:

Claude Code Briefing: B2-7 — WWW-Authenticate Header on Backend 401 Responses
Context
The Priority Guardian shared backend is a FastAPI app acting as an OAuth 2.1 provider (inbound: ChatGPT connects to it). Per the OpenAI Apps SDK authentication spec (compliance item B2-7), when the backend returns a 401 on OAuth endpoints, the response must include:
WWW-Authenticate: Bearer resource_metadata="<PG_MCP_SERVER_URL>/.well-known/oauth-protected-resource"
This tells ChatGPT where to find the Protected Resource Metadata to re-trigger the OAuth flow. This is backend-only — do not touch the MCP server.
Config gap to fix first
backend/core/config.py → Settings class has no MCP_SERVER_URL field. The MCP server URL lives only in mcp_server/priority_guardian/config.py (env var PG_MCP_SERVER_URL). Before adding the header, add this field to the backend's Settings:
pythonPG_MCP_SERVER_URL: str = "http://localhost:8003"
This env var already exists on Render for the MCP server — the backend just needs to read it too.
Then define the header value once, at module level in main.py:
pythonRESOURCE_METADATA_URL = f"{settings.PG_MCP_SERVER_URL}/.well-known/oauth-protected-resource"
WWW_AUTHENTICATE_VALUE = f'Bearer resource_metadata="{RESOURCE_METADATA_URL}"'
What triggers a 401 on OAuth endpoints
In the current codebase, 401 responses on /oauth/* paths come from exactly two places:

InvalidClientError raised → caught by the existing @app.exception_handler(OAuthError) in backend/main.py
Direct JSONResponse(status_code=401, ...) in token_endpoint.py (two occurrences — one per grant type)

All other OAuth errors (invalid_grant, PKCE mismatch, expired code, etc.) return 400. There are no other 401-producing paths on OAuth routes.
Implementation
In backend/main.py — update oauth_exception_handler:
Add the header when the error is a 401 AND the path starts with /oauth/ AND the header is not already present.
In backend/core/oauth_provider/token_endpoint.py — update both direct JSONResponse(status_code=401) returns:
Add the WWW-Authenticate header to those response objects. Use the same WWW_AUTHENTICATE_VALUE constant imported from main.py or defined in a shared location.
Constraints

Read doc/OPERATIONS_PREDEPLOY.md before committing
No new dependencies
No changes to the MCP server
No changes to middleware, non-OAuth routes, or exception hierarchy
Header value constructed from config, not hardcoded
Only inject header when request.url.path.startswith("/oauth/") AND status_code == 401
Only inject header if WWW-Authenticate is not already present in the response
Do not modify the response body or OAuth error JSON structure — add the header only

Acceptance criteria

Any 401 from /oauth/* includes WWW-Authenticate: Bearer resource_metadata="<PG_MCP_SERVER_URL>/.well-known/oauth-protected-resource"
401 from non-OAuth paths does NOT include this header
Existing WWW-Authenticate header on a response is preserved, not overwritten
Response body and OAuth error JSON structure are unchanged
All existing OAuth tests pass

Unit tests

invalid_client on /oauth/pg/token → 401 with correct WWW-Authenticate header, exact format Bearer resource_metadata="..."
401 from a non-OAuth path → no WWW-Authenticate header
Response already has WWW-Authenticate → not overwritten
Response body unchanged when header is added

Integration tests
None required — no DB or external API involvement. Sonnet 4.6