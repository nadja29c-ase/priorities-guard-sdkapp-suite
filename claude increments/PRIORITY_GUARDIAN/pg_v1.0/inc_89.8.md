# Increment 89.8 — Route diagnostic events through `callTool` to bypass browser CSP

**Type:** Bug fix / architecture change. The browser-CSP path for widget→backend diagnostics is fundamentally broken on the published PG app; route via the MCP bridge instead.

**Why this is the next step:** Inc 89.6 (new-form `_meta.ui.csp.connectDomains`) and Inc 89.7 (legacy-form `openai/widgetCSP.connect_domains`) both failed to allow the diagnostic POST. The hardcoded sandbox CSP allowlist appears to ignore both declared forms for already-approved apps. Issue #85 (Oct 2025, still open) describes the same failure. We've exhausted the CSP-config approach. Time to bypass browser CSP entirely.

**Mechanically:** `window.openai.callTool()` invokes an MCP tool via the host iframe bridge (postMessage / JSON-RPC). The host (ChatGPT) makes the HTTP request to the MCP server from outside the iframe. The browser's iframe CSP does not apply to the MCP bridge — it only applies to network requests made FROM the iframe. So routing diagnostic events through `callTool` sidesteps the CSP problem entirely.

This same architecture is already used by every widget-callable tool in PG (add_priority, update_priority, connect_google_calendar, etc.) — it's the proven path.

---

## Implementation Approach — Copy the Existing Private-Tool Pattern, Don't Invent

`mcp_server/priority_guardian/tools/widget_tools/` already contains 11 private widget-only tools that are invisible to the LLM. The new diagnostic tool follows the exact same pattern. Don't restructure, don't invent new conventions, don't add config layers — just copy the shape of an existing tool with adjustments for what diagnostic events need.

---

## Files Touched (4)

1. **`mcp_server/priority_guardian/tools/widget_tools/record_widget_diagnostic.py`** — NEW. Private MCP tool that takes a diagnostic event payload and logs it via structlog (same logger destination as the now-broken HTTP endpoint).
2. **`mcp_server/priority_guardian/tools/widget_tools/__init__.py`** — Add `RECORD_WIDGET_DIAGNOSTIC` import and export.
3. **`mcp_server/priority_guardian/tools/__init__.py`** — Register `RECORD_WIDGET_DIAGNOSTIC` in `TOOL_REGISTRY`.
4. **`mcp_server/priority_guardian/widget-react/src/widgetErrorReporter.ts`** — Replace `fetch()`-based `reportWidgetDiagnostic` with a `callTool('record_widget_diagnostic', ...)`-based implementation. Drop the fetch endpoint constant. Keep the cap and silent-failure semantics.

The widget bundle is rebuilt. The shared-backend `widget_diagnostic.py` HTTP endpoint stays in place but becomes unused — leave it for now; delete in a cleanup increment.

The `_meta.ui.csp.connectDomains` and `openai/widgetCSP.connect_domains` additions from Inc 89.6 and 89.7 stay in place. They're documented best practice and don't hurt anything. If OpenAI fixes Issue #85, our future widget→backend HTTP calls will work. For now we just don't depend on them.

---

## Edits

### 1. NEW: `mcp_server/priority_guardian/tools/widget_tools/record_widget_diagnostic.py`

Pattern reference: `mcp_server/priority_guardian/tools/widget_tools/connect_google_calendar.py`. Copy the structure (module docstring, imports, NAME/DESCRIPTION/INPUT_SCHEMA constants, handle function, ToolDefinition export). Adjust as below.

Full file content:

```python
"""
record_widget_diagnostic tool for Priority Guardian MCP.

Private widget-only tool that receives diagnostic events from the widget
and logs them via structlog. Used by the Inc 89 fullscreen flash-revert
diagnostic instrumentation.

This tool exists because browser CSP blocks direct widget->backend HTTP
calls (Issue #85, still open as of May 2026). Routing through the MCP
bridge bypasses iframe CSP entirely.

Visibility: private (widget-only, hidden from LLM).
"""

import json

import structlog
from mcp import types as mcp_types

from ..base import ToolDefinition, ToolUsageError

logger = structlog.get_logger(__name__)

# Same byte limit as the (now-broken) HTTP endpoint enforced.
# Reject oversized payloads loudly so we know if the widget is shipping
# diagnostic data larger than expected.
MAX_DATA_BYTES = 2048

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "record_widget_diagnostic"

DESCRIPTION = (
    "Record a diagnostic event from the widget. Private widget-only tool — "
    "the model never sees or calls this. Used for production debugging of "
    "widget runtime behavior."
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "event": {
            "type": "string",
            "minLength": 1,
            "maxLength": 100,
            "description": "Event name, e.g. 'mount', 'displayMode.change', 'set_globals'",
        },
        "data": {
            "type": "object",
            "description": "Event-specific structured data. Serialized form must not exceed 2048 bytes.",
            "additionalProperties": True,
        },
        "ts": {
            "type": "integer",
            "description": "Client-side timestamp (ms since epoch)",
        },
        "ua": {
            "type": "string",
            "maxLength": 500,
            "description": "User agent string",
        },
    },
    "required": ["event"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Record a widget diagnostic event.

    Validates the payload size and logs structurally via structlog at INFO
    level under event name `widget.diagnostic`. The log entry is shipped to
    Better Stack by the existing logging pipeline.

    Returns a minimal success response. The widget reporter does not parse
    the response — this is fire-and-forget from the widget's perspective.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments (event, data, ts, ua)

    Returns:
        CallToolResult with minimal success indicator (no LLM-visible narration —
        this is a private widget-only tool; verbose text content is unnecessary
        surface area).
    """
    event_name = arguments.get("event")
    if not isinstance(event_name, str) or not event_name.strip():
        raise ToolUsageError("event field is required and must be a non-empty string")

    # Server-side length enforcement. Per ToolDefinition contract: the dispatcher
    # does NOT validate against input_schema, so schema maxLength is advisory only.
    # Handlers must enforce limits themselves.
    if len(event_name) > 100:
        raise ToolUsageError("event field exceeds 100 characters")

    data = arguments.get("data") or {}
    if not isinstance(data, dict):
        raise ToolUsageError("data field must be an object")

    # Enforce serialized size limit. Same threshold the HTTP endpoint used.
    serialized = json.dumps(data, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > MAX_DATA_BYTES:
        raise ToolUsageError(
            f"diagnostic data exceeds {MAX_DATA_BYTES} bytes — reduce payload size"
        )

    ts = arguments.get("ts")

    ua = arguments.get("ua")
    if ua is not None and not isinstance(ua, str):
        raise ToolUsageError("ua field must be a string when provided")
    # Truncate ua at 500 chars even if the schema bounds it — defense in depth.
    ua_truncated = ua[:500] if isinstance(ua, str) else None

    # PII minimization: log only the first 8 chars of user_id. Enough for cross-
    # session grouping during diagnostic analysis (e.g., "is this the same user
    # who reported the bug?") without putting the full identifier in logs.
    # If broader attribution is needed for abuse investigation, the correlation_id
    # is the join key — full user_id can be retrieved via auth audit trail.
    user_id_prefix = user_id[:8] if isinstance(user_id, str) else None

    # Log at INFO so it ships to Better Stack alongside other widget.diagnostic events.
    # Event name matches the original HTTP endpoint's structlog event so downstream
    # filters/dashboards keep working unchanged.
    logger.info(
        "widget.diagnostic",
        service="priority-guardian",
        user_id_prefix=user_id_prefix,
        correlation_id=correlation_id,
        diagnostic_event=event_name,
        data=data,
        client_ts=ts,
        user_agent=ua_truncated,
    )

    # Minimal response — no LLM-visible narration. Private tool; the widget
    # reporter does not read the response. structuredContent kept terse.
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="")],
        structuredContent={"ok": True},
    )


# ============================================================================
# Tool Definition
# ============================================================================

RECORD_WIDGET_DIAGNOSTIC = ToolDefinition(
    name=NAME,
    title="Record Widget Diagnostic",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,            # Does not produce widget output
    handle=handle,
    # Annotation rationale:
    # - read_only_hint=False: the tool writes a log entry. Even though the log
    #   is an append-only operational record (no user-visible state mutation),
    #   we mark it as not read-only to be honest about the side effect.
    # - destructive_hint=False: per project policy, destructiveHint applies only
    #   to permanent removal (deletes), not appends. Logging is not destructive.
    # - open_world_hint=False: no external system interaction; structlog ships
    #   to Better Stack via the existing logging pipeline (internal infrastructure).
    read_only_hint=False,
    destructive_hint=False,
    open_world_hint=False,
    widget_accessible=True,     # Widget calls this via callTool
    visibility="private",       # LLM cannot see or call
)
```

**Notes for Claude Code:**
- `read_only_hint=False`: the tool writes a log entry, which is a side effect. Marking it as read-only would be dishonest about that. Per project memory: "readOnlyHint applies to user-visible state mutation only — invisible backend bookkeeping does not make a tool non-read-only" was reasoned the other way for previous tools. Going with `False` here because (a) we want to be unambiguous about the side effect, and (b) this is a private widget-only tool — the readOnlyHint is not user-facing in any way, so leaning conservative costs nothing.
- `destructive_hint=False`: per project policy, destructiveHint applies only to permanent removal (deletes), not appends. A log write is not destructive.
- `open_world_hint=False`: no external system interaction. structlog ships to Better Stack via the existing internal pipeline, not an external API.
- `widget_accessible=True` is required so the widget can invoke it via callTool.
- `visibility="private"` ensures the LLM never sees this tool in its tool list.
- `MAX_DATA_BYTES = 2048`: same threshold as the original HTTP endpoint. One diagnostic event carries `sid` (~30 chars), `caller` (~30 chars), `next` (~10 chars), `hostMode` (~10 chars), `ts` (~10 chars), `isMobile` (boolean), and similar small fields. Total ~150-300 bytes typical. 2048 is ~7x headroom — enough for unexpected event shapes during diagnosis, low enough that the log line stays readable.
- **Cap of 20 events/session (in the widget reporter, not this tool):** ~4 events per click in the expected case (mount, set_globals, set_globals, displayMode.change). With one repro per session, 20 covers up to 5 retries with margin. Higher would be cheap (Better Stack and our log volume can absorb it), but 20 catches obvious runaway behavior — e.g. a remount loop that produces 100 events would hit the cap loud and fast, signaling a different bug.

### 2. `mcp_server/priority_guardian/tools/widget_tools/__init__.py`

Add the import and export. Append the new tool to the existing list. Reference current state of this file (read it first) and add the new entries alphabetically among the existing ones or at the end — match the surrounding style.

After the existing `from .disconnect_google_calendar import DISCONNECT_GOOGLE_CALENDAR` line, add:

```python
from .record_widget_diagnostic import RECORD_WIDGET_DIAGNOSTIC
```

In the `__all__` list, add `"RECORD_WIDGET_DIAGNOSTIC"` to the existing entries.

### 3. `mcp_server/priority_guardian/tools/__init__.py`

Add the new tool to `TOOL_REGISTRY`.

In the existing import block where private widget tools are imported (the `from .widget_tools import (...)` block), add `RECORD_WIDGET_DIAGNOSTIC` to the tuple of names being imported.

In `TOOL_REGISTRY`, add a line in the private widget-only tools section (where you see entries like `ADD_PRIORITY.name: ADD_PRIORITY`):

```python
RECORD_WIDGET_DIAGNOSTIC.name: RECORD_WIDGET_DIAGNOSTIC,
```

No new entry needed in `TOOL_INVOCATION_MESSAGES` — that dict is for public tools only; private tools don't display invocation messages.

### 4. `mcp_server/priority_guardian/widget-react/src/widgetErrorReporter.ts`

Replace the `fetch()`-based `reportWidgetDiagnostic` implementation with one that calls `window.openai.callTool('record_widget_diagnostic', ...)`. Drop the `WIDGET_DIAGNOSTIC_ENDPOINT` constant — no longer needed.

**Find the diagnostic section** (the block starting `// ============ Diagnostic Reporter (Inc 89) ============` and ending before the next major section or end of file).

**Replace** the entire section with:

```ts
// ============ Diagnostic Reporter (Inc 89 / 89.8) ============
// Temporary — remove after fullscreen flash-revert bug is diagnosed.
//
// Inc 89.8: routes through window.openai.callTool() instead of fetch().
// Browser CSP blocks direct widget->backend HTTP calls (Issue #85), so we
// invoke a private MCP tool which the host runs server-side, bypassing
// iframe CSP entirely.

const MAX_DIAGNOSTIC_EVENTS_PER_SESSION = 20
let diagnosticCount = 0

export interface WidgetDiagnosticPayload {
  event: string
  data?: Record<string, unknown>
}

interface OpenAIHostWithCallTool {
  callTool?: (name: string, args: Record<string, unknown>) => Promise<unknown>
}

export async function reportWidgetDiagnostic(payload: WidgetDiagnosticPayload): Promise<void> {
  try {
    if (diagnosticCount >= MAX_DIAGNOSTIC_EVENTS_PER_SESSION) return
    diagnosticCount++

    const host = (typeof window !== 'undefined'
      ? (window.openai as OpenAIHostWithCallTool | undefined)
      : undefined)

    if (!host?.callTool) return  // No host bridge available — silent skip

    await host.callTool('record_widget_diagnostic', {
      event: payload.event,
      data: payload.data ?? {},
      ts: Date.now(),
      ua: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
    })
  } catch {
    // Silent failure — diagnostic must never break the widget
  }
}
```

Update `__resetReporterStateForTesting` so it still resets `diagnosticCount` (no change from current behavior — verify the existing function still resets it).

### Important: keep both Inc 89.6 and Inc 89.7 CSP changes

Do NOT remove `_meta.ui.csp.connectDomains` or `openai/widgetCSP.connect_domains` from `handlers/resources.py`. They cause no harm and represent best-practice configuration. If OpenAI fixes Issue #85, our future widget→backend HTTP calls will work without further changes.

---

## Test Updates

### `widgetErrorReporter.test.ts`

The existing tests for `reportWidgetDiagnostic` mock `fetch()` and verify it was called with the right endpoint, body, etc. Those tests must be replaced.

New tests for the callTool-based implementation. Reference the existing pattern but adapt to test `window.openai.callTool`:

- Calls `window.openai.callTool` with name `'record_widget_diagnostic'` and a payload containing `event`, `data`, `ts`, `ua`
- Respects `MAX_DIAGNOSTIC_EVENTS_PER_SESSION` cap (21st call does nothing)
- Does NOT dedup (calling twice with same event triggers callTool twice)
- Silent on host promise rejection (no throw)
- Skips silently when `window.openai.callTool` is undefined (e.g., dev environment without host bridge)
- `__resetReporterStateForTesting` resets `diagnosticCount`

Setup pattern:
```ts
beforeEach(() => {
  ;(window as any).openai = {
    callTool: vi.fn().mockResolvedValue({ success: true }),
  }
})
```

### Backend test

A new unit test for the `record_widget_diagnostic` tool handler in `tests/unit/priority_guardian/`. Pattern: read an existing widget-tool test like `test_pg_priorities.py` or similar to see how the project tests tool handlers, then mirror.

Required cases:
- Valid payload → returns `CallToolResult` with `success=True`
- Missing `event` → raises `ToolUsageError`
- Empty/whitespace `event` → raises `ToolUsageError`
- `data` over 2048 bytes (serialized) → raises `ToolUsageError`
- `data` exactly 2048 bytes → succeeds (boundary case)
- `data` is not a dict (e.g., a list) → raises `ToolUsageError`

---

## Out of Scope

- **No** changes to the existing `backend/apps/priority_guardian/routers/widget_diagnostic.py` HTTP endpoint. It stays in place, unused, deletable in a future cleanup increment. Removing it now adds a moving part to this deploy that doesn't need to move.
- **No** changes to `WIDGET_URI`. Stays v12 — see "WIDGET_URI: do NOT bump" section above for why bumping is forbidden on this published app.
- **No** changes to the Inc 89 App.tsx instrumentation. The diagnostic logging is already wired correctly — it just couldn't deliver. Now it can.
- **No** changes to the Inc 83 widget-error reporter. That's a separate silent failure (same CSP root cause) — separate cleanup increment.

---

## Pre-Deploy

Read `doc/OPERATIONS_PREDEPLOY.md`. Per project rules.

Specifically:

```bash
# Verify the new tool file exists
ls -la mcp_server/priority_guardian/tools/widget_tools/record_widget_diagnostic.py

# Verify the tool is registered
grep -n "RECORD_WIDGET_DIAGNOSTIC" mcp_server/priority_guardian/tools/__init__.py
# Should show two lines: one in the import block, one in TOOL_REGISTRY.

# Verify the widget reporter no longer references the dead HTTP endpoint
grep -n "WIDGET_DIAGNOSTIC_ENDPOINT\|widget-diagnostic" mcp_server/priority_guardian/widget-react/src/widgetErrorReporter.ts
# Should return 0 results. (The HTTP endpoint references should be gone.)

# Verify the widget reporter uses callTool
grep -n "callTool" mcp_server/priority_guardian/widget-react/src/widgetErrorReporter.ts
# Should show at least one match (the new implementation).

# Rebuild widget
cd mcp_server/priority_guardian/widget-react && npm run build
cd -

# Verify the built bundle is correctly inlined
grep -c '<script[^>]*src="' mcp_server/priority_guardian/widgets/pg-dashboard.html
# Must return 0.

# Verify the build embedded the new logic — search for any string that should appear
grep -c "record_widget_diagnostic" mcp_server/priority_guardian/widgets/pg-dashboard.html
# Should return at least 1.

# Run unit tests
npm test  # widget tests
pytest tests/unit/priority_guardian/  # backend tests
```

---

## Deploy

PG MCP service requires manual deploy on Render (no auto-deploy). Procedure:

1. Push commit (widget + backend changes + rebuilt bundle).
2. Render dashboard → PG MCP service → Manual Deploy → Deploy latest commit.
3. Wait for "Deploy live".
4. Verify in PG MCP logs: `mcp.server.startup` event with current timestamp.

---

## WIDGET_URI: do NOT bump

Earlier in this debugging session, bumping `WIDGET_URI` from v12 → v14 broke the published widget entirely (returned empty, ChatGPT fell back to stale CDN cache). The cause is that OpenAI's published-app pipeline appears to pin a URI-bundle association at approval time. Bumping the URI desyncs that association.

`WIDGET_URI` stays at v12. The rebuilt widget bundle reuses the v12 URI. We are relying on ChatGPT's documented cache-bust dance (server restart + Refresh in app settings + new conversation) to deliver the new bundle content under the existing URI.

This is the pragmatic path given what we know today. If post-deploy verification (below) shows that ChatGPT is still serving the old fetch-based bundle, we have a deeper cache-busting problem on this published app and will need a separate increment to investigate. Do NOT pre-empt this by bumping the URI.

---

## Post-Deploy Verification

The primary risk is that ChatGPT's bundle cache doesn't flush after the documented dance and the running widget remains the old `fetch()`-based bundle. The verification sequence below catches this before we try to diagnose the original bug.

1. **Cache-bust dance** (all three required):
   - Confirm Render shows the PG MCP "Deploy live" with current timestamp.
   - ChatGPT app → Settings → Apps → Priority Guardian → click **Refresh**.
   - Start a **brand new conversation** (not a refresh of an existing one).

2. **Confirm the running widget is the new bundle.** In the widget iframe console:

   ```javascript
   // Should be ~340000+ — confirms the inline bundle is loaded.
   document.querySelector('script').textContent.length
   ```

   If this returns 0 with a `src=https://.../assets/main-*.js` attribute, ChatGPT is still serving the stale CDN bundle. Stop here — the deploy did not effectively take effect.

3. **PRIMARY VERIFICATION: trigger a real widget action that fires diagnostic events.**

   In ChatGPT, click "Open full dashboard". This triggers the `handleExpandToFullscreen` path which calls `logDisplayModeChange` which calls `reportWidgetDiagnostic` which (post-Inc-89.8) calls `callTool('record_widget_diagnostic', ...)`.

   Wait 5 seconds for the call to land.

   Check PG MCP service Render logs (not shared backend — the MCP server is where `callTool` dispatches arrive). Look for:

   ```
   {"event": "tool.dispatch.executing", "tool_name": "record_widget_diagnostic", ...}
   {"event": "widget.diagnostic", "diagnostic_event": "displayMode.change", ...}
   {"event": "tool.timing", "tool_name": "record_widget_diagnostic", "success": true, ...}
   ```

   If all three appear: 89.8 works, the diagnostic pipe is functional, and we can analyze the bug data.

   If `tool.dispatch.executing` for `record_widget_diagnostic` does NOT appear: the widget is still running the old bundle, OR the new bundle didn't register the tool correctly. Investigate the bundle first (recheck step 2), then the registration (`grep RECORD_WIDGET_DIAGNOSTIC mcp_server/priority_guardian/tools/__init__.py`).

4. **SECONDARY DIAGNOSTIC: manual callTool from iframe console.**

   Only if step 3 fails — and only as a diagnostic to localize the failure, not a primary gate. Some hosts restrict `callTool` from DevTools for security; a failure here does NOT necessarily mean the widget-driven path is broken.

   ```javascript
   try {
     const r = await window.openai.callTool('record_widget_diagnostic', {
       event: 'manual-test-89-8',
       data: {note: 'verification'},
       ts: Date.now(),
     });
     console.log('OK', r);
   } catch (e) {
     console.log('ERROR', e?.message ?? e);
   }
   ```

   - `OK ...` → the callTool path works at the host level; if step 3 still failed, the issue is in widget code paths, not infrastructure.
   - `ERROR Unknown tool` → tool registration didn't propagate. Check PG MCP server has restarted with new code.
   - `ERROR` other → host restriction, deploy in progress, or auth issue. Not necessarily a failure of the production path.

5. **Once step 3 succeeds**, reproduce the fullscreen bug normally (click Open full dashboard, wait for revert, wait 5 seconds). Collect the `widget.diagnostic` events for that repro, group by `sid` from the data field, and analyze against Inc 89's H1/H2/H3/H4 hypotheses.

---

## What This Increment Decides

That diagnostic instrumentation in PG widgets goes through `callTool`, not `fetch()`. Going forward, anything the widget needs to communicate to the backend that isn't tool-call business logic — diagnostics, errors, telemetry — should use this pattern, not direct HTTP. This is now the canonical PG pattern until OpenAI fixes Issue #85.

It also means **Inc 83's widget-error reporter is broken the same way** and should be migrated to callTool in a separate cleanup. That cleanup is not blocked by this increment — it can happen in parallel or later.

---

## What It Does NOT Decide

- The root cause of the fullscreen flash-revert bug. Inc 89's purpose. Still waiting for data, now finally unblocked.
- Whether to file the CSP issue with OpenAI as a published-app developer. Separate decision after we recover the diagnostic capability.
- Whether to keep the `backend/apps/priority_guardian/routers/widget_diagnostic.py` HTTP endpoint indefinitely. Leave it in place for now; delete after we've validated callTool path works for at least a week.

---

## Risk Assessment

- **Low-to-medium risk.** New code paths but follows an established pattern (private widget-only tools). The risk is in the widget rebuild and tool registration — both are well-trodden ground.
- **Rollback**: revert the commit. The widget falls back to the broken-but-known-broken state. No user-visible regression possible because the diagnostic isn't user-visible.
- **No data migration, no schema change, no API contract change for external consumers.**

---

## Effort Estimate

- New tool file: ~120 lines (mostly boilerplate matching existing pattern)
- `widget_tools/__init__.py`: 2 lines
- `tools/__init__.py`: 2 lines
- Widget reporter rewrite: ~30 lines net
- Widget tests rewrite: ~80 lines
- Backend tool tests: ~60 lines
- Total: ~300 lines, mostly additive
- Claude Code work: ~30 min
- Verification cycle: ~10 min
