# Increment: Wire Priority Guardian Widget to Existing widget-error Endpoint

## Context

The backend endpoint `POST /api/priority-guardian/widget-error` already exists
(`backend/apps/priority_guardian/routers/health_router.py`) and is wired into
the structlog → Render → Better Stack pipeline. CORS is open (`*`) and an
OPTIONS preflight handler is in place. It was built during the iOS WKWebView
debug session but **no widget-side caller has ever been written**.

Result today: when the PG widget crashes inside the ChatGPT iframe, the
ErrorBoundary in `mcp_server/priority_guardian/widget-react/src/main.tsx`
catches the error and runs `console.error(...)`. That output stays in the
user's browser console. Nothing reaches the backend. Better Stack is blind.

This increment closes that gap. Scope is **Priority Guardian widget only**.
MindSort AI gets the same treatment in a later increment.

## Scope

Two files in `mcp_server/priority_guardian/widget-react/src/`:

1. **NEW:** `widgetErrorReporter.ts` — the reporter module (logic + caps + dedup)
2. **EDIT:** `main.tsx` — wires the reporter into the ErrorBoundary and global `window` listeners

The reporter lives in its own file so it can be unit-tested directly without
exporting internals from `main.tsx` or relying on DOM event simulation for
every assertion. This is the right unit boundary, not overengineering.

No changes to:
- The MCP tool schema (no impact — this is widget-internal)
- The MCP server (`mcp_server/priority_guardian/server.py`)
- The backend (endpoint already exists)
- Any other widget files

No new dependencies. No build config changes.

## Requirements

### R1 — Add a single error reporter helper

In `widgetErrorReporter.ts`, export a `reportWidgetError` function that
POSTs a JSON payload to:

```
https://priorities-guard-sdkapp-suite.onrender.com/api/priority-guardian/widget-error
```

Payload shape (must match the backend `WidgetErrorReport` Pydantic model
exactly — see `health_router.py`):

```ts
{
  name?: string         // error.name
  message?: string      // error.message
  stack?: string        // error.stack (truncated, see R5)
  componentStack?: string  // React errorInfo.componentStack (truncated, see R5)
  ua?: string           // navigator.userAgent
}
```

Use `fetch` with:
- `method: 'POST'`
- `headers: { 'Content-Type': 'application/json' }`
- `body: JSON.stringify(payload)`
- `keepalive: true` (so the request survives if the iframe is unloaded
  mid-crash). Browser keepalive has a 64KB cap across all in-flight
  keepalive requests; our truncated payloads (~3KB max) stay well under
  this. Do not remove the truncation in R5.

### R2 — Fire-and-forget, never throws

The reporter must:
- Be `async` but not awaited by callers
- Wrap the entire `fetch` in `try/catch` with an empty catch (silent failure)
- Never block render, never re-throw, never `console.error` on failure
  (silent — we already have the error itself in the boundary)

### R3 — Wire into ErrorBoundary

In `componentDidCatch`, after the existing `console.error(...)`, call the
reporter with `error` and `errorInfo.componentStack`. The existing
`console.error` stays — useful for local dev.

### R4 — Wire into global error handlers

Before `createRoot(...).render(...)` runs (i.e. at module scope, after the
ErrorBoundary class is defined), add two listeners:

- `window.addEventListener('error', handler)` — catches uncaught
  synchronous errors. Extract `event.error?.name`, `event.error?.message`,
  `event.error?.stack`. Fall back to `event.message` and a stack of `null`
  if `event.error` is unavailable.
- `window.addEventListener('unhandledrejection', handler)` — catches
  unhandled promise rejections. Extract from `event.reason`: if it's an
  `Error`, use `name/message/stack`; otherwise use `String(event.reason)`
  as `message` and `null` for `stack`.

Both handlers call the same reporter. `componentStack` is omitted (only
React provides that).

### R5 — Caps to prevent abuse

- **Stack truncation:** truncate `stack` and `componentStack` to **2000
  characters each** before sending. (Better Stack ingestion costs scale
  with payload size; full stacks are rarely needed past the top frames.)
- **Per-session cap:** maintain a module-level counter. Reject calls after
  **10 reports per page load** to prevent infinite-loop crash storms from
  hammering the backend. No user-facing message — silent drop.
- **Deduplication:** maintain a `Set<string>` of seen `name + message`
  combinations. Skip if already seen this session. (Prevents the same
  render error from firing on every re-render.)

### R6 — Data minimization

This increment does not intentionally collect any user or app state.
However, `error.message` strings and stack traces can incidentally
contain user data depending on what crashed (e.g., a serialization error
might include a property name or value from a priority object). Truncation
in R5 limits exposure but cannot eliminate it. This is acceptable for
crash diagnostics and consistent with the existing ErrorBoundary fallback
UI, which already exposes the same fields to the user themselves.

Do **not** intentionally capture:
- `window.openai.toolOutput` (contains user priorities/goals)
- React component props or state
- DOM contents
- localStorage / sessionStorage
- URL or referrer
- User identifiers of any kind

## Backend URL — hardcoded, intentional

Hardcode `https://priorities-guard-sdkapp-suite.onrender.com/api/priority-guardian/widget-error`
as a constant at the top of `main.tsx`. The widget builds as a single
HTML file (`vite-plugin-singlefile`) with no env var injection at build
time. The backend URL is stable and documented in user memory.

## Out of scope

- Source map upload / symbolication
- A shared widget infrastructure package (deferred until MindSort AI
  needs the same — rule of two)
- MindSort AI ErrorBoundary changes
- Backend endpoint changes (already exists and is sufficient for this
  increment — endpoint has no auth or server-side rate limit, which is
  acceptable at MVP scale; revisit if Better Stack volume becomes a
  problem)
- Rate limiting on the backend (R5 client-side caps are sufficient at
  current scale)

## Implementation Approach

### File 1 — `widgetErrorReporter.ts` (new)

Greenfield module. Exports:
- `reportWidgetError(payload)` — the main entry point
- (Optionally) `__resetReporterStateForTesting()` — test-only helper to
  reset `errorCount` and `seenErrors` between tests. Internal use only.

Module-level state: `errorCount: number`, `seenErrors: Set<string>`,
`WIDGET_ERROR_ENDPOINT` constant.

### File 2 — `main.tsx` (existing — minimal edits only)

Copy the existing `main.tsx` verbatim. Make only these adjustments:

1. Add `import { reportWidgetError } from './widgetErrorReporter'` near
   the top.
2. Add the global `error` and `unhandledrejection` listeners at module
   scope, after the ErrorBoundary class definition and before
   `createRoot(...).render(...)`.
3. Add one line inside `componentDidCatch` to call `reportWidgetError`
   after the existing `console.error(...)`.

Do NOT rewrite, restructure, or "improve" anything else in `main.tsx` —
including the existing ErrorBoundary fallback UI, the locale-setting IIFE,
or the root element lookup.

## Unit Tests

Two test files.

### File A — `src/__tests__/widgetErrorReporter.test.ts` (reporter unit tests)

Mock `global.fetch`. Reset reporter state (`__resetReporterStateForTesting`)
in `beforeEach`. Verify:

| Test | Expected |
|------|----------|
| Sends POST with correct URL | `fetch` called with `https://priorities-guard-sdkapp-suite.onrender.com/api/priority-guardian/widget-error` |
| Sends correct payload shape | Body matches `WidgetErrorReport` schema (`name`, `message`, `stack`, `componentStack`, `ua`) |
| Uses `keepalive: true` | fetch options include `keepalive: true` |
| Sends `Content-Type: application/json` | Request header present |
| Stack truncated to 2000 chars | A 5000-char stack is sent as 2000 chars |
| componentStack truncated to 2000 chars | Same as above |
| Swallows fetch rejection | `fetch.mockRejectedValue(new Error('network'))` → no throw, no rethrow |
| Per-session cap enforced — distinct messages | Call reporter with **11 distinct messages** ("err1", "err2", ..., "err11"); fetch called exactly 10 times. (Distinct messages required so dedup does not eat the calls before the cap fires.) |
| Deduplication enforced | Same `name + message` called 5 times; fetch called exactly once |
| Cap and dedup interaction | 5 distinct messages each repeated 3 times = 15 calls total → fetch called exactly 5 times (dedup wins before cap is reached) |
| Non-Error rejection-style payload | Reporter accepts a payload with `stack: null` and serializes correctly |

### File B — `src/__tests__/ErrorReporterIntegration.test.tsx` (wiring tests)

Mock the `widgetErrorReporter` module (`vi.mock('./widgetErrorReporter')`).
Verify that the wiring in `main.tsx` calls the (mocked) reporter correctly:

| Test | Expected |
|------|----------|
| ErrorBoundary integration | Render a child component that throws on mount; assert mocked `reportWidgetError` was called with `{name, message, stack, componentStack, ua}` where `componentStack` is non-empty |
| `window.error` listener integration | Dispatch `new ErrorEvent('error', { message: 'x', error: new Error('x') })` on `window`; assert reporter called with `componentStack: undefined` |
| `unhandledrejection` listener integration | Dispatch synthetic event with `event.reason = new Error('x')`; assert reporter called with the error fields |
| Non-Error rejection reason handled | Dispatch synthetic event with `event.reason = 'plain string'`; assert reporter called with `{message: 'plain string', stack: null}` |

## Integration Tests

None for this increment. The backend endpoint already has implicit coverage
through structlog tests, and there is no meaningful boundary to integration-
test on the widget side beyond the unit tests above (the network call is
fire-and-forget).

A manual smoke test is sufficient post-deploy — see "Pre-Deploy Checks".

## Pre-Deploy Checks

Before pushing:

1. **Read `doc/OPERATIONS_PREDEPLOY.md`** and complete all listed pre-deploy
   tasks (Alembic head check etc.).
2. Run the new unit test suite: `cd mcp_server/priority_guardian/widget-react && npm test`
3. Verify the widget builds: `npm run build`. Output is
   `mcp_server/priority_guardian/widgets/pg-dashboard.html`.
4. Confirm backend is unchanged — no migration, no router change.
   `git diff backend/` should be empty.

After deploy:

5. **Manual smoke test:** open the widget on desktop ChatGPT, open DevTools
   on the widget iframe, and run this in the iframe console:

   ```js
   window.dispatchEvent(new ErrorEvent('error', {
     message: 'test widget reporting',
     error: new Error('test widget reporting')
   }))
   ```

   Within ~5s, the error should appear in Better Stack with
   `event = "widget.client_error"` and `error_message = "test widget reporting"`.

   **Why dispatch instead of `throw`:** running `throw new Error(...)`
   directly in the DevTools console executes in the DevTools context, not
   the iframe's main script context, so the `window.error` listener
   registered in `main.tsx` may not fire. The synthetic dispatch reliably
   triggers the listener.

6. If step 5 succeeds, the increment is complete.
