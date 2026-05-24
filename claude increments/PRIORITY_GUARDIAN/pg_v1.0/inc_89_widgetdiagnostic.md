# Increment 89 — Diagnostic: Fullscreen flash-revert on production

**Type:** Instrumentation only — NO behavior changes.
**Goal:** Capture a real production repro so we can identify what reverts `displayMode` after the user clicks "Open full dashboard".
**Status:** Investigation. No fix yet — see "Implementation Approach" below.

---

## Problem Statement

On production (May 24, 2026) "Open full dashboard" is broken for users on desktop ChatGPT web:

- User clicks `ExpandButton` ("Open full dashboard")
- Widget enters fullscreen for ~500ms (visible flash)
- Widget reverts to inline mode without user action
- Sometimes (rarely) it stays in fullscreen — but with broken layout (separate issue, not in scope here)
- Reproduces across multiple Macs and multiple ChatGPT accounts in fresh chats
- Last `pg-dashboard.html` build is from **April 26, 2026 (28 days ago)** — the widget bundle has not changed
- Last commit touching `App.tsx` was Inc 73 in April; nothing widget-side has been deployed since

**Reported by:** Nadja, today. Worked reliably "a few days ago" per user statement.

**What we do NOT know yet** (and what this increment is designed to find out):

1. Whether ChatGPT host emits `openai:set_globals` with `displayMode === 'inline'` shortly after our optimistic `setDisplayMode('fullscreen')`, causing the `handleSetGlobals` sync to clobber local state back to inline
2. Whether some other code path inside the widget calls `setDisplayMode('inline')` (e.g. a stale effect, a remount, an unexpected handler firing)
3. Whether the widget remounts entirely and re-reads `window.openai.displayMode === 'inline'` from the host on initial state setup
4. Whether the host quota errors observed in the console (`QuotaExceededError` on host localStorage, 401/404 on `/backend-api/sentinel/ping` and `/backend-api/codex/surface_usage`) are correlated with the revert or unrelated noise

We will NOT propose a fix in this increment. Per `PG_context.md` and project rules: never fix until 100% sure of cause. We instrument first.

---

## Implementation Approach — Copy and Adjust, Never Rewrite

This is a diagnostic-only increment. Make ONLY the specific edits listed below to existing files. Do NOT refactor, restructure, simplify, improve naming, change formatting, or touch anything not explicitly listed. The widget bundle has been stable in production for 28 days — any unrelated change introduces confounding variables.

If something looks "off" in surrounding code, leave it alone. If a TypeScript error appears that requires a non-listed change to resolve, stop and ask.

**Reference precedent:** `ios_bug.md` — Increment 58-debug used the same pattern: temporary `PG_DEBUG` flag, in-widget capture, post-mortem, then a separate increment for the fix and another to remove the debug code.

---

## Files Touched (3)

1. `mcp_server/priority_guardian/widget-react/src/App.tsx` — add diagnostic logging points
2. `mcp_server/priority_guardian/widget-react/src/widgetErrorReporter.ts` — add a sibling function `reportWidgetDiagnostic`
3. `backend/apps/priority_guardian/routers/widget_diagnostic.py` — NEW backend endpoint to receive diagnostic events

---

## Why backend endpoint and not just `console.log`

Console logs require Chrome DevTools open and the user being able to capture them. The user has already tried this and could not switch reliably to the iframe context. Per `ios_bug.md` learning #3: in-widget logs that ship to a backend endpoint are the only practical debugging tool for sandboxed widgets. Inc 83 already wired this pattern for errors. We extend it for diagnostics.

Diagnostic data goes to Better Stack via existing log shipping (Inc 84/85). It will appear alongside widget errors and can be queried after Nadja reproduces the bug once.

---

## Build-time constant for verifiable widget build date

ChatGPT's review correctly flagged that a hardcoded build-date string is self-attestation that proves nothing. We use Vite's `define` to inject the actual build timestamp.

**In `mcp_server/priority_guardian/widget-react/vite.config.ts`:** locate the existing `defineConfig({ ... })` block and add (or extend) a `define` field:

```ts
define: {
  __WIDGET_BUILD_TIME__: JSON.stringify(new Date().toISOString()),
},
```

If a `define` block already exists, add this entry to it. Do not replace existing entries.

**In `mcp_server/priority_guardian/widget-react/src/vite-env.d.ts`:** append the type declaration:

```ts
declare const __WIDGET_BUILD_TIME__: string
```

`App.tsx` will use `__WIDGET_BUILD_TIME__` directly (see the mount effect under Edits §2). This makes the build date verifiable — it reflects the actual moment Vite produced the bundle.

---

## Edits

### 1. `widgetErrorReporter.ts`

**Goal:** Add a `reportWidgetDiagnostic` function — same fire-and-forget shape as `reportWidgetError`, separate endpoint, separate per-session cap, no dedup.

**Add** (after the existing `reportWidgetError` function, before `__resetReporterStateForTesting`):

```ts
// ============ Diagnostic Reporter (Inc 89) ============
// Temporary — remove after fullscreen flash-revert bug is diagnosed.

const WIDGET_DIAGNOSTIC_ENDPOINT =
  'https://priorities-guard-sdkapp-suite.onrender.com/api/priority-guardian/widget-diagnostic'

const MAX_DIAGNOSTIC_EVENTS_PER_SESSION = 20
let diagnosticCount = 0

export interface WidgetDiagnosticPayload {
  event: string
  data?: Record<string, unknown>
}

export async function reportWidgetDiagnostic(payload: WidgetDiagnosticPayload): Promise<void> {
  try {
    if (diagnosticCount >= MAX_DIAGNOSTIC_EVENTS_PER_SESSION) return
    diagnosticCount++

    const body = {
      event: payload.event,
      data: payload.data ?? {},
      ts: Date.now(),
      ua: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
    }

    await fetch(WIDGET_DIAGNOSTIC_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      keepalive: true,
    })
  } catch {
    // Silent failure
  }
}
```

Also update `__resetReporterStateForTesting`:

```ts
export function __resetReporterStateForTesting(): void {
  errorCount = 0
  seenErrors.clear()
  diagnosticCount = 0  // Inc 89
}
```

### 2. `App.tsx`

**Goal:** Capture every event that could change `displayMode`, and every set_globals event, with enough context to identify the culprit.

**Add at the top of App.tsx**, after the existing imports:

```ts
import { reportWidgetDiagnostic } from './widgetErrorReporter'

// Inc 89: temporary diagnostic flag. Set to false before next non-diagnostic deploy.
const PG_DIAG_FULLSCREEN = true
```

**Add a session correlation id** so backend can group events from a single repro. Right after the existing refs near the top of `App()`:

```ts
// Inc 89: session-scoped diagnostic id
const diagSessionIdRef = useRef<string>(
  `pg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
)
```

**Wrap every call to `setDisplayMode`** in a helper. Above the existing `useState<DisplayMode>(...)` line, add:

```ts
// Inc 89: helper to log every displayMode change with caller marker
const logDisplayModeChange = (next: DisplayMode | 'sync', caller: string, extra?: Record<string, unknown>) => {
  if (!PG_DIAG_FULLSCREEN) return
  reportWidgetDiagnostic({
    event: 'displayMode.change',
    data: {
      sid: diagSessionIdRef.current,
      next,
      caller,
      hostMode: (window.openai as { displayMode?: string } | undefined)?.displayMode,
      ts: performance.now(),
      ...extra,
    },
  })
}
```

Note: place this declaration where `diagSessionIdRef` is in scope. Put it immediately after `diagSessionIdRef` is declared. Do not move `diagSessionIdRef` — adjust this helper's position to be after the ref.

**Modify the four `setDisplayMode` call sites** to also call the logger. Locate each by exact text. Each is a one-line addition before the existing `setDisplayMode(...)` line.

**Call site 1** — inside `handleExpandToFullscreen`:

Find:
```ts
    }
    setDisplayMode('fullscreen')
    notifyHeight()
  }, [isMobile, notifyHeight])
```

Replace with:
```ts
    }
    logDisplayModeChange('fullscreen', 'handleExpandToFullscreen', { isMobile })
    setDisplayMode('fullscreen')
    notifyHeight()
  }, [isMobile, notifyHeight])
```

**Call site 2** — inside `handleMinimizeToInline`:

Find:
```ts
    }
    setDisplayMode('inline')
    notifyHeight()
  }, [isMobile, notifyHeight])
```

Replace with:
```ts
    }
    logDisplayModeChange('inline', 'handleMinimizeToInline', { isMobile })
    setDisplayMode('inline')
    notifyHeight()
  }, [isMobile, notifyHeight])
```

**Call site 3** — inside `handleSetGlobals`, the host-sync path:

Find:
```ts
      // Sync displayMode from host (only after init to avoid layout flicker)
      if (isInitializedRef.current) {
        const hostMode = (window.openai as OpenAIHost | undefined)?.displayMode
        if (hostMode === 'fullscreen' || hostMode === 'inline') {
          setDisplayMode(prev => prev !== hostMode ? hostMode : prev)
        }
      }
```

Replace with:
```ts
      // Sync displayMode from host (only after init to avoid layout flicker)
      if (isInitializedRef.current) {
        const hostMode = (window.openai as OpenAIHost | undefined)?.displayMode
        // Inc 89: log every set_globals event with host displayMode, regardless of whether we sync
        if (PG_DIAG_FULLSCREEN) {
          reportWidgetDiagnostic({
            event: 'set_globals',
            data: {
              sid: diagSessionIdRef.current,
              hostMode,
              ts: performance.now(),
            },
          })
        }
        if (hostMode === 'fullscreen' || hostMode === 'inline') {
          // Inc 89: log the sync intent before it fires
          logDisplayModeChange('sync', 'handleSetGlobals.hostSync', { hostMode })
          setDisplayMode(prev => prev !== hostMode ? hostMode : prev)
        }
      }
```

**Call site 4** — the `useState` initializer (initial mount). This is intentionally NOT wrapped, because logging from inside `useState`'s lazy initializer is awkward and runs only once. Instead, log it in an effect that fires immediately on mount.

**Add a new effect** right after the existing `// Set document language for VoiceOver on mount (Inc 62)` effect:

```ts
  // Inc 89: log initial displayMode at mount
  useEffect(() => {
    if (!PG_DIAG_FULLSCREEN) return
    reportWidgetDiagnostic({
      event: 'mount',
      data: {
        sid: diagSessionIdRef.current,
        initialDisplayMode: displayMode,
        hostMode: (window.openai as { displayMode?: string } | undefined)?.displayMode,
        availableDisplayModes: (window.openai as { availableDisplayModes?: unknown } | undefined)?.availableDisplayModes,
        hasRequestDisplayMode: typeof (window.openai as { requestDisplayMode?: unknown } | undefined)?.requestDisplayMode === 'function',
        widgetBuildTime: __WIDGET_BUILD_TIME__,  // injected by Vite — actual build moment
      },
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
```

`displayMode` in the dependency array is intentionally omitted — we only want this on mount, not on every displayMode change. The lint disable comment is required.

**Important:** Do NOT change `handleExpandToFullscreen`'s desktop-vs-mobile logic. Do NOT add a `requestDisplayMode` call on desktop. We are diagnosing, not fixing. The current behavior is: desktop does not call `requestDisplayMode`, mobile does. Keep that.

### 3. `backend/apps/priority_guardian/routers/widget_diagnostic.py` (NEW)

**Goal:** Receive diagnostic events, log them via structlog at INFO level so they ship to Better Stack.

**Non-negotiable pre-step:** Before writing this file, read both:
1. `claude increments/PRIORITY_GUARDIAN/pg_v1.0/inc_83_widgeterrors.md` (the briefing that created the existing widget-error endpoint)
2. The actual existing `widget-error` router file in `backend/apps/priority_guardian/routers/` (find it by name)

The new file must mirror the existing widget-error router file structurally — same imports, same router decorator pattern, same auth posture (none — public endpoint), same rate-limit dependency, same structlog setup, same response shape (204 No Content on success), same registration call site in the main app, same CORS / preflight behavior.

When done, diff the two files side-by-side mentally: the only legitimate differences should be (a) the URL path, (b) the Pydantic model fields, (c) the structlog event name, (d) the data-size validation logic described below. If anything else differs, you have deviated — go back and align.

**Pydantic model:**

```python
event: str (required, min_length=1, max_length=100)
data: dict[str, Any] | None (optional)
ts: int | None (optional, client-provided timestamp)
ua: str | None (optional, max_length=500)
```

**Data-size enforcement (REQUIRED, not optional):**

Pydantic does not enforce serialized JSON byte size on a `dict` field out of the box. Enforce explicitly inside the route handler before logging:

```python
if payload.data is not None:
    serialized = json.dumps(payload.data, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > 2048:
        # Reject — do not silently truncate; we want to know if the widget
        # is shipping oversized payloads so we can fix the source.
        raise HTTPException(
            status_code=413,
            detail="diagnostic data field exceeds 2048 bytes",
        )
```

Use `413 Payload Too Large` (not 422) — the field is structurally valid, just too big. This matches HTTP semantics. Reject rather than truncate because:
1. Silent truncation hides bugs in the widget that would produce oversized payloads
2. We're in diagnostic mode — we want loud failures, not silent data loss
3. Inc 83's `truncate()` policy was for known-large fields (stack traces). This is different — `data` is structured and bounded by design.

**Handler logging:**

Log at INFO level via structlog with event name `widget.diagnostic`. Include all payload fields plus `ip_hash` (exact same pattern as Inc 83 — copy it, do not reinvent) and `service: "priority-guardian"` so the Better Stack filter picks it up.

**Rate limit:** Use the same dependency / decorator that the widget-error endpoint uses. Same number. Do not invent a new rate-limit value.

**Router registration:** Register in the same main app file where widget-error is registered, immediately adjacent to it.

**CORS / preflight:** Whatever CORS middleware or per-route config the widget-error endpoint uses, this endpoint inherits identically. If widget-error works for the widget today, this one must work the same way. Do NOT add CORS config that diverges. If you find yourself reasoning about CORS specifics, you are diverging — go back and copy the working endpoint's configuration verbatim.

**Do NOT** add database persistence, queue routing, or any other infrastructure. Logs only. Better Stack handles the rest.

---

## Out of Scope (explicit)

- **No** fix for the bug. We do not know the cause yet.
- **No** changes to the host-sync logic in `handleSetGlobals` beyond adding logging.
- **No** changes to `handleExpandToFullscreen` beyond adding logging.
- **No** removal of the desktop CSS-only fullscreen approach.
- **No** changes to the `max-w-2xl` constraint or any layout code.
- **No** changes to bundled KaTeX CSS (separate known issue, also out of scope).
- **No** UI changes visible to users.

---

## Unit Tests

Required:

1. `widgetErrorReporter.test.ts` — extend to cover `reportWidgetDiagnostic`:
   - Calls fetch with the diagnostic endpoint URL
   - Respects `MAX_DIAGNOSTIC_EVENTS_PER_SESSION` cap (21st call does nothing)
   - Does NOT dedup (calling with same event twice triggers fetch twice)
   - Silent on fetch failure (no throw)
   - `__resetReporterStateForTesting` resets `diagnosticCount`

2. Backend endpoint tests (mirror the existing widget-error endpoint test from Inc 83):
   - POST with valid payload returns 204
   - POST with `data` field that serializes to > 2048 bytes returns **413 Payload Too Large** (not 422, not truncated — explicit rejection per the new policy)
   - POST with `data` field that serializes to exactly 2048 bytes succeeds (boundary)
   - POST with missing `event` field returns 422
   - POST with `event` field longer than 100 chars returns 422
   - Rate limit fires after the limit is exceeded (use same fixture as Inc 83's rate-limit test)
   - CORS preflight (OPTIONS) returns the same headers as the widget-error endpoint's preflight

No new App.tsx tests required for this increment — the logging is pure side-effect and behavior is unchanged. Existing tests must still pass.

---

## Integration Tests

None required for this increment. The endpoint is fire-and-forget, no DB writes, no downstream dependencies.

---

## Pre-deploy Checklist

**READ `doc/OPERATIONS_PREDEPLOY.md` BEFORE COMMITTING.** Per project rules.

Confirm:
- `widget-react/` build succeeds (`npm run build` in `mcp_server/priority_guardian/widget-react/`)
- `pg-dashboard.html` is regenerated and committed (per project memory: tracked by git, output of viteSingleFile)
- Backend tests pass
- Widget tests pass
- `PG_DIAG_FULLSCREEN = true` in shipped bundle (set false later in cleanup increment)
- The new endpoint is registered in `backend` main app router list
- WIDGET_URI is bumped if necessary for cache busting (check Inc 47 / 48 / cache-bust pattern — if the bundle changes, the URI must bump)

---

## Post-Deploy: How to Use the Diagnostic

This is for Nadja, not for Claude Code:

1. After deploy reaches production, open ChatGPT desktop web in any chat where PG is connected.
2. Trigger Priority Guardian. Wait for the widget to render in inline mode.
3. Click "Open full dashboard".
4. Wait 5 seconds. Then check Better Stack for events with `event: "widget.diagnostic"` from the last 60 seconds.
5. Group by `sid` (session id) — one click produces one session's worth of events.
6. Expected event ordering for a HEALTHY click (hypothesis to verify):
   - `mount` (initial)
   - any number of `set_globals` events with `hostMode: inline` (during initial render)
   - `displayMode.change` with `caller: handleExpandToFullscreen`, `next: fullscreen`
   - (desktop only) NO further changes — stays fullscreen
7. Expected event ordering for the BUGGY click (alternative hypotheses):
   - **H1 (host-sync clobber):** `displayMode.change` `handleExpandToFullscreen` fullscreen → `set_globals` `hostMode: inline` → `displayMode.change` `handleSetGlobals.hostSync` sync inline → BUG CONFIRMED, host syncs back to inline
   - **H2 (remount):** A new `sid` appears mid-click. Widget remounted, lost local state, re-read inline from host
   - **H3 (other handler):** `displayMode.change` with `caller: handleMinimizeToInline` appears unexpectedly → trace why that handler fired
   - **H4 (no second event):** Only one `displayMode.change` event logged but the UI still reverts → CSS / layout-level problem, not state. Different investigation entirely.

Send Claude the Better Stack output for one repro, grouped by `sid`. The branch we take next depends on which hypothesis the data supports.

---

## Cleanup (Future Increment 89-cleanup, after diagnosis)

Once the bug is diagnosed and fixed:
- Set `PG_DIAG_FULLSCREEN = false`
- Remove `logDisplayModeChange` helper and all its call sites
- Remove the `mount` effect added in this increment
- Remove `reportWidgetDiagnostic` and `WIDGET_DIAGNOSTIC_ENDPOINT` from `widgetErrorReporter.ts`
- Remove the backend `widget-diagnostic` endpoint
- Bump widget URI for cache bust

Mirror exactly what Inc 58-debug → Inc 59 → Inc 59-cleanup did.

---

## Estimated Effort

- App.tsx: 6 edits, ~30 lines added
- widgetErrorReporter.ts: 1 new function, ~30 lines added
- backend router: 1 new file, ~40 lines (mirror Inc 83)
- Tests: extend existing test files, ~40 lines
- Total: ~140 lines, all additive
- No refactoring, no behavior changes

---

## What This Increment Does NOT Decide

- Whether the bug is host-side or our side. That's the whole point of running the diagnostic.
- Whether other open issues (KaTeX CSP violations, max-w-2xl fullscreen layout, composer overlap) get addressed. Out of scope.
- Whether to escalate to OpenAI. We will decide that after seeing the diagnostic data — if H1 confirms host-sync clobber with a verifiably bad host-emitted state, we file with OpenAI with hard evidence. If H2/H3/H4, we fix on our side.
