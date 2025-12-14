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
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `uvicorn mcp_server.clarity.server:app --host 0.0.0.0 --port $PORT`
- **Plan:** Starter or higher

### URLs

| Endpoint | URL |
|----------|-----|
| MCP Server | `https://priorities-guard-clarity-mcp.onrender.com` |
| MCP Endpoint | `https://priorities-guard-clarity-mcp.onrender.com/mcp` |
| OAuth Discovery | `https://priorities-guard-clarity-mcp.onrender.com/.well-known/oauth-protected-resource` |

## ChatGPT Connector Registration

**Note:** ChatGPT connector registration is not yet available. This section documents the expected process for when it becomes available.

### Expected Steps

1. **Access Developer Console**
   - Go to ChatGPT developer console (URL TBD)
   - Log in with your OpenAI account

2. **Create New Connector**
   - Click "Create Connector" or equivalent
   - Select "MCP Server" type

3. **Configure OAuth**
   - **Authorization URL:** `{BACKEND_URL}/oauth/pg/authorize`
   - **Token URL:** `{BACKEND_URL}/oauth/pg/token`
   - **Scopes:** `clarity.write`
   - **PKCE:** Required

4. **Configure MCP Endpoint**
   - **MCP URL:** `https://priorities-guard-clarity-mcp.onrender.com/mcp`

5. **Copy Client ID**
   - After registration, copy the generated `client_id`
   - Set as `CHATGPT_CLIENT_ID_CLARITY` environment variable

6. **Redeploy**
   - Update environment variable on Render
   - Service will automatically redeploy

## Manual URL Connection (Current Method)

Until ChatGPT connector registration is available, you can test the MCP server manually:

### Using MCP Inspector

1. Install MCP Inspector (if not already installed)
2. Connect to: `https://priorities-guard-clarity-mcp.onrender.com/mcp`
3. Authenticate using your OAuth provider

### Using curl

```bash
# Check OAuth discovery
curl https://priorities-guard-clarity-mcp.onrender.com/.well-known/oauth-protected-resource

# Call tool (requires valid JWT)
curl -X POST https://priorities-guard-clarity-mcp.onrender.com/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"method": "tools/call", "params": {"name": "cluster_raw_thoughts", "arguments": {...}}}'
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
   - Verify requirements.txt includes all dependencies

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
