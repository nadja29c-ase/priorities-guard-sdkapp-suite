# Clarity MCP Server Deployment Guide

## Prerequisites

1. Backend API deployed and running
2. OAuth provider configured in backend
3. Environment variables set (see `ENV_TEMPLATE.md`)

## Render Deployment

The Clarity MCP server is deployed on Render as a web service.

### Service Configuration

- **Name:** `priorities-guard-clarity-mcp`
- **Region:** Frankfurt (or closest to your users)
- **Build Command:** `poetry install --no-root --only main` (env var `POETRY_VERSION=2.2.0` required)
- **Start Command:** `uvicorn mcp_server.clarity.server:app --host 0.0.0.0 --port $PORT`
- **Plan:** Starter or higher

### URLs

| Endpoint | URL |
|----------|-----|
| MCP Server | `https://mindsort.priority-guard.com` |
| MCP Endpoint | `https://mindsort.priority-guard.com/mcp` |
| OAuth Discovery | `https://mindsort.priority-guard.com/.well-known/oauth-protected-resource` |

## ChatGPT Connector Registration

MindSort is registered as a ChatGPT dev connector. The connector uses OAuth 2.0 with PKCE for authentication.

### Connector Configuration

- **MCP URL:** `https://mindsort.priority-guard.com/mcp`
- **Authorization URL:** `{BACKEND_URL}/oauth/pg/authorize`
- **Token URL:** `{BACKEND_URL}/oauth/pg/token`
- **Scopes:** `clarity.write`
- **PKCE:** Required

### After Registration

1. Copy the generated `client_id` from the ChatGPT developer console
2. Set as `CHATGPT_CLIENT_ID_CLARITY` environment variable on Render
3. Redeploy the service

## Manual Testing

### Using MCP Inspector

1. Install MCP Inspector (if not already installed)
2. Connect to: `https://mindsort.priority-guard.com/mcp`
3. Authenticate using your OAuth provider (Inspector supports guided OAuth flow)

### Using curl

```bash
# Check OAuth discovery
curl https://mindsort.priority-guard.com/.well-known/oauth-protected-resource

# Call tool (requires valid JWT)
curl -X POST https://mindsort.priority-guard.com/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "method": "tools/call",
    "params": {
      "name": "organize_thoughts",
      "arguments": {
        "user_thoughts_exhausted_verbatim": "that is it",
        "user_confirmed_no_more_thoughts": true,
        "thoughts_exhausted": true,
        "clusters": [
          {"cluster_name": "Work", "thought_items": ["Finish report", "Email client"]},
          {"cluster_name": "Personal", "thought_items": ["Buy groceries", "Call mom"]}
        ]
      }
    }
  }'
```

## Verification Checklist

After deployment, verify:

- [ ] Service is running (check Render logs)
- [ ] OAuth discovery endpoint responds
- [ ] JWT validation works with test tokens
- [ ] Persistence to backend works
- [ ] Internal secret is enforced in production

## Troubleshooting

### Common Issues

1. **ImportError on startup**
   - Check all Python files are committed and pushed
   - Verify the dependency is declared in `pyproject.toml` and `poetry.lock` is current (run `poetry lock` locally if in doubt)

2. **OAuth validation fails**
   - Verify `CLARITY_ISSUER` matches token's `iss` claim
   - Verify `CLARITY_AUDIENCE` matches token's `aud` claim
   - Check JWKS URL is accessible

3. **Persistence fails**
   - Verify `CLARITY_BACKEND_URL` is correct
   - Verify `INTERNAL_API_SECRET` matches backend's value
   - Check backend logs for errors

4. **403 on tool calls**
   - Token may lack `clarity.write` scope
   - Check OAuth provider scope configuration
