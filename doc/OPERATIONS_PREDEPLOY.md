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

## Widget Bundle Changes

The PG widget bundle is built by Vite (`mcp_server/priority_guardian/widget-react/`) and committed as a single inlined HTML file at `mcp_server/priority_guardian/widgets/pg-dashboard.html`. The PG MCP server loads this file ONCE at module import (`handlers/resources.py` → `_load_widget_html()`) — meaning every Render deploy restarts the server and reloads the file fresh, but the file must be correct on disk before commit.

### Pre-commit checks (any change to `widget-react/src/` or a `WIDGET_URI` bump)

```bash
cd mcp_server/priority_guardian/widget-react && npm run build
cd -

# Verify the bundle is correctly inlined — NOT split into /assets/
grep -c '<script[^>]*src="' mcp_server/priority_guardian/widgets/pg-dashboard.html
# Must return 0. Non-zero means viteSingleFile broke; widget will load externally
# and ChatGPT will serve a stale cache from oaiusercontent.com instead.

# Verify Vite-injected constants were replaced (when applicable)
grep -c "__WIDGET_BUILD_TIME__" mcp_server/priority_guardian/widgets/pg-dashboard.html
# Must return 0 if the constant is being used. Non-zero means Vite's `define`
# block didn't fire — the diagnostic code in the bundle will run with an
# undefined constant and either fail silently or report wrong build times.

# Verify file size is reasonable (~350KB+ for current bundle)
ls -la mcp_server/priority_guardian/widgets/pg-dashboard.html
```

### Pre-commit checks (any `WIDGET_URI` bump)

`WIDGET_URI` is the single source of truth in `tools/widget_tools/constants.py`. The resource handler imports it from there. If you see a hardcoded `WIDGET_URI = "..."` anywhere else in the PG codebase, that is a bug — fix it to import from `tools.widget_tools.constants` instead. Two copies will drift and the resource handler will return empty for the advertised URI, causing ChatGPT to fall back to its CDN cache (which can be weeks old).

To verify there is only one source of truth:

```bash
grep -rn "WIDGET_URI = " mcp_server/priority_guardian/ --include="*.py" | grep -v __pycache__
# Should return exactly ONE match — the assignment in tools/widget_tools/constants.py.
# All other files must IMPORT it, not redefine it.
```

### Post-deploy verification (production iframe console)

After deploying a widget bundle change AND completing the cache-bust dance (restart MCP server on Render, click Refresh in ChatGPT → Settings → Apps → Priority Guardian, start a NEW conversation), open DevTools, switch context to the widget iframe (the `pg-priority-guard-com.web-sandbox.oaiusercontent.com` frame), and run:

```javascript
// Must return 1
document.querySelectorAll('script').length

// Must return ~340000+ — the inlined bundle.
// If 0, ChatGPT is serving a cached widget from oaiusercontent.com,
// not your MCP server. The deploy did NOT take effect.
document.querySelector('script').textContent.length

// If the bundle uses __WIDGET_BUILD_TIME__ (or any similar Vite-injected
// constant), the timestamp string should be present in the bundle text:
document.documentElement.innerHTML.includes('2026-')  // adjust year
```

If the bundle is loaded externally (`textContent.length: 0` AND the script tag has a `src=https://.../assets/main-*.js` attribute), the deploy did not take effect. Check Render PG MCP logs for `resource.read.requested` events at the deploy time:

```
{"event": "resource.read.requested", "uri": "ui://widget/pg-dashboard-vN.html", ...}
{"event": "resource.read.serving_widget", "uri": "ui://widget/pg-dashboard-vN.html", ...}
```

If `resource.read.requested` appears with a URI that the handler doesn't recognize, you'll see NO matching `serving_widget` event — that's the failure mode. Bump `WIDGET_URI` in `constants.py` to a clearly new value (v14 → v15) and redeploy.

### Why this matters

The PG MCP resource handler responds to `ui://widget/pg-dashboard-vN.html` requests. If ChatGPT requests a URI the handler doesn't recognize (because `WIDGET_URI` is hardcoded somewhere out-of-sync), the handler returns an empty result and ChatGPT silently falls back to whatever it has cached at the `oaiusercontent.com` CDN — which can be weeks old. No error appears in logs. The widget appears to render but is running stale code. This failure mode hides production bugs from your diagnostic work and made Increment 89's diagnostic instrumentation invisible for hours.

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

---

## Backend Domain Notes

- **Apex redirect:** `priority-guard.com` 301-redirects to `www.priority-guard.com` (configured in Render).
- **robots.txt:** The backend serves `GET /robots.txt` returning `User-agent: *\nDisallow: /\n`. This is intentional — the backend is OAuth/API only, not a public content surface. The marketing site is `fulfilling-productivity.com`.

---

## MindSort Claude MCP — Deploy Runbook (Widget-A and after)

This section is MindSort-Claude-specific. The PG widget guidance above is written for PG/ChatGPT paths and does NOT translate 1:1 — do not follow it verbatim for MindSort. Service code lives in `mcp_server/mindsort_claude/`; widget bundle at `mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html`.

### Widget bundle facts (verified)
- Single source of truth for the URI: `WIDGET_URI` in `handlers/resources_dupl.py` (`ui://mindsort-claude/dashboard-v1.html`). Both consumers (`tools_list_dupl.py`, `handlers/tools_dupl.py`) IMPORT it. Do not hardcode it anywhere else.
- The server loads the HTML ONCE at module import: `WIDGET_HTML = _load_widget_html()` in `resources_dupl.py`. A Render restart/redeploy reloads it fresh, so the file must be correct AND committed before deploy.
- **Silent-failure trap:** `_load_widget_html()` catches FileNotFoundError/PermissionError/any error and returns `WIDGET_FALLBACK_HTML` ("Widget failed to load"). If the bundle is missing or uncommitted, the server starts FINE, serves the fallback, and logs a single `widget.load.file_not_found`. No crash, no failed deploy. The widget just shows the failure text. Watch for that log line after deploy.

### Pre-commit / pre-deploy checks (any change under `widget-react/src/` or a WIDGET_URI bump)
```bash
# 1. Build the bundle
cd mcp_server/mindsort_claude/widget-react && npm run build && cd -

# 2. Verify it's the inlined bundle, NOT the placeholder
grep -c "MindSort Widget (placeholder)" mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html   # must be 0
grep -c 'react.production.min' mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html            # must be >=1

# 3. Verify single-file inlining (no external asset split)
grep -c '<script[^>]*src="' mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html               # must be 0

# 4. Verify single WIDGET_URI source of truth
grep -rn "WIDGET_URI = " mcp_server/mindsort_claude/ --include="*.py" | grep -v __pycache__                  # exactly ONE match (resources_dupl.py)

# 5. Bundle size sanity (current build ~470-480KB)
ls -la mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html

# 6. CRITICAL: confirm the bundle is COMMITTED, not just built
git status --porcelain mcp_server/mindsort_claude/widgets/mindsort-dashboard-claude.html                    # empty = committed; non-empty = STAGE + COMMIT before deploy
```
Built-but-uncommitted is the #1 deploy trap: Render builds from the committed tree, so an uncommitted bundle means production serves the OLD bytes (or the placeholder) while local looks correct.

### Render service config — set BEFORE first deploy
This service was dormant before the Poetry migration, so the Poetry build rule applies (see "Resuming a suspended Render service" above):
- **Build Command:** `poetry install --no-root --only main`
- **Env `POETRY_VERSION`** = `2.2.0` (without it, the build tries the removed `requirements_fullbackend.txt` and fails)
- **Start Command:** `uvicorn mcp_server.mindsort_claude.server_dupl:create_app --factory --host 0.0.0.0 --port $PORT`

**Required env vars** (from `mcp_server/mindsort_claude/config.py`). Two of these HARD-FAIL startup if unset in production — that is intentional fail-fast, but it means you must set them first:

| Variable | Value | Note |
|----------|-------|------|
| `ENV` | `production` | enables the prod startup guards |
| `CLARITY_CLAUDE_MCP_SERVER_URL` | `https://mindsort-mcp.priority-guard.com` (deployed origin, **NO** `/mcp`) | putting `/mcp` here produces `/mcp/mcp` and breaks the resource claim, .well-known URLs, AND the `ui.domain` hash. This is the custom domain mapped to the Render service `priorities-guard-sdkapp-suite-6jri.onrender.com`; the env var must use the custom domain, not the onrender.com URL, so the `ui.domain` hash matches the host Claude connects through. |
| `CLARITY_CLAUDE_OAUTH_ISSUER_URL` | `https://www.priority-guard.com/oauth/pg` | |
| `CLARITY_CLAUDE_BACKEND_URL` | `https://www.priority-guard.com` | |
| `CLARITY_CLAUDE_INTERNAL_API_SECRET` | matches backend `INTERNAL_API_SECRET` | empty string = dev-mode skip; MUST be set in prod |
| `CLARITY_CLAUDE_JWKS_URL` | `https://www.priority-guard.com/oauth/pg/jwks` | |
| `CLARITY_CLAUDE_ISSUER` | `https://www.priority-guard.com` | JWT `iss` claim |
| `CLARITY_CLAUDE_AUDIENCE` | `https://www.priority-guard.com` | JWT `aud` claim |
| `CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS` | `https://claude.ai` | **HARD-FAILS startup if unset in prod/staging** |

Optional but recommended (Better Stack log separation): `BETTER_STACK_SOURCE_TOKEN` and `SERVICE_NAME=mindsort-claude-mcp`. Note: `server_dupl.py` does not yet call `configure_logging()` — wiring Better Stack requires adding that call (same pattern as PG OpenAI MCP). Until then logs go to stdout only.

### Deploy sequence
1. Run all pre-commit checks above; confirm bundle committed (#6).
2. `git status` clean; if `pyproject.toml` changed at any point, `poetry lock` and commit both (a stale lock fails EVERY service's build, not just this one).
3. Push to the branch Render builds from.
4. Confirm the Render service Build/Start commands + env vars above (especially `POETRY_VERSION`, `ENV=production`, `CLARITY_CLAUDE_CORS_ALLOWED_ORIGINS`).
5. Render Dashboard → MindSort Claude MCP service → **Manual Deploy → Deploy latest commit** (Render does not auto-deploy this repo).

### Post-deploy verification
```bash
# OAuth discovery (issuer must be root domain, no path — same invariant as PG)
curl https://mindsort-mcp.priority-guard.com/.well-known/oauth-protected-resource
#   "resource"               == https://mindsort-mcp.priority-guard.com/mcp
#   "authorization_servers[0]" == https://www.priority-guard.com
curl https://mindsort-mcp.priority-guard.com/.well-known/oauth-authorization-server
#   "issuer" == https://www.priority-guard.com
```
The `resource` claim must show the custom domain (`mindsort-mcp.priority-guard.com`), not the onrender.com URL. If it shows the onrender URL, `CLARITY_CLAUDE_MCP_SERVER_URL` did not take effect (or still points at onrender) — fix and redeploy, because the `ui.domain` hash is derived from this value and a mismatch breaks widget rendering.
Then check Render logs for the widget-load path at startup:
- GOOD: a `resource.read.serving_widget` event appears when Claude first reads the resource, with a non-trivial `html_length`.
- BAD: `widget.load.file_not_found` at startup → the server is serving `WIDGET_FALLBACK_HTML`. The bundle isn't on disk in the container (uncommitted, or wrong path). Fix and redeploy.

### Client cache-bust (Claude — NOT the ChatGPT refresh dance)
Widget bundle bytes change on every deploy; only the URI is frozen at approval. Claude caches the bundle. To force the new bytes:
**Delete the MindSort connector and re-add it, then start a NEW conversation.** Disconnect/reconnect is NOT sufficient. (This differs from the PG/ChatGPT "Refresh in Settings → Apps" flow above.)

### First-render smoke test (resolves parked questions)
In a fresh Claude conversation, trigger a widget-producing tool (e.g. organize_thoughts). Confirm the inline summary renders. This is where the parked items resolve empirically:
- Does MIME `text/html;profile=mcp-app` render? (PG ships `text/html+mcp`; if MindSort renders blank but PG renders, suspect MIME.)
- Does the host need tool-level `domain` on `_meta`? (MindSort omits it; PG includes it.)
Report findings before changing any server file — do not change MIME/domain without a confirmed root cause.
