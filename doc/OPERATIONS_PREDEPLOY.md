# Operations Notes

## ⚠️ Which Render service is which — READ BEFORE ANY DEPLOY

Four MCP services run from this one repo. **The names do not disambiguate them, the domains actively
mislead, and they do not share deploy settings.** Getting this wrong has already produced a session
spent reasoning about the wrong service's deploy state, and a widget "verified" against bytes that
were never deployed.

| Service ID | Render name | App it actually runs | Verified `resource` | autoDeploy |
|---|---|---|---|---|
| `srv-d6vbrt9r0fns73c6n080` | `priority-guardian-claude-mcp` | **PG · Claude** — `priority_guardian_claude.server_dupl` | `https://mcp.priority-guard.com/mcp` · `pg.access` | **YES** *(changed 2026-08-06 12:31; was NO)* |
| `srv-d90din3sq97s7399nbl0` | `priorities-guard-mindsort-claude-mcp` | **MindSort · Claude** — `mindsort_claude.server_dupl` | `https://mindsort-mcp.priority-guard.com/mcp` · `clarity.write` | **YES**, on commit |
| `srv-d64ea0khg0os73d588t0` | `priority-guard-pg-mcp` | **PG · OpenAI** — `priority_guardian.server` | `https://pg.priority-guard.com/mcp` · `pg.access` | NO |
| `srv-d4vg1c24d50c73814mi0` | `prioritiy-guard-mindsort-mcp` | **MindSort · OpenAI** — `clarity.server` | `https://mindsort.priority-guard.com/mcp` · `clarity.write` | NO |

**The two traps, in order of how much they cost:**

1. **`pg.priority-guard.com` is PG-OpenAI, NOT PG-Claude.** PG-Claude is `mcp.priority-guard.com`.
   The subdomain that reads like "PG" belongs to the other platform.
2. **Deploy settings differ per service AND change over time — read them, never remember them.**
   PG-Claude was `autoDeploy: "no"` until 2026-08-06 12:31 and is now `"yes"`. During the window when
   it was off and MindSort-Claude's was on, pushing to `main` deployed MindSort within a minute and
   did *nothing* to PG-Claude — so watching a commit go live was evidence that **MindSort** deployed,
   not PG. That cost several rounds of reasoning about the wrong service's state. **The table above is
   a snapshot; the deploy log is the truth.** Check `autoDeploy` at the moment you care, and confirm
   the deploy landed by reading the service's own deploy list — never infer it from a push.

### How to identify a service without trusting its name

Two checks, both authoritative, neither requiring the dashboard:

```bash
# 1. Ask the running service what it is. Public, no auth.
curl -s https://<host>/.well-known/oauth-protected-resource
#    resource + scopes_supported identify the app unambiguously.

# 2. Identify the service from a widget iframe already open in Claude.
#    The claudemcpcontent.com subdomain IS sha256(MCP_RESOURCE_URL)[:32] —
#    see WIDGET_APP_DOMAIN in handlers/resources_dupl.py.
python3 -c "import hashlib; print(hashlib.sha256(b'https://mcp.priority-guard.com/mcp').hexdigest()[:32])"
#    -> a7b31ccb44096357600a7460eb0a78e9   (PG-Claude)
```

Known widget-frame hashes: **PG-Claude `a7b31ccb44096357600a7460eb0a78e9`**. If the iframe origin in
DevTools does not start with that, you are not looking at PG-Claude.

### After deploying PG-Claude

**Delete the connector and re-add it, then start a NEW conversation.** Disconnect/reconnect does not
fetch new bundle bytes — Claude keeps the cached bundle, and every on-host observation will be made
against the old widget while appearing to succeed. See "Client cache-bust" below.

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

### Git Stash-Before-Overwrite Rule

Before any `git checkout`, `git restore`, or full-file overwrite of tracked files, **stash first**:

```bash
git stash push -m "before <operation>"
```

This applies even to "obviously safe" operations. A stash entry costs nothing and makes traceless loss of uncommitted work unrepresentable — if work disappears, it's recoverable from `git stash list` or `git fsck --lost-found`.

**Why this matters:** Without a stash, uncommitted-but-made work can be overwritten by a checkout or paste, leaving no recoverable trace. Git forensics can only prove "no trace exists" — they cannot distinguish "never made" from "made and traceless-overwritten." The stash closes this ambiguity path.

### Never Amend After Hook Failure

Pre-commit hook failures mean the commit **did not happen**. After fixing the issue:

```bash
git add <fixed-files>
git commit -m "..."   # NEW commit, not --amend
```

Never use `--amend` after a hook failure — it modifies the **previous** commit, which may contain unrelated work. This is how commits get silently corrupted.

### Stage Specific Files

Prefer explicit file staging over bulk operations:

```bash
git add path/to/file.py path/to/other.py   # Good
git add -A                                  # Avoid — risks staging secrets or large binaries
```

Review `git status` before every commit. Secrets (`.env`, credentials) and large binaries should never reach the repo.

### Alembic Migration Fork Detection

Before pushing, verify there's only one migration head:

```bash
alembic heads | wc -l | grep -q "^1$" && echo "OK: Single head" || echo "ERROR: Multiple heads"
```

### Production Schema Diff

To verify production schema matches migrations:

> **⚠️ These commands will FAIL by default.** As of 2026-07-30 the production
> database `priority-guardian-db` has an EMPTY external allow list — there is no
> standing external access, by design (it previously allowed `0.0.0.0/0`, i.e. the
> whole internet). See "Database External Access" below before running either command.

```bash
# Dump production schema
pg_dump --schema-only "$PRODUCTION_DATABASE_URL" > /tmp/prod_schema.sql

# Compare against expected (use psql introspection queries)
psql "$PRODUCTION_DATABASE_URL" -c "\d+ pg_priorities"
```

### Database External Access (allow list)

**Default state: EMPTY.** `priority-guardian-db` accepts NO external connections.
Changed 2026-07-30 from `0.0.0.0/0`.

What still works without any allow-list entry:
- **All Render services** — backend, Celery worker, and every MCP server connect over
  Render's internal network, which the allow list does not govern. Verified by OAuth
  token issue/refresh (a DB read+write) and Celery Beat jobs continuing after the change.

What does NOT work without an entry:
- `pg_dump` / `psql` from a local machine (the commands above).
- **The Render MCP `query_render_postgres` tool.** It connects via the EXTERNAL endpoint
  (`dpg-…frankfurt-postgres.render.com`), so agent-run diagnostic queries are blocked too.
  Do not assume otherwise: `pg_stat_activity.client_addr` shows Render's proxy address
  (private `10.x`) for external clients, so it CANNOT be used to tell internal from
  external. That inference was made and was wrong.

To run a manual dump or query:
1. Add your current public IP as a `/32` in the Render dashboard →
   `https://dashboard.render.com/d/dpg-d4o3dnumcj7s738u0img-a` → Access Control.
2. Do the work.
3. **Remove the entry.** Do not leave it — home IPs rotate, and a stale entry points at
   whoever inherits the address.

Never restore `0.0.0.0/0`. The database holds personal data (board contents, thoughts)
under GDPR; a standing internet-wide entry means any credential leak or future Postgres
CVE is exploitable from anywhere rather than from nowhere.

Verifying the app after any allow-list change (external SQL will be unavailable, so
check the app instead — `/health` is `{"status":"ok"}` and does NOT touch the DB):
```bash
# Real DB round-trip: look for oauth.token.success with old_jti -> new_jti rotation,
# and Celery Beat cleanup jobs. Zero connection errors = services still reach Postgres.
# Render dashboard → service → Logs, or the Render MCP list_logs tool.
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

### Dependency pinning and build provenance (applies to ALL widget trees)

Every widget bundle in this repo is a **committed build artifact**. Production serves the committed
bytes, not a build produced at deploy time. That makes the dependency versions which produced those
bytes part of the shipped artifact, so they must be exact and reviewed — not resolved at install time.

Rules:

1. **Exact versions, no ranges**, for any dependency that lands in a bundle. A caret means the bytes
   that ship can change without any source edit. `widget-react/package.json` for PG-Claude pins
   `@modelcontextprotocol/ext-apps` exactly for this reason.
2. **Commit the lockfile in the same commit** as the bundle it produced.
3. **Build with `npm ci`, never `npm install`.** `npm ci` installs exactly the lockfile. `npm install`
   re-resolves — and it re-resolves *transitively*: upgrading one SDK moved 24 packages in the
   PG-Claude tree, including `@modelcontextprotocol/sdk` 1.27.1 → 1.30.0, because npm re-resolves the
   whole subtree rooted at the changed package, not just that package.
4. **A dependency change is reviewed like a code change.** Diff the lockfile before/after and state
   which packages moved and why.

**Reproducibility is verifiable and was verified.** `npm ci` from the committed lockfile followed by
`npm run build` reproduced the committed PG-Claude bundle byte-for-byte (identical SHA-256), both for
the pre-upgrade bundle and for two independent clean builds of the post-upgrade bundle. If a rebuild
does *not* reproduce the committed hash, the committed bundle and its lockfile have diverged — treat
that as a defect, not as Vite nondeterminism, until proven otherwise.

**Note the type-check gap:** `npm run build` is `vite build` only — it does **not** type-check. Run
`npx tsc --noEmit` explicitly; a type error will otherwise ship.

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

⚠️ **CORRECTED 2026-08-06 — this line read "is currently deprecated". It is not.** The PG Claude MCP
server is **live**: Render reports `srv-d6vbrt9r0fns73c6n080` as `not_suspended`, it answers
`/.well-known/oauth-protected-resource` on `https://mcp.priority-guard.com`, and it is **the app being
submitted** to the Claude MCP Directory — not a service awaiting reactivation afterwards. The same
false deprecation was carried by `doc/testing_baseline_2026-07-04.md`, where it was used to justify
leaving a red test file unexamined across three increments. One wrong belief, two authoritative
documents; correcting only one is the failure this correction exists to prevent.

**Note also: this service does NOT auto-deploy.** `autoDeploy: "no"`, `autoDeployTrigger: "off"` — a
push ships nothing until Manual Deploy is triggered. `priorities-guard-mindsort-claude-mcp`
(`srv-d90din3sq97s7399nbl0`) is the opposite: `autoDeploy: "yes"` on commit. Two Claude MCP services in
one repo with opposite settings is how a smoke test ends up run against stale bytes.

The four steps below remain **outstanding** — the server still ships no logs to Better Stack, which is
its own audit, not this increment's:

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
| `CLARITY_CLAUDE_OAUTH_ISSUER_URL` | `https://www.priority-guard.com/oauth/pg` | path-qualified endpoint base |
| `CLARITY_CLAUDE_OAUTH_ISSUER_BASE` | `https://www.priority-guard.com` | root issuer for `authorization_servers`; **HARD-FAILS localhost in prod** (inc_05b) |
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
