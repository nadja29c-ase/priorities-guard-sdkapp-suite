# Clarity MCP Server Environment Variables

Environment variables for Render deployment.

## Required Variables

| Variable | Example Value | Description |
|----------|--------------|-------------|
| `CLARITY_MCP_SERVER_URL` | `https://priorities-guard-clarity-mcp.onrender.com` | Public URL of the Clarity MCP server |
| `CLARITY_OAUTH_ISSUER_URL` | `https://priorities-guard-sdkapp-suite.onrender.com/oauth/pg` | OAuth authorization server base URL |
| `CLARITY_JWKS_URL` | `https://priorities-guard-sdkapp-suite.onrender.com/oauth/pg/jwks` | JWKS endpoint for JWT verification |
| `CLARITY_ISSUER` | `https://www.priority-guard.com` | Expected `iss` claim in JWT tokens |
| `CLARITY_AUDIENCE` | `https://www.priority-guard.com` | Expected `aud` claim in JWT tokens |
| `CLARITY_BACKEND_URL` | `https://priorities-guard-sdkapp-suite.onrender.com` | Backend API URL for persistence |
| `INTERNAL_API_SECRET` | `<generate-strong-random-value>` | Secret for MCP→Backend communication |
| `ENV` | `production` | Environment mode |

## Optional Variables (Future)

| Variable | Example Value | Description |
|----------|--------------|-------------|
| `CHATGPT_CLIENT_ID_CLARITY` | `<from-chatgpt-console>` | ChatGPT client ID for `azp` validation. Not yet available - leave empty until ChatGPT connector marketplace launches. |

## How to Set on Render

1. Go to your Clarity MCP service in Render dashboard
2. Navigate to **Environment** tab
3. Add each variable as a key-value pair
4. Click **Save Changes**
5. Service will automatically redeploy

## Generating INTERNAL_API_SECRET

Use a cryptographically secure random generator:

```bash
# Option 1: Python
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Option 2: OpenSSL
openssl rand -base64 32
```

**Important:** Use the same `INTERNAL_API_SECRET` value for both:
- Clarity MCP server
- Backend API server

## Notes

- `CLARITY_ISSUER` and `CLARITY_AUDIENCE` should match what your OAuth provider puts in tokens
- `CHATGPT_CLIENT_ID_CLARITY` will be obtained after registering your connector in ChatGPT (not yet available)
- In dev mode, leave `INTERNAL_API_SECRET` empty to skip verification
- When `CHATGPT_CLIENT_ID_CLARITY` is empty, `azp` claim validation is skipped
