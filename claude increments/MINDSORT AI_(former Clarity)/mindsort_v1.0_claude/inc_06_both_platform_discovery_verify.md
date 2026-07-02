# Increment inc_06: both-platform shared-backend discovery verification

**Status:** Verification-only. NO code change. Run after inc_05 deploys. Confirms the backend redeploy (which activated the Claude redirect URIs) stayed additive and did not disturb the live OpenAI deployments.

**Why this exists:** the backend OAuth provider at `www.priority-guard.com` is shared by PG (both platforms) and MindSort (both platforms). The redirect-URI change was additive — `_CHATGPT_REDIRECT_URIS` retains every OpenAI entry (the code comment says "existing — do not modify") — so risk is low. But "low" must be confirmed, not assumed: these are production services, and you don't want latent OAuth breakage discovered at submission time. Cost of this check: ~2 minutes of curls. Cost of skipping and being wrong: a broken OpenAI connector found by a reviewer.

**This is NOT a Claude Code task** — it's a deployer-run checklist of curls. Included as an increment doc for traceability.

## Checks
```bash
# 1. Backend AS discovery (source of truth) — issuer must be root, registration present
curl https://www.priority-guard.com/.well-known/oauth-authorization-server | python3 -m json.tool
#   "issuer" == "https://www.priority-guard.com"
#   "registration_endpoint" present

# 2. MindSort-OpenAI protected-resource — unchanged from pre-redeploy
#    (resource URL = the clarity/ ChatGPT MCP service origin + /mcp; confirm from its Render service / clarity config)
curl https://<mindsort-openai-origin>/.well-known/oauth-protected-resource
#   "resource" and "authorization_servers" unchanged vs pre-redeploy

# 3. PG-OpenAI protected-resource — unchanged
curl https://pg.priority-guard.com/.well-known/oauth-protected-resource
#   "resource" == https://pg.priority-guard.com/mcp ; "authorization_servers[0]" == https://www.priority-guard.com

# 4. (Optional) Confirm OpenAI redirect URIs still in deployed allowlist by exercising a DCR
#    against /oauth/pg/register or /oauth/mindsort/register with a chatgpt.com redirect_uri in a
#    staging/test context — OR simply confirm the live ChatGPT connectors still connect (the
#    authoritative empirical check, since those apps are live).
```

## Pass criteria
- All discovery documents return expected, unchanged values.
- The live ChatGPT MindSort and PG connectors still connect for a real OAuth flow (the decisive empirical proof — even at 0 users, run one connect each).
- OpenAI redirect URIs (`https://chatgpt.com/connector/oauth/`, `https://platform.openai.com/apps-manage/oauth`) confirmed intact in deployed config.

## If anything differs
STOP. The backend change was not as additive as believed. Investigate before any further deploys — this is shared prod infrastructure. Do not proceed to inc_05b or inc_07 until resolved.

## Scope note
Unpack is NOT in scope — it does not use this OAuth provider (no shared-backend OAuth coupling). The shared-backend OAuth consumers are PG (both platforms) and MindSort (both platforms) only.
