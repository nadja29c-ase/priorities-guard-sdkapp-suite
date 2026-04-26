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

With Increment 52 deployed, wrong values cause startup failure rather than silent misbehavior.

## Schema Change Checklist

### Adding a New PG-Owned Table?

**Extend the fresh-shell check in `reconcile_router.py`.**

The `_reconcile_user_by_subject` function in `backend/apps/priority_guardian/routers/reconcile_router.py` determines whether a CoreUser is a "fresh shell" (safe to remap to a different user). Currently it checks:
- No active (non-revoked) Google connection
- No PgPriority rows (of any status)

When adding a new table that represents meaningful user state (e.g., `pg_settings`, `pg_templates`), add an existence check for that table to the fresh-shell guard. Missing a table here silently widens the remap blast radius and risks cross-user data exposure.

### Adding a New Personal-Data Column or Table?

**Update the Data Retention Strategy detailed table in the same commit.**

The ROPA Data Categories block references the Data Retention Strategy table and does not need separate updates. Keeping retention rules in one place (the detailed table) prevents drift between two lists.

### Poetry Lock File Consistency

After any change to `pyproject.toml`, regenerate `poetry.lock` and commit both files together:

```bash
poetry lock
git add pyproject.toml poetry.lock
git commit -m "deps: <what changed>"
```

**Suite-wide impact:** All Render services deployed from this repo (backend, PG OpenAI MCP, PG Claude MCP, MindSort MCP, and any other MCP services) share this `pyproject.toml` + `poetry.lock`. A dependency change affects every service.

Render installs production dependencies via `poetry install --no-root --only main` (set as Build Command on every service). If `poetry.lock` is out of sync with `pyproject.toml`, Render builds will fail with a lock-file-stale error. This is intentional — it prevents silent dependency drift between local and production.

`requirements_fullbackend.txt` was removed in Increment 81 Commit 2. Do not reintroduce it — `pyproject.toml` + `poetry.lock` are the single source of truth for every service deployed from this repo.

**Resuming a suspended Render service:** If you resume a service that was suspended during/before the Poetry migration (PG Claude MCP, Focused, Sharpen), update its Build Command to `poetry install --no-root --only main` and set env var `POETRY_VERSION=2.2.0` BEFORE triggering its first deploy. Otherwise the build will fail — the old `pip install -r requirements_fullbackend.txt` references a file that no longer exists in the repo.

---

## Better Stack Log Shipping

### Overview

The backend and MCP servers ship structured JSON logs to Better Stack via `logtail-python`. The shared logging module (`shared/logging.py`) handles configuration for both services.

### Environment Variables

| Variable | Required On | Value |
|----------|-------------|-------|
| `BETTER_STACK_SOURCE_TOKEN` | Backend, PG OpenAI MCP | Token from Better Stack source settings |
| `SERVICE_NAME` | Backend, PG OpenAI MCP | `priority-guardian-backend` (backend) / `priority-guardian-mcp` (MCP) |

**Each service needs these env vars set independently.** Render does not propagate env vars across services.

**Why SERVICE_NAME matters:** All suite logs flow into a single Better Stack source. The `service` field (injected automatically by `shared/logging.py`) is how you filter backend vs MCP logs in saved views. If `SERVICE_NAME` is unset on a service, its logs are tagged `priority-guard-suite` and become indistinguishable from other services — degrading the value of saved views and alerts.

If the env var is unset or empty, the service runs normally but logs only to stdout — fine for local dev, not desired in production.

### Post-Deploy Verification

After setting the env var on a Render service:

1. Restart the service (or trigger a deploy)
2. Open Better Stack → Live Tail
3. Verify the `logging.betterstack.enabled` startup event appears within ~30 seconds
4. The `service` field should identify the service (`priority-guardian-backend`, `priority-guardian-mcp`)

### Deferred Services

The **PG Claude MCP server** (`mcp_server/priority_guardian_claude/`) is currently deprecated. When PG is submitted to the Claude MCP Directory and this service is reactivated:

1. Add `BETTER_STACK_SOURCE_TOKEN` to its Render env vars
2. Add `SERVICE_NAME=priority-guardian-claude-mcp` to its Render env vars
3. Add `configure_logging()` call inside `server_dupl.py`'s `create_app()` (same pattern as PG OpenAI MCP's `server.py`)
4. Follow the "Resuming a suspended Render service" checklist in the Poetry Lock section

Same applies to any future MCP service in the suite (Focused, Sharpen, MindSort, etc.).

### Graceful Degradation

If Better Stack is unreachable or the token is invalid at startup, the service continues normally with stdout-only logging. The `logging.betterstack.init_failed` warning will appear in stdout. This is intentional — Better Stack is a best-effort transport, not a startup dependency.

---

## Deploy Reminder

**After pushing changes to the shared backend**, manually redeploy the service on Render.

Render does not auto-deploy on push — you must trigger it manually:
1. Go to Render Dashboard → priority-guardian service
2. Click "Manual Deploy" → "Deploy latest commit"

Changes to `backend/` are not live until the service is redeployed.
