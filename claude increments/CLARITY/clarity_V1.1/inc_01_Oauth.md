PG production output confirmed as the canonical reference. Now I have everything needed.
Here's the full diff between Clarity and PG that needs to be fixed:
discovery.py — 3 changes:

oauth_protected_resource: MCP_SERVER_URL → f"{MCP_SERVER_URL}/mcp"
openid_configuration + oauth_authorization_server: add missing fields response_types_supported, grant_types_supported, token_endpoint_auth_methods_supported

config.py — 1 change:
Clarity constructs discovery URLs by appending to OAUTH_ISSUER_URL (which already contains /oauth/pg), while PG separates OAUTH_ISSUER_BASE (domain only) from OAUTH_ISSUER_URL (domain + path). The end result is identical in production, but the pattern is inconsistent and fragile. This is a refactor though — not strictly needed to unblock resubmission.

My recommendation: Fix only what's needed for resubmission now. The config.py refactor is a non-breaking internal cleanup — do it post-submission.

Here's the Claude Code briefing:

Briefing: Align Clarity Discovery Endpoints with PG Standard
Context: Clarity's OAuth discovery endpoints diverge from the Priority Guardian pattern, which is the verified working standard in production. This fix is required for resubmission to the OpenAI GPT store.
Scope: One file only — mcp_server/clarity/discovery.py
Before starting: Read OPERATIONS_PREDEPLOYMENT.md (if it exists for Clarity) and check for any pre-deploy tasks.

Required changes to mcp_server/clarity/discovery.py:
1. Fix oauth_protected_resource — resource must include /mcp path:
Current:
python"resource": MCP_SERVER_URL,
Required:
python"resource": f"{MCP_SERVER_URL}/mcp",
2. Add missing fields to openid_configuration and oauth_authorization_server:
Both functions are missing these three fields that PG returns:
python"response_types_supported": ["code"],
"grant_types_supported": ["authorization_code", "refresh_token"],
"token_endpoint_auth_methods_supported": ["none"],
PG production output is the canonical reference:
json{
  "resource": "https://pg.priority-guard.com/mcp",
  "authorization_servers": ["https://www.priority-guard.com"],
  "scopes_supported": ["pg.access"]
}
Clarity must match this structure exactly, substituting clarity.priority-guard.com and clarity.write.
Copy and adjust only — do not rewrite, restructure, or improve anything not listed above.

Unit test: Verify the three functions return the correct structure with the correct fields. No integration test needed — this is pure static data.
After deploy: Confirm with:
bashcurl https://clarity.priority-guard.com/.well-known/oauth-protected-resource
curl https://clarity.priority-guard.com/.well-known/oauth-authorization-server
Expected resource value: https://clarity.priority-guard.com/mcp