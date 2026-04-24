Claude Code Briefing: Switch Render Build to Poetry — Suite-Wide
Context
Scope clarification: The priority-guardian repo hosts the entire Priority Guard Suite shared backend, not just Priority Guardian. Any change to build configuration affects every service deployed from this repo.
Services deploying from this repo (verified via codebase):
Service typeSourceEntry pointBackend API + workersbackend/FastAPI + Celery worker + Celery beatPG OpenAI MCPmcp_server/priority_guardian/server.pyuvicorn ...server:appPG Claude MCPmcp_server/priority_guardian_claude/server_dupl.pyuvicorn ...server_dupl:create_app --factoryMindSort MCPmcp_server/clarity/server.pyuvicorn ...server:appFocused MCPmcp_server/focused/(may be deprecated — verify in dashboard)Sharpen MCPmcp_server/sharpen/(paused — verify in dashboard)
All services share:

One pyproject.toml
One poetry.lock
One requirements_fullbackend.txt
Currently, all build via pip install -r requirements_fullbackend.txt (some docs reference other filenames — those docs are stale; verify in Render dashboard)

Services differ in: Start Command (each service runs its own entry point). Not changed by this increment.
Dependency split-brain verified:

Local dev: Poetry (pyproject.toml + poetry.lock, both Poetry 2.2.0)
Production: stale poetry export from Dec 7, 2025
Result: silent dependency drift since Jan 12, 2026

Codebase audit findings:

DATABASE_URL=postgresql+asyncpg://... → runtime uses asyncpg.
backend/alembic/env.py uses async_engine_from_config → Alembic also uses asyncpg.
Zero imports of psycopg / psycopg2 anywhere in source.
Zero imports of pysonar anywhere in source.
psycopg2-binary only exists in requirements_fullbackend.txt — dead weight.

Python runtime: 3.13.7 pinned in .python-version (Increment 80, complete).
Goal
Make pyproject.toml + poetry.lock the single source of truth for production dependencies across all services deployed from this repo. Split into two commits with a 48-hour stability gate covering all active services.
Implementation Approach — Copy and Adjust, Never Rewrite
Three atomic file changes in Commit 1. One file deletion + one doc update in Commit 2. Do not rewrite, restructure, or refactor anything else.

Pre-Work (Human Executes Before Claude Code Starts)
Pre-Work 1: Remove pysonar from pyproject.toml
Delete from [tool.poetry.dependencies]:
tomlpysonar = "^1.3.0.4086"
Regenerate lock:
bashcd "/Users/nadja/Desktop/Priority Guard Suite/priority-guardian"
poetry lock
Commit as its own change:
bashgit add pyproject.toml poetry.lock
git commit -m "chore: remove unused pysonar dependency"
Pre-Work 2: Enumerate and audit all affected Render services
This is the critical step — skipping any service leaves a split dependency state that's worse than the current one.
Open Render Dashboard. For every service in your Render workspace that connects to this git repo, record in a local scratchpad:
ColumnWhat to captureService namee.g. priority-guardian, priorities-guard-pg-mcp, priorities-guard-clarity-mcpCurrent Build CommandVerbatim from dashboardCurrent Start CommandVerbatim from dashboardCurrently active?Yes / suspended / deprecatedPOETRY_VERSION env var set?Yes / No
Expected findings:

All services should have Build Command = pip install -r requirements_fullbackend.txt (or similar pip install ... referencing a requirements file).
Flag any service with a different Build Command — it means my scope assumption is wrong for that service and the briefing needs adjustment before proceeding.
POETRY_VERSION should not be set on any service. If it is, delete it (we'll add 2.2.0 consistently at deploy time).

Pre-Work 3: Decide which services are in-scope

In-scope for switch: All active services (backend + currently-used MCP servers).
Deprecated services (Focused, possibly Sharpen): decide whether to include or suspend them on Render. Recommendation: include them in the switch if they still auto-deploy on git push — otherwise the next commit will crash their build. If they're suspended in Render, skip them.

Do not proceed until the full service list is documented.

═══════════════════════════════════════════════════
COMMIT 1 — Switch to Poetry, Keep Fallback File
═══════════════════════════════════════════════════
Changes Claude Code Will Make
Change 1: Remove poetry.lock from .gitignore
File: /Users/nadja/Desktop/Priority Guard Suite/priority-guardian/.gitignore
Find the # Poetry section:
# Poetry
poetry.lock
Delete only the poetry.lock line. Keep the # Poetry comment header.
Change 2: Add Poetry workflow section to OPERATIONS_PREDEPLOY.md
File: /Users/nadja/Desktop/Priority Guard Suite/priority-guardian/doc/OPERATIONS_PREDEPLOY.md
Insert at the end of the "Local Pre-Deploy Checks" section, immediately before --- and ## Deploy Reminder:
markdown### Poetry Lock File Consistency

After any change to `pyproject.toml`, regenerate `poetry.lock` and commit both files together:

\`\`\`bash
poetry lock
git add pyproject.toml poetry.lock
git commit -m "deps: <what changed>"
\`\`\`

**Suite-wide impact:** All Render services deployed from this repo (backend, PG OpenAI MCP, PG Claude MCP, MindSort MCP, and any other MCP services) share this `pyproject.toml` + `poetry.lock`. A dependency change affects every service.

Render installs production dependencies via `poetry install --no-root --only main` (set as Build Command on every service). If `poetry.lock` is out of sync with `pyproject.toml`, Render builds will fail with a lock-file-stale error. This is intentional — it prevents silent dependency drift between local and production.

`requirements_fullbackend.txt` was retained temporarily during the Poetry migration as a rollback fallback. It will be removed once Poetry-based deploys have proven stable.
Change 3: Keep requirements_fullbackend.txt untouched
Do not delete requirements_fullbackend.txt in this commit. It stays as rollback fallback for every service. Deletion happens in Commit 2 after 48h of stable deploys across all services.
Commit 1 Message
chore: switch Render build from pip to poetry (single source of truth)

Affects all Render services deployed from this repo:
- Backend API + Celery worker + Celery beat
- PG OpenAI MCP, PG Claude MCP, MindSort MCP, and any others

- Commit poetry.lock (removed from .gitignore)
- Document poetry workflow in OPERATIONS_PREDEPLOY.md

Build Command on every Render service must be updated to:
  poetry install --no-root --only main

Env var POETRY_VERSION=2.2.0 must be set on every service.

requirements_fullbackend.txt retained as rollback fallback; will be
removed in a follow-up commit once Poetry deploys prove stable across
all services.
Pre-Deploy Dry Run (Human Executes, Before Pushing Commit 1)
Mandatory. Do not skip.

Scratch-install simulating Render:

bash   cd /tmp
   python3.13 -m venv render-sim
   source render-sim/bin/activate
   pip install poetry==2.2.0
   cd "/Users/nadja/Desktop/Priority Guard Suite/priority-guardian"
   poetry install --no-root --only main

Expected: install completes cleanly.
Diff against current prod:

bash   pip freeze | sort > /tmp/new-deps.txt
   sed 's/ ;.*//' requirements_fullbackend.txt | sort > /tmp/old-deps.txt
   diff /tmp/old-deps.txt /tmp/new-deps.txt
Expected: psycopg2-binary disappears; pysonar + transitives absent; minor/patch bumps on transitives.
Unexpected — STOP and flag: Any major-version jump (first digit) on any dep.

Smoke test:

bash   poetry run uvicorn backend.main:app --port 8001
http://localhost:8001/health → 200. Ctrl-C.

Also smoke test one MCP service locally (pick any active one, e.g. PG OpenAI):

bash   PORT=8003 poetry run uvicorn mcp_server.priority_guardian.server:app --port 8003
http://localhost:8003/health → 200. Ctrl-C.
This proves the MCP services boot correctly under the new Poetry install, not just the backend.
Only proceed past this gate if all five steps pass.
Deploy Verification (Commit 1) — Multi-Service
Before deploying: read OPERATIONS_PREDEPLOY.md for the standard pre-deploy checklist (Alembic head check, OAuth discovery sanity check, env var verification).
Deploy sequence (order matters):

Push Commit 1 to git.
For EACH Render service in your Pre-Work service list, in quick succession:

Environment tab → Add POETRY_VERSION = 2.2.0.
Settings tab → Build Command → change to poetry install --no-root --only main.
Save.
Leave Start Command unchanged — each service has its own, unrelated to this switch.


Recommended order for triggering deploys (safest first):

Backend service (priority-guardian) — deploy first, verify.
PG OpenAI MCP — deploy next, verify.
PG Claude MCP — deploy next, verify.
MindSort MCP — deploy next, verify.
Any remaining active MCP services.

Deploying one service at a time (rather than all at once) lets you catch a misconfiguration on the first service before it propagates.
Per-service verification (run after each deploy):
For the backend service:

Build log: expect Installing dependencies from lock file messages; no pip install -r requirements_fullbackend.txt.
/health → 200 on https://www.priority-guard.com/health (or wherever backend is hosted).
OAuth discovery: curl https://www.priority-guard.com/.well-known/oauth-authorization-server → valid JSON.

For each MCP service:

Build log: same expectations.
/health on that service's URL → 200.
OAuth protected resource discovery: curl https://<mcp-host>/.well-known/oauth-protected-resource → valid JSON.


If any service's deploy fails:

Revert that service's Build Command in Render dashboard to the previous pip install ... command.
Trigger redeploy on that service — it will use requirements_fullbackend.txt (still in repo) and recover.
Leave the other services' Build Commands as-is if they've already been flipped and are stable.
git revert <commit1> + push only if you need to roll back the git-tracked changes too.
Investigate before proceeding.




═══════════════════════════════════════════════════
🛑 STOP HERE 🛑

DO NOT PROCEED TO COMMIT 2 UNTIL:

✅ Every service's Commit 1 deploy succeeded
✅ Every service's /health returns 200
✅ Every service's OAuth discovery returns valid JSON
✅ 48 hours have elapsed with no incidents on any service
✅ Backend Celery beat has run at least one scheduled task
(check logs for successful OAuth cleanup or retention job)
✅ At least one real end-to-end flow on PG (OpenAI or Claude)
has completed: auth → tool call → result
✅ At least one real end-to-end flow on MindSort has completed
✅ At least one Google token refresh has occurred in prod
(check backend logs for token.refresh.success)

This 48h gate exists because dependency issues often don't
surface at boot — they surface when a specific code path runs
for the first time under prod load. Each MCP service has its
own handlers, its own OAuth flow, its own widget-rendering.
All of them need live exercise before you remove the fallback.

If ANY of the above fails during the gate: investigate that
service; do not proceed until resolved.
═══════════════════════════════════════════════════

═══════════════════════════════════════════════════
COMMIT 2 — Remove Fallback File (After 48h Stability)
═══════════════════════════════════════════════════
Changes Claude Code Will Make
Change 1: Delete requirements_fullbackend.txt
git rm requirements_fullbackend.txt
Change 2: Update the OPERATIONS_PREDEPLOY.md note
File: /Users/nadja/Desktop/Priority Guard Suite/priority-guardian/doc/OPERATIONS_PREDEPLOY.md
In the "Poetry Lock File Consistency" subsection added in Commit 1, replace:
`requirements_fullbackend.txt` was retained temporarily during the Poetry migration as a rollback fallback. It will be removed once Poetry-based deploys have proven stable.
with:
`requirements_fullbackend.txt` was removed in Increment 81 Commit 2. Do not reintroduce it — `pyproject.toml` + `poetry.lock` are the single source of truth for every service deployed from this repo.
Change 3: Fix stale deployment doc (opportunistic cleanup)
File: /Users/nadja/Desktop/Priority Guard Suite/priority-guardian/mcp_server/clarity/DEPLOYMENT.md
This doc currently says Build Command: pip install -r requirements.txt — wrong filename, and now outdated anyway. Replace that line with:
markdown- **Build Command:** `poetry install --no-root --only main` (env var `POETRY_VERSION=2.2.0` required)
Flag to human: Check if other DEPLOYMENT.md or ENV_TEMPLATE.md files under mcp_server/*/ have similar stale Build Command references. If yes, they should be updated too — but that's an optional cleanup, not required for this increment to succeed.
Commit 2 Message
chore: remove requirements_fullbackend.txt; poetry is sole source of truth

Poetry-based deploys have been stable for 48h+ across all services
(backend, PG OpenAI MCP, PG Claude MCP, MindSort MCP). The fallback
file is no longer needed and keeping it risks reintroducing drift.

pyproject.toml + poetry.lock are the canonical dependency declaration
for every service deployed from this repo.

Also updates mcp_server/clarity/DEPLOYMENT.md with current Build Command.
Deploy Verification (Commit 2) — Multi-Service
Trivial — this commit only removes a file Render no longer reads.

Push Commit 2.
Trigger manual deploy on every service (in same order as Commit 1).
For each service: build logs should show no change vs Commit 1; /health → 200.
Done.


Out of Scope — Do Not Touch

pyproject.toml (pysonar removal happened in Pre-Work as a separate commit)
poetry.lock (regenerated during Pre-Work; committed via Commit 1's .gitignore change)
.python-version (locked in Increment 80, stays 3.13.7)
Each service's Start Command (unchanged)
Actual Python source code under backend/, mcp_server/, tests/
CI configuration
Alembic, migrations, environment variables (other than POETRY_VERSION per service)

Flag to Human

Render changes are manual and per-service. Claude Code cannot do them. Every active service needs Build Command + POETRY_VERSION updated in the Render dashboard.
Service enumeration in Pre-Work 2 is the most important step. Missing a service = a broken build on the next git push for that service. Don't skip or rush it.
Deploy services in sequence, not simultaneously. Lets you catch a problem on the first service before it propagates.
48h gate covers every service, not just the backend. All flows must be exercised.
Stale docs exist. mcp_server/clarity/DEPLOYMENT.md already identified; others may exist. Commit 2 addresses MindSort; others are optional follow-up.
