# PG Widget Increment A: Foundation + Read-Only Display + Google Connect/Disconnect

## Objective

Create the Priority Guardian dashboard widget that displays current priorities (read-only) and provides UI-based Google Calendar connect/disconnect controls. No CRUD operations in this increment.

---

## What Exists

### Backend (deployed on Render)
- `backend/apps/priority_guardian/routers/priorities_router.py` — Priority CRUD endpoints
- `backend/apps/priority_guardian/routers/google_connection_router.py` — Connection status + initiate endpoints
- `backend/apps/priority_guardian/routers/offboarding_router.py` — Disconnect with Google token revocation
- `backend/apps/priority_guardian/db_models.py` — PG priority + deliverable models
- DB tables: `pg_priorities`, `pg_deliverables` (migration `m3h4i5j6k7l8`)
- Backend public URL: `https://priorities-guard-sdkapp-suite.onrender.com`

### MCP Server
- `mcp_server/priority_guardian/server.py` — App factory, middleware, ASGI entrypoint
- `mcp_server/priority_guardian/tools/connect_google_calendar.py` — Checks status, returns connect URL
- `mcp_server/priority_guardian/tools/disconnect_google_calendar.py` — Requires confirm=true, calls disconnect endpoint
- `mcp_server/priority_guardian/tools/__init__.py` — TOOL_REGISTRY with existing tools
- `mcp_server/priority_guardian/handlers/tools.py` — Dispatcher
- `mcp_server/priority_guardian/http_client.py` — backend_get/backend_post helpers

### NOT yet built
- No widget HTML file
- No widget resource registration in server.py
- No `get_priorities` MCP tool
- No `_meta["openai/outputTemplate"]` on any tool
- No `widget_accessible` field on ToolDefinition

---

## Reuse from Clarity (mandatory reference)

Clarity's widget is the production reference for all widget patterns. Do NOT reinvent these — copy and adapt.

### Exact files to reference

| Pattern | Clarity file | What to reuse |
|---------|-------------|---------------|
| Resource registration | `mcp_server/clarity/server.py` | `_list_resources()`, `_handle_read_resource()`, `_embedded_widget_resource()`, `request_handlers` registration |
| Tool response with widget | `mcp_server/clarity/server.py` | `_call_tool_request()` — structuredContent + `_meta` with `openai/outputTemplate`, `openai/widgetAccessible`, `openai/resultCanProduceWidget`, embedded widget resource |
| Tool `_meta` structure | `mcp_server/clarity/server.py` | `_tool_meta()` helper — annotations (readOnlyHint, destructiveHint, openWorldHint), outputTemplate, widgetAccessible |
| Widget data access | `mcp_server/clarity/widget-react/src/App.tsx` | `window.openai.toolOutput` for reading structuredContent, `window.openai.callTool()` for save/mutations |
| Theme handling | `mcp_server/clarity/widget-react/src/App.tsx` | `window.openai.theme` detection, `openai:set_globals` event listener for theme changes |
| Widget build pipeline | `mcp_server/clarity/widget-react/` | Entire scaffold: `vite.config.ts`, `package.json`, `tsconfig.json`, `main.tsx`, `main.css`. Copy directory, strip Clarity-specific components. |
| Widget build output | `mcp_server/clarity/widgets/clarity-clusters.html` | Single compiled HTML file pattern — inline CSS + JS, no external deps |

### Specific patterns to copy

**1. Resource registration in server.py** — Clarity uses manual `request_handlers` override (NOT `@mcp.resource()` decorator, which doesn't support `_meta`):
```
mcp._mcp_server.request_handlers[mcp_types.ReadResourceRequest] = _handle_read_resource
```

**2. Embedded widget in tool response** — Clarity embeds widget HTML as `EmbeddedResource` in tool call results. Copy `_embedded_widget_resource()` helper.

**3. `callTool` from widget** — Clarity's widget calls `window.openai.callTool("save_board", { clusters })` for mutations. PG widget uses same pattern for connect/disconnect/get_priorities.

**4. Theme switching** — Clarity listens for `openai:set_globals` events and reads `window.openai.theme`. Copy this pattern exactly.

**5. `list_tools()` _meta** — Clarity's `list_tools` handler includes `openai/widgetAccessible`, `openai/outputTemplate`, `openai/resultCanProduceWidget`, and `annotations` in each tool's `_meta`. Copy this structure for PG tools.

### What is NOT reusable from Clarity

- Clarity's `tool_logic.py` (cluster enrichment) — PG has no equivalent processing layer, data comes straight from backend.
- Clarity's component structure (ClusterCard, SubCluster, etc.) — PG has its own card types (Deadline, Flexible). Build new components, but follow Clarity's component patterns.
- Clarity's `save_board` tool logic — PG uses different mutation tools (deferred to Inc B).

---

## Deliverables

### 1. Widget HTML Template

Single self-contained HTML file. Registered as MCP resource with MIME type `text/html+skybridge`.

**Source:** `mcp_server/priority_guardian/widget-react/` (React + Vite, same as Clarity)
**Build output:** `mcp_server/priority_guardian/widgets/pg-dashboard.html` (single compiled HTML)
**Resource path:** `mcp_server/priority_guardian/resources/pg-dashboard.html` (or wherever server.py reads from — match Clarity's pattern)

**Architecture:** React + Vite build pipeline, copied from `mcp_server/clarity/widget-react/`. Produces a single compiled HTML file with inline CSS+JS. Same build tooling, same `window.openai` hooks, same output format. Starting with React avoids rewriting when Inc B adds CRUD and Inc C adds the time allocation bar.

Copy Clarity's:
- `vite.config.ts` (single-file HTML output config)
- `package.json` (dependencies, build scripts)
- `src/main.tsx` (CSS import + createRoot pattern)
- `src/main.css` (SDK UI imports: `@import "tailwindcss"`, `@import "@openai/apps-sdk-ui/css"`)
- `src/hooks/useOpenAiGlobal.ts` (if extracted — the `useSyncExternalStore` hook for theme/toolOutput reactivity)

Adapt Clarity's `App.tsx` structure for PG's data model. Do NOT copy Clarity's cluster rendering logic — only the `window.openai` integration patterns.

**What the widget displays:**

**A. Connection Status Header (top of widget)**
- When disconnected: "Google Calendar: Not connected" + "Connect" button
- When connected: "Google Calendar: Connected ✓" + "Disconnect" button
- Connect button: calls `connect_google_calendar` tool via `callTool`, receives `connect_url`, calls `window.openai.openExternal({ href: connect_url })` to open OAuth flow in browser
- Disconnect button: shows confirmation prompt (not HTML `<form>`, use JS confirm or custom inline confirmation), then calls `disconnect_google_calendar` tool via `callTool` with `{ confirm: true }`
- After connect/disconnect: re-call `get_priorities` to refresh state (connection status is embedded in the response)

**B. Priority Cards (body)**
- Rendered from `get_priorities` response data
- One card per active priority, ordered by calendarKeyword (P1, P2, P3)
- Max 3 active priorities

**Deadline Card layout:**
- Header: `[P1]` badge (colored) + priority name
- Type badge: "⏱ Deadline"
- Progress: "[X] of [Y] done · [N]d left"
- Calendar keyword reminder: "📅 Tag calendar events with **P1** to track time"
- Deliverables section: read-only checklist (gray checkbox + strikethrough when done)

**Flexible Card layout:**
- Header: `[P2]` badge (colored) + priority name
- Type badge: "↻ Flexible"
- Checkpoint: "[N]d until check-in"
- Calendar keyword reminder: "📅 Tag calendar events with **P2** to track time"
- 1-month goal section: header "1-MONTH GOAL" + "by [checkpoint date]" + desiredResult text
- Hour ring: actual vs target weekly hours (neutral gray, no judgment colors)

**C. Empty State**
- When no priorities exist: friendly message indicating the user should set up priorities through conversation
- Do NOT show "Add priority" button in this increment (that's Inc B)

**D. Loading State**
- Show skeleton/spinner while `get_priorities` call is in flight

### 2. `get_priorities` MCP Tool

**New tool file:** `mcp_server/priority_guardian/tools/get_priorities.py`

Follows MCP Server Implementation Standard: one file, one tool, fully self-contained. Uses ToolDefinition dataclass. Handler signature: `async def handle(user_id: str, correlation_id: str, arguments: dict) -> CallToolResult`.

**Tool metadata:**
- name: `get_priorities`
- visibility: public (LLM can call it for onboarding, reflection, "how am I doing")
- widgetAccessible: true (widget calls it on mount and after mutations)
- read_only_hint: true
- destructive_hint: false
- open_world_hint: false
- required_scopes: `["pg.access"]`
- widget_uri: `"ui://widget/pg-dashboard.html"` (points to the registered resource)

**What it returns in structuredContent:**

```
{
  "success": true,
  "data": {
    "google_connected": true/false,
    "google_connected_at": "ISO timestamp" | null,
    "priorities": [
      {
        "id": "uuid",
        "name": "Ship Priority Guardian v1",
        "type": "deadline",
        "calendarKeyword": "P1",
        "status": "active",
        "deadline": "2026-03-15",
        "deliverables": [
          { "id": "uuid", "name": "Widget increment A", "done": true },
          { "id": "uuid", "name": "Widget increment B", "done": false }
        ],
        "createdAt": "ISO",
        "updatedAt": "ISO"
      },
      {
        "id": "uuid",
        "name": "Content marketing",
        "type": "flexible",
        "calendarKeyword": "P2",
        "status": "active",
        "weeklyHourTarget": 10,
        "weeklyHourActual": 0,
        "desiredResult": "Publish 4 blog posts about AI productivity tools",
        "checkpointDate": "2026-03-10",
        "createdAt": "ISO",
        "updatedAt": "ISO"
      }
    ]
  },
  "_meta": {
    "openai/outputTemplate": "ui://widget/pg-dashboard.html"
  },
  "assistant_guidance": "The dashboard is now showing the user's current priorities. Do not repeat or list the priorities in text — the widget displays them. If the user has no priorities, guide them through onboarding setup conversationally."
}
```

**Backend call:** `GET /api/priority-guardian/priorities` with X-User-ID header. This endpoint must return both priorities and Google connection status in a single response — the widget always needs both on mount. If `priorities_router.py` doesn't currently include connection status, add it. One call, one response.

If backend returns empty priorities list, return the structure with empty array. Widget handles empty state display.

### 3. Modify Existing Tools

**connect_google_calendar:**
- Add `_meta: { "openai/outputTemplate": "ui://widget/pg-dashboard.html" }` to structuredContent
- Add `widget_uri = "ui://widget/pg-dashboard.html"` to ToolDefinition

**disconnect_google_calendar:**
- Add `_meta: { "openai/outputTemplate": "ui://widget/pg-dashboard.html" }` to structuredContent
- Add `widget_uri = "ui://widget/pg-dashboard.html"` to ToolDefinition

### 4. ToolDefinition Extension

Add `widget_accessible: bool = False` field to `mcp_server/priority_guardian/tools/base.py` ToolDefinition dataclass.

Set `widget_accessible = True` on:
- `get_priorities`
- `connect_google_calendar`
- `disconnect_google_calendar`

### 5. Tool Registration in `tools/__init__.py`

Add `get_priorities` to TOOL_REGISTRY. Follow Clarity's `list_tools` handler pattern for `_meta` — copy the structure from `mcp_server/clarity/server.py` that includes `openai/widgetAccessible`, `openai/outputTemplate`, `openai/resultCanProduceWidget`, and `annotations` in each tool descriptor.

### 6. Widget Resource Registration in `server.py`

Follow Clarity's `server.py` pattern exactly: `_list_resources()`, `_handle_read_resource()`, `_embedded_widget_resource()`, `request_handlers` override. Do NOT use `@mcp.resource()` decorator — it doesn't support `_meta`.

Resource metadata must include:
```
_meta: {
    "openai/widgetPrefersBorder": true,
    "openai/widgetDomain": "https://chatgpt.com",
    "openai/widgetCSP": {
        "connect_domains": ["https://chatgpt.com"],
        "redirect_domains": ["https://priorities-guard-sdkapp-suite.onrender.com"]
    }
}
```

- `redirect_domains` is required so `openExternal` can open the OAuth URL on the backend domain and return to ChatGPT without the safety interstitial modal.
- `connect_domains` allows the widget's `callTool` to communicate with ChatGPT's runtime.

---

## Design Requirements

### OpenAI Design Tokens (mandatory)

Use the SDK design token system. Reference: `openai-sdk-ui-tokens-reference.md` in project knowledge.

**Colors:**
- P1 badge: `bg-success-soft-alpha` + `text-success` (green semantic)
- P2 badge: `bg-warning-soft-alpha` + `text-warning` (orange semantic)
- P3 badge: `bg-danger-soft-alpha` + `text-danger` (red semantic)
- Card backgrounds: `bg-surface` or `bg-surface-secondary`
- Card borders: `border-default` with `rounded-xl`
- Text: `text-default`, `text-secondary`, `text-tertiary`

**Typography:**
- System font stack only (`font-sans`). No custom fonts.
- Priority name: `heading-sm` or `heading-xs`
- Body text: `text-base` or `text-sm`
- Labels/metadata: `text-xs` + `text-secondary`

**Spacing:** Use 4px base unit system. Cards separated by `gap-3` or `gap-4`.

### Dark Mode
- Widget must support light/dark via `data-theme` attribute on root element
- All semantic color tokens auto-switch between modes
- Detect theme from `window.openai.theme` or `data-theme` attribute

### Accessibility (compliance A6)
- All interactive elements keyboard-focusable
- ARIA labels on buttons, status indicators
- Minimum contrast WCAG AA
- Screen reader: connection status announced, priority card content structured

### Responsive
- Must work at ChatGPT's inline card width (mobile ~320px to desktop)
- No horizontal scroll

---

## SDK Constraints (compliance blockers if violated)

- **A11:** No localStorage/sessionStorage for core state. Use `window.openai.setWidgetState()` for UI state only (e.g., which section is expanded). Priority data always fetched fresh from server.
- **A12:** No HTML `<form>` elements. Use `onClick` handlers.
- **A1:** Single compiled HTML file (built from React via Vite). All CSS and JS inline in build output.
- **A2:** Every tool returning UI must include `_meta["openai/outputTemplate"]`
- **A3:** Widget file registered as MCP resource
- **A4:** `try/catch` around `window.openai.toolOutput` with friendly fallback text
- **A10:** All backend errors caught and displayed as readable messages in widget
- **11b:** No browser cookies (iframe sandbox blocks them)
- Compliance ref 12: No custom fonts — system font stack only

---

## Widget Data Flow

1. Widget mounts → calls `get_priorities` via `window.openai.callTool("get_priorities", {})` → receives priority data + connection status → renders cards + connection header
2. User clicks "Connect" → widget calls `callTool("connect_google_calendar", {})` → receives `connect_url` → calls `window.openai.openExternal({ href: connect_url })` → user completes OAuth in browser → returns to ChatGPT
3. After OAuth return: widget has no automatic callback. User interaction triggers re-fetch. Add a "Refresh" affordance or re-fetch on visibility change if SDK supports it. At minimum, re-call `get_priorities` to update connection status.
4. User clicks "Disconnect" → widget shows inline confirmation ("Disconnect Google Calendar? You can reconnect anytime.") → on confirm, calls `callTool("disconnect_google_calendar", { confirm: true })` → on success, re-calls `get_priorities` to update UI

---

## What This Increment Does NOT Include

Explicitly deferred to Inc B or later:
- No add/edit/delete priority from widget (Inc B: CRUD)
- No add/edit/delete deliverable from widget (Inc B: CRUD)
- No "Add priority" button (Inc B)
- No inline editing (Inc B)
- No time allocation bar (Inc C)
- No weekly report link (Inc C)
- No `sendFollowUpMessage` bridges
- No fullscreen/PiP modes
- No drag-and-drop

---

## Unit Tests

### MCP Tool Tests (Python)

Test the `get_priorities` tool handler in isolation:

- Returns correct structuredContent shape with priorities array
- Returns `google_connected: false` when user has no Google connection
- Returns `google_connected: true` with connected_at when connected
- Returns empty priorities array (not error) when user has no priorities
- Returns `_meta.openai/outputTemplate` pointing to widget URI
- Includes `assistant_guidance` in structuredContent
- Returns priorities ordered by calendarKeyword
- Maps deadline vs flexible priority types correctly with their respective fields
- Handles backend 404 (user not found) gracefully
- Handles backend 500 gracefully with readable error

Test ToolDefinition extensions:
- `widget_accessible` field exists and defaults to False
- `get_priorities`, `connect_google_calendar`, `disconnect_google_calendar` have `widget_accessible = True`

Test tool registration:
- `list_tools()` output includes `_meta.openai/widgetAccessible` for widget-accessible tools
- `list_tools()` output includes `_meta.openai/outputTemplate` for tools with widget_uri

### Widget Component Tests (React — Vitest + React Testing Library)

Follow Clarity's test setup. Mock `window.openai` object.

- App renders loading state when `toolOutput` is null
- App renders empty state when `toolOutput.data.priorities` is empty array
- App renders DeadlineCard for type="deadline" priorities
- App renders FlexibleCard for type="flexible" priorities
- Cards ordered by calendarKeyword (P1 → P2 → P3)
- ConnectionStatus shows "Not connected" + Connect button when `google_connected: false`
- ConnectionStatus shows "Connected ✓" + Disconnect button when `google_connected: true`
- Connect button calls `window.openai.callTool("connect_google_calendar", {})`
- Disconnect button shows confirmation before calling `callTool`
- Theme switching responds to `openai:set_globals` event

## Integration Tests

- Full `get_priorities` tool dispatch through dispatcher with mocked backend responses (verifies auth → dispatch → handler → response chain)
- Widget resource registration returns valid `text/html+skybridge` content with correct `_meta` CSP config
- Connect flow: `connect_google_calendar` dispatch returns structuredContent with `connect_url` and `_meta.openai/outputTemplate`
- Disconnect flow: `disconnect_google_calendar` dispatch with `confirm=true` returns success with `_meta.openai/outputTemplate`

---

## Files to Create

| File | Purpose |
|------|---------|
| `mcp_server/priority_guardian/widget-react/` | React project directory (copy Clarity's scaffold) |
| `mcp_server/priority_guardian/widget-react/src/App.tsx` | Main widget component |
| `mcp_server/priority_guardian/widget-react/src/main.tsx` | Entry point (copy from Clarity) |
| `mcp_server/priority_guardian/widget-react/src/main.css` | SDK UI CSS imports (copy from Clarity) |
| `mcp_server/priority_guardian/widget-react/src/components/PriorityCard.tsx` | Shared card wrapper |
| `mcp_server/priority_guardian/widget-react/src/components/DeadlineCard.tsx` | Deadline priority card |
| `mcp_server/priority_guardian/widget-react/src/components/FlexibleCard.tsx` | Flexible priority card |
| `mcp_server/priority_guardian/widget-react/src/components/ConnectionStatus.tsx` | Google connect/disconnect header |
| `mcp_server/priority_guardian/widget-react/vite.config.ts` | Build config (copy from Clarity) |
| `mcp_server/priority_guardian/widget-react/package.json` | Dependencies (copy from Clarity) |
| `mcp_server/priority_guardian/widgets/pg-dashboard.html` | Build output (generated, not hand-written) |
| `mcp_server/priority_guardian/tools/get_priorities.py` | get_priorities tool (metadata + handler) |
| `tests/unit/mcp_pg/test_get_priorities.py` | Unit tests for tool |
| `tests/integration/mcp_pg/test_widget_inc_a.py` | Integration tests |
| `mcp_server/priority_guardian/widget-react/src/__tests__/App.test.tsx` | Widget component tests |

## Files to Modify

| File | Change |
|------|--------|
| `mcp_server/priority_guardian/tools/base.py` | Add `widget_accessible: bool = False` to ToolDefinition |
| `mcp_server/priority_guardian/tools/__init__.py` | Add get_priorities to TOOL_REGISTRY, update list_tools() for _meta |
| `mcp_server/priority_guardian/tools/connect_google_calendar.py` | Add _meta.outputTemplate, widget_uri, widget_accessible |
| `mcp_server/priority_guardian/tools/disconnect_google_calendar.py` | Add _meta.outputTemplate, widget_uri, widget_accessible |
| `mcp_server/priority_guardian/server.py` | Register widget resource with CSP config |

---

## Validation Criteria (Definition of Done)

1. Widget renders in ChatGPT when LLM calls `get_priorities`
2. Widget shows priority cards from backend data (read-only)
3. Widget shows Google connection status with Connect/Disconnect buttons
4. Connect button opens Google OAuth via `openExternal`
5. Disconnect button calls tool with confirmation
6. Dark mode works correctly
7. Empty state displays when no priorities exist
8. All tests pass
9. Deployed to Render and testable in ChatGPT developer mode