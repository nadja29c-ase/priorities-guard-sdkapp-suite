Increment 14: MCP OAuth Discovery for ChatGPT Integration
Problem Statement
ChatGPT connector returns "MCP server does not implement OAuth" when connecting to our MCP server. Three gaps prevent ChatGPT from discovering our OAuth provider:

Missing discovery endpoint: /.well-known/oauth-protected-resource returns 404 on MCP server
Tools don't declare OAuth requirement: No security metadata on tool definitions
Wrong error format: Auth errors use www_authenticate instead of SDK-required _meta["mcp/www_authenticate"]

Requirements
A. Add OAuth Protected Resource Endpoint to MCP Server
File: mcp_server/focused/server.py
Add /.well-known/oauth-protected-resource route that returns:
json{
  "resource": "https://priorities-guard-focused-mcp-production.up.railway.app",
  "authorization_servers": ["https://priorities-guard-fastapi-backend-production.up.railway.app/oauth/focused"],
  "scopes_supported": ["focused.read", "focused.write", "focused.notify"]
}
Critical notes:

authorization_servers MUST include /oauth/focused path because ChatGPT appends /.well-known/openid-configuration to this URL
scopes_supported is required for ChatGPT dynamic client registration
resource must match MCP RPC entrypoint (currently /, so base URL is correct)

Use Starlette routing to mount this alongside FastMCP app. Do NOT replace FastMCP—wrap it.
B. Add security to All Tool Decorators
File: mcp_server/focused/server.py
Each tool must declare its OAuth requirement via the security parameter in the tool decorator:
python@mcp.tool(
    name="check_calendar",
    description="...",
    security=[{"type": "oauth2", "scopes": ["focused.read"]}]
)
async def check_calendar(...):
    ...

@mcp.tool(
    name="watch_calendar",
    description="...",
    security=[{"type": "oauth2", "scopes": ["focused.write"]}]
)
async def watch_calendar(...):
    ...

@mcp.tool(
    name="run_focus_mode",
    description="...",
    security=[{"type": "oauth2", "scopes": ["focused.write"]}]
)
async def run_focus_mode(...):
    ...

@mcp.tool(
    name="notify_user",
    description="...",
    security=[{"type": "oauth2", "scopes": ["focused.notify"]}]
)
async def notify_user(...):
    ...
Critical: Use security=[...] parameter directly on the decorator. Do NOT use _meta—it will be ignored.
Reference TOOL_SCOPES mapping from mcp_server/focused/config.py to keep scope definitions consistent.
C. Fix WWW-Authenticate Error Format
File: mcp_server/focused/mcp_auth.py
Unauthorized Error (no token or invalid token) — Code -32001
Change build_unauthorized_error() to return:
json{
  "error": {
    "code": -32001,
    "message": "Unauthorized",
    "data": {
      "_meta": {
        "mcp/www_authenticate": [{
          "type": "oauth2",
          "resource_metadata": "https://priorities-guard-focused-mcp-production.up.railway.app/.well-known/oauth-protected-resource"
        }]
      }
    }
  }
}
Forbidden Error (valid token but insufficient scope) — Code -32003
Change build_forbidden_error() to use different error code:
json{
  "error": {
    "code": -32003,
    "message": "Forbidden",
    "data": {
      "_meta": {
        "mcp/www_authenticate": [{
          "type": "oauth2",
          "resource_metadata": "https://priorities-guard-focused-mcp-production.up.railway.app/.well-known/oauth-protected-resource"
        }]
      }
    }
  }
}
Critical: Different error codes ensure ChatGPT distinguishes between "needs authentication" (-32001) and "insufficient permissions" (-32003).
Reference Documentation

ChatGPT Apps SDK - Authentication.md: securitySchemes examples, per-tool auth
ChatGPT Apps SDK - API Reference.md: _meta["mcp/www_authenticate"] specification
MCP Specification - Tools.md: Tool security metadata
RFC 9728: OAuth Protected Resource Metadata

Environment
ComponentURLMCP Serverhttps://priorities-guard-focused-mcp-production.up.railway.appBackend OAuth Providerhttps://priorities-guard-fastapi-backend-production.up.railway.app/oauth/focusedOIDC Discoveryhttps://priorities-guard-fastapi-backend-production.up.railway.app/oauth/focused/.well-known/openid-configuration
Config file: mcp_server/focused/config.py (contains TOOL_SCOPES and URL constants)
Verification
Step 1: Discovery endpoint
bashcurl https://priorities-guard-focused-mcp-production.up.railway.app/.well-known/oauth-protected-resource
Expected response:
json{
  "resource": "https://priorities-guard-focused-mcp-production.up.railway.app",
  "authorization_servers": ["https://priorities-guard-fastapi-backend-production.up.railway.app/oauth/focused"],
  "scopes_supported": ["focused.read", "focused.write", "focused.notify"]
}
Step 2: Verify authorization server resolves
bashcurl https://priorities-guard-fastapi-backend-production.up.railway.app/oauth/focused/.well-known/openid-configuration
Should return OIDC metadata (already implemented).
Step 3: ChatGPT connector
Retry ChatGPT connector setup with MCP server URL.
Constraints

Keep FastMCP as transport layer—do not replace
URLs must be configurable via environment variables (not hardcoded)
Follow existing code patterns in server.py and mcp_auth.py
MCP is mounted at / (root), ensure resource URL reflects this

Files to Modify

mcp_server/focused/server.py — Add discovery endpoint route, add security parameter to all tool decorators
mcp_server/focused/mcp_auth.py — Fix error response format and codes
mcp_server/focused/config.py — Add URL constants for discovery endpoint if needed