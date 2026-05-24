# Increment 89.5 — Fix WIDGET_URI two-copy split (root cause of Inc 89 cache miss)

**Type:** Bug fix. Structural change. Single-source-of-truth refactor.
**Scope:** PG OpenAI MCP only (`mcp_server/priority_guardian/`). Claude PG MCP is untouched (it lives in `priority_guardian_claude/` and has its own URI scheme).
**Status:** Production widget is currently serving a cached stale bundle from `oaiusercontent.com`. The diagnostic instrumentation from Inc 89 is in the built file on disk but NEVER reaches users because the resource handler returns empty for the advertised URI. This must be fixed before Inc 89 can produce data.

---

## Root Cause

`WIDGET_URI` is defined in **two places**:

1. **`mcp_server/priority_guardian/tools/widget_tools/constants.py`** — defines `WIDGET_URI = "ui://widget/pg-dashboard-v13.html"`. Imported by `tools/get_priorities.py`, `tools/create_priority.py`, `tools/render_weekly_report.py`. This is what the MCP server **advertises** to ChatGPT in tool `_meta.openai/outputTemplate` and resource listings.

2. **`mcp_server/priority_guardian/handlers/resources.py`** line 27 — hardcoded `WIDGET_URI = "ui://widget/pg-dashboard-v12.html"`. This is what the resource handler **responds to** when ChatGPT asks for a widget. The check is literally `if uri_str == WIDGET_URI` against this local copy.

When ChatGPT calls `get_priorities`, it sees `outputTemplate = "ui://widget/pg-dashboard-v13.html"`. It then asks the MCP server for that URI via a `ReadResourceRequest`. The resource handler compares against its hardcoded **v12** copy, the equality check fails, and the handler returns an empty `ReadResourceResult(contents=[])` with a `_meta.error` field. No exception, no obvious failure in logs — just silently no widget HTML returned.

Because ChatGPT got nothing usable from the MCP server, it falls back to whatever it has cached at the `oaiusercontent.com` CDN — a pre-Inc-89 bundle (the last one the MCP server returned successfully, presumably weeks ago). That cached bundle gets served externally via `<script src="https://pg-priority-guard-com.web-sandbox.oaiusercontent.com/assets/main-BGT6Rqhf.js">` instead of being inlined.

This explains every observation from today's debugging session:
- Local `widgets/pg-dashboard.html` is correct v13 (inlined bundle, has build timestamp)
- Production widget iframe loads bundle externally from `/assets/main-BGT6Rqhf.js` with `textContent.length: 0`
- `typeof __WIDGET_BUILD_TIME__` returns `'undefined'` because the running bundle is pre-Inc-89 and doesn't have the Vite-injected constant
- Zero `widget.diagnostic` events in Better Stack — the diagnostic code is in v13 on disk but never runs because v13 is never served
- The `WIDGET_URI` bump from v12 → v13 in Inc 89 made the problem *worse*, not better: before Inc 89, advertised URI matched responded URI (both v12), so the handler served the correct file; Inc 89 broke the match

This is not new to Inc 89. The two-copy split has existed since `widget_tools/constants.py` was created. It happened to work as long as both copies stayed in sync. Inc 89 was the first time they diverged.

---

## Implementation Approach — Single Source of Truth

Make `tools/widget_tools/constants.py` the sole owner of `WIDGET_URI`. Delete the hardcoded constant in `handlers/resources.py`. Import from the canonical location.

This is a deliberate structural fix, not a one-line patch. Hardcoding v13 in `handlers/resources.py` would fix today's symptom but leave the bug class in place — the next URI bump would break again.

---

## Files Touched (3)

1. **`mcp_server/priority_guardian/handlers/resources.py`** — delete the local `WIDGET_URI` constant, import from `tools.widget_tools.constants`.
2. **`mcp_server/priority_guardian/tools/widget_tools/constants.py`** — bump `WIDGET_URI` from v13 to v14 (see "Why v14, not just fix v13" below), update the comment to reflect that it is now the single source of truth.
3. **`doc/OPERATIONS_PREDEPLOY.md`** — add a new section "Widget Bundle Changes" with pre-commit and post-deploy verification steps.

No widget source changes. No backend changes. No new tests required (existing widget unit tests cover the bundle; this fix is a Python-side refactor).

---

## Why v14, Not Just Fix v13

The v13 URI was advertised in production for ~hours today but never successfully served. ChatGPT's CDN cache may have a poisoned association of `ui://widget/pg-dashboard-v13.html` → "empty response" or "use stale fallback." Bumping to v14 forces ChatGPT to treat this as a freshly-discovered resource with no cache history.

If we just fixed v13 in place, we'd be betting that ChatGPT's CDN re-fetches on retry. We don't know its cache invalidation semantics. v14 is one extra character and removes the bet.

---

## Edits

### 1. `mcp_server/priority_guardian/handlers/resources.py`

**Find:**

```python
from mcp_server.priority_guardian.config import BACKEND_URL, MCP_SERVER_URL

logger = structlog.get_logger(__name__)


def _extract_origin(url: str) -> str:
    """
    Extract pure origin (scheme + host) from URL.

    OpenAI Apps SDK requires ui.domain to be a pure origin without path.
    Example: https://pg-mcp.priority-guard.com (not https://pg-mcp.priority-guard.com/mcp)
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


# Widget configuration
WIDGET_VERSION = ""
WIDGET_URI = "ui://widget/pg-dashboard-v12.html"
WIDGET_PATH = Path(__file__).parent.parent.joinpath("widgets/pg-dashboard.html")
```

**Replace with:**

```python
from mcp_server.priority_guardian.config import BACKEND_URL, MCP_SERVER_URL
from mcp_server.priority_guardian.tools.widget_tools.constants import WIDGET_URI

logger = structlog.get_logger(__name__)


def _extract_origin(url: str) -> str:
    """
    Extract pure origin (scheme + host) from URL.

    OpenAI Apps SDK requires ui.domain to be a pure origin without path.
    Example: https://pg-mcp.priority-guard.com (not https://pg-mcp.priority-guard.com/mcp)
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


# Widget configuration
# WIDGET_URI is imported from tools.widget_tools.constants — single source of truth.
# Do NOT redefine it here. If you need a different value, change constants.py.
WIDGET_VERSION = ""
WIDGET_PATH = Path(__file__).parent.parent.joinpath("widgets/pg-dashboard.html")
```

Two changes:
- Add `from mcp_server.priority_guardian.tools.widget_tools.constants import WIDGET_URI` to the import block.
- Delete the line `WIDGET_URI = "ui://widget/pg-dashboard-v12.html"`.
- Add the comment block above WIDGET_VERSION explaining the import.

Nothing else in this file changes. Do NOT refactor `_load_widget_html`, the resource handler, the fallback HTML, or anything else. The bug is solely the duplicate constant.

**Circular import check:** `handlers/resources.py` already imports from `mcp_server.priority_guardian.config`. The `tools.widget_tools.constants` module imports nothing else (it's a one-line file). No circular risk.

### 2. `mcp_server/priority_guardian/tools/widget_tools/constants.py`

**Current contents (3 lines + blank):**

```python
# Single source of truth for the widget URI.
# Must stay in sync with WIDGET_URI in handlers/resources.py.
# Update this value when the widget version bumps.
WIDGET_URI = "ui://widget/pg-dashboard-v13.html"
```

**Replace entire file with:**

```python
# Single source of truth for the widget URI.
#
# Imported by:
#   - mcp_server/priority_guardian/handlers/resources.py (resource read handler)
#   - mcp_server/priority_guardian/tools/get_priorities.py
#   - mcp_server/priority_guardian/tools/create_priority.py
#   - mcp_server/priority_guardian/tools/render_weekly_report.py
#
# When bumping the version: change ONLY this constant.
# Do not redefine WIDGET_URI in any other file. Two copies will drift.
#
# Bump version (v12 → v13 → v14 ...) whenever the widget bundle content changes,
# to force ChatGPT to invalidate its widget cache and fetch the new bundle.
WIDGET_URI = "ui://widget/pg-dashboard-v14.html"
```

The version bump from v13 to v14 is intentional (see "Why v14, not just fix v13" above).

### 3. `doc/OPERATIONS_PREDEPLOY.md`

Add a new section. Insert AFTER the existing `## Schema Change Checklist` section, BEFORE the `## Better Stack Log Shipping` section. (To locate: find the line `## Better Stack Log Shipping` and insert the new section immediately above it, separated by `---` and blank lines.)

**New section to add verbatim:**

```markdown
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
```

---

## Out of Scope

- **No** changes to the widget React source. The v13 bundle on disk is fine — it will be served once the URI mismatch is fixed and the URI is bumped to v14.
- **No** rebuild of the widget bundle. The bundle content is unchanged. The URI bump is metadata only. (If Vite is run anyway, that's harmless — same bundle, same size, just a fresh build timestamp inside.)
- **No** new tests. The bug is a Python-level constant mismatch, not a behavioral defect that tests would catch — tests on the resource handler would have passed against either v12 or v13 in isolation, because the bug is the inconsistency between two files.
- **No** cleanup of the `priority_guardian_claude/` Claude MCP server. It has its own `WIDGET_URI = "ui://pg-claude/dashboard-v1.html"` in its own `resources_dupl.py` file. Different URI scheme, different file, intentionally separate per the `_dupl` pattern. Out of scope here.

---

## Pre-Deploy Checks

**READ `doc/OPERATIONS_PREDEPLOY.md` BEFORE COMMITTING** — the new section you're adding becomes part of this requirement going forward, but for this deploy specifically:

```bash
# Verify single source of truth: exactly ONE WIDGET_URI = "..." in the PG codebase
grep -rn 'WIDGET_URI = "' "mcp_server/priority_guardian/" --include="*.py" | grep -v __pycache__
# Expected output: exactly one line, from tools/widget_tools/constants.py.

# Verify the new value is v14
grep "WIDGET_URI" mcp_server/priority_guardian/tools/widget_tools/constants.py
# Should show: WIDGET_URI = "ui://widget/pg-dashboard-v14.html"

# Verify imports resolve (no circular import, no missing module)
python -c "from mcp_server.priority_guardian.handlers.resources import WIDGET_URI; print(WIDGET_URI)"
# Should print: ui://widget/pg-dashboard-v14.html

# Confirm the widget HTML file still exists and is current (no rebuild needed)
ls -la mcp_server/priority_guardian/widgets/pg-dashboard.html
# Same file from Inc 89 (~357KB, built 2026-05-24 morning)
```

---

## Post-Deploy Verification

After Render deploys and the PG MCP server restarts:

1. **Cache-bust dance** (all three are required):
   - Confirm MCP server restarted (Render dashboard → PG MCP service → last deploy time matches)
   - ChatGPT app → Settings → Apps → Priority Guardian → click **Refresh**
   - Start a **brand new conversation** (don't refresh an existing one)

2. **Verify in production iframe console:**

   ```javascript
   document.querySelectorAll('script').length
   // Must return 1

   document.querySelector('script').textContent.length
   // Must return ~340000+ (the inlined bundle, not 0)

   document.documentElement.innerHTML.includes('2026-05-24T09:42:59')
   // Must return true — confirms the v13-built bundle (the one with diagnostic
   // instrumentation) is now being served. The build timestamp is embedded
   // inside the bundle by Vite's `define` block.
   ```

3. **Check Render PG MCP logs** for the resource read flow:

   ```
   {"event": "resource.read.requested", "uri": "ui://widget/pg-dashboard-v14.html", ...}
   {"event": "resource.read.serving_widget", "uri": "ui://widget/pg-dashboard-v14.html", "html_length": 356980, ...}
   ```

   Both events must appear, with matching v14 URIs. If `serving_widget` is missing, the resource handler is still rejecting the URI — investigate the import.

4. **Run the Inc 89 diagnostic repro** (the original reason Inc 89 exists):
   - Click "Open full dashboard"
   - Wait 30 seconds
   - Check Better Stack for `event:"widget.diagnostic"` entries from the past 60 seconds
   - At minimum a `mount` event must appear; the `set_globals` and `displayMode.change` events follow depending on what the host emits

If step 4 produces diagnostic events, Inc 89 is finally functional and we can analyze the fullscreen flash-revert bug. If step 4 still produces zero events but steps 1-3 pass, the diagnostic itself has a bug — but that's a different investigation.

---

## Risk Assessment

- **Low risk.** Single-file Python refactor, no behavior change beyond fixing a constant lookup. The new behavior (resource handler returns the widget HTML) is what the system was always supposed to do — Inc 89 just exposed that it was broken.
- **No data migration, no schema change, no API contract change.**
- **Rollback:** if anything breaks, revert the commit; v13 was already broken so reverting only restores the prior broken state (cached widget being served). Either way the widget renders something, just whether it's stale or fresh.

---

## Effort Estimate

- 3 file edits, < 30 lines net change (most of it is the new OPERATIONS section)
- One Render deploy
- One post-deploy verification cycle
- Total: ~20 minutes of Claude Code work, ~5 minutes of Nadja's verification

---

## What This Increment Decides

That `WIDGET_URI` lives in exactly one place going forward. That the OPERATIONS_PREDEPLOY checklist includes widget bundle validation. That the Inc 89 diagnostic instrumentation can actually produce data.

**What it does NOT decide:**
- The root cause of the fullscreen flash-revert bug — that's Inc 89's job, blocked until this ships
- Whether to clean up the `_dupl` Claude MCP codebase — separate decision, out of scope
- The KaTeX CSP font violations in the widget — known issue, separate increment

---

## Reminder Per Project Rules

When Claude Code finishes implementing, do NOT commit until Nadja runs the four pre-deploy verification commands above and confirms output. The pre-deploy section was added in this very increment because skipping verification is exactly how Inc 89 deployed broken.