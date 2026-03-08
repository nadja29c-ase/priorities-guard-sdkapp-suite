# Operations Notes

## PostgreSQL Version

| Environment | Version | Notes |
|-------------|---------|-------|
| Production  | 16 | Render managed PostgreSQL |
| Local tools | 16 | `brew install postgresql@16` |

When Render upgrades PostgreSQL, update local tools to match for `pg_dump` schema diffs.

## Render Pre-Deploy Command

Set this as the **Build Command** or **Pre-Deploy Command** in Render:

```bash
alembic heads | wc -l | grep -q "^1$" || (echo "FATAL: Multiple Alembic heads detected" && exit 1)
alembic upgrade head
```

This is system-enforced — if there are multiple heads, the deploy fails before touching the DB.

**Why this matters:** Alembic allows creating two migrations with the same `down_revision`, creating a fork. Without this check, one branch can be deployed while the other is silently ignored.

## Defense in Depth

The `alembic_version` table has a unique index `idx_alembic_version_single_row` that ensures exactly one row. If a forked migration somehow tries to insert a second version row, PostgreSQL rejects it.

## Local Pre-Deploy Checks

### Alembic Migration Fork Detection

Before pushing, verify there's only one migration head:

```bash
alembic heads | wc -l | grep -q "^1$" && echo "OK: Single head" || echo "ERROR: Multiple heads"
```

### Production Schema Diff

To verify production schema matches migrations:

```bash
# Dump production schema
pg_dump --schema-only "$PRODUCTION_DATABASE_URL" > /tmp/prod_schema.sql

# Compare against expected (use psql introspection queries)
psql "$PRODUCTION_DATABASE_URL" -c "\d+ pg_priorities"
```

### OAuth Discovery Sanity Check

After any change to OAuth config or MCP discovery code, verify:

```bash
# Backend AS discovery (source of truth)
curl https://www.priority-guard.com/.well-known/oauth-authorization-server | python3 -m json.tool
# Verify: "issuer" == "https://www.priority-guard.com" (no path, no trailing slash)

# MCP server proxied discovery (must match backend)
curl https://pg.priority-guard.com/.well-known/oauth-authorization-server
# "issuer" must equal "https://www.priority-guard.com" (matches backend OAUTH_ISSUER)
# "authorization_servers" is not present here — only in oauth-protected-resource

curl https://pg.priority-guard.com/.well-known/oauth-protected-resource
# "authorization_servers[0]" must equal "https://www.priority-guard.com"
# "resource" must equal "https://pg.priority-guard.com/mcp"
```

**Critical invariant:** `issuer` must be the root domain (`https://www.priority-guard.com`), not a path prefix (`https://www.priority-guard.com/oauth/pg`). ChatGPT fetches `{authorization_servers[0]}/.well-known/oauth-authorization-server` — path prefixes break this.

**Run after every backend deploy** — takes 10 seconds, prevents silent OAuth failures.

See `ADR_MCP Server Implementation Standard.md` → OAuth Discovery Configuration for full documentation.

### Pre-Submission Env Var Verification

Before OpenAI submission, verify Render env vars match exactly:

| Variable | Required Value |
|----------|----------------|
| `OAUTH_ISSUER` | `https://www.priority-guard.com` |
| `BACKEND_PUBLIC_URL` | `https://www.priority-guard.com` |
| `PG_MCP_SERVER_URL` | `https://pg.priority-guard.com` |

With Increment 52 deployed, wrong values cause startup failure rather than silent misbehavior.

## Deploy Reminder

**After pushing changes to the shared backend**, manually redeploy the service on Render.

Render does not auto-deploy on push — you must trigger it manually:
1. Go to Render Dashboard → priority-guardian service
2. Click "Manual Deploy" → "Deploy latest commit"

Changes to `backend/` are not live until the service is redeployed.
