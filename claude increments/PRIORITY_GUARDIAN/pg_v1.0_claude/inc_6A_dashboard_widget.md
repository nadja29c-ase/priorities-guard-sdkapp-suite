# Increment Claude-06: Priority Guardian Dashboard Widget (MCP Apps Standard)

**Goal:** Implement the Priority Guardian dashboard widget for the Claude MCP server using the MCP Apps standard (SEP-1865 / `@modelcontextprotocol/ext-apps` v1.2.2). The widget renders inline in Claude.ai using the `ui://` resource URI pattern, `useApp` / `ontoolresult` bridge, and `text/html+mcp` MIME type.

---

## Verified SDK Facts (do not deviate from these)

Package: `@modelcontextprotocol/ext-apps` — v1.2.2 on npm, actively maintained.

**Tool `_meta` structure for linking to UI resource:**
```json
{
  "_meta": {
    "ui": {
      "resourceUri": "ui://pg-claude/dashboard-v1.html"
    }
  }
}
```
Note: The key is `ui.resourceUri` nested under `ui` — NOT a flat `"ui/resourceUri"` string key.

**Widget data access (React):**
```typescript
import { useApp, useHostStyles } from "@modelcontextprotocol/ext-apps/react"

const { app } = useApp({
  appInfo: { name: "Priority Guardian", version: "1.0.0" },
  capabilities: {},
  onAppCreated: (app) => {
    // CRITICAL: register ontoolresult BEFORE app.connect() is called
    app.ontoolresult = async (result) => {
      // structuredContent shape: { success: true, data: { ...DashboardData } }
      // Must access .data — never cast structuredContent directly as DashboardData
      const data = (result.structuredContent as { data?: DashboardData })?.data
      if (data?.priorities) setData(data)
    }
  }
})
// Apply host CSS variables for theme (replaces window.openai.theme)
useHostStyles(app)
```

**`app.connect()` is called automatically by `useApp` — DO NOT call manually.**

**Theming:** `useHostStyles(app)` injects the host's CSS variables into the document. Use host CSS variables (`var(--color-background-primary)`, etc.) — NOT hardcoded hex values and NOT `prefers-color-scheme`. The host controls the theme.

**MIME type:** `"text/html+mcp"` — hardcode this string in Python resource handler. The TypeScript SDK exports it as `RESOURCE_MIME_TYPE` but that constant is only in the TypeScript package.

**Build:** Use `vite-plugin-singlefile` to bundle React app into a single self-contained HTML file. This is the standard approach per official quickstart.

**CSP for Claude:** Claude computes a stable app domain via SHA-256 of the MCP server URL. Always set `_meta.ui.domain` for Claude resources — it provides iframe isolation stability regardless of whether the widget makes direct HTTP calls. Formula:
```python
import hashlib
def compute_claude_app_domain(mcp_server_url: str) -> str:
    h = hashlib.sha256(mcp_server_url.encode()).hexdigest()[:32]
    return f"{h}.claudemcpcontent.com"
```

---

## Context

The ChatGPT widget uses `window.openai.*` — a ChatGPT-specific compatibility layer not injected by Claude. The Claude widget must use `@modelcontextprotocol/ext-apps` exclusively.

| ChatGPT bridge | MCP Apps bridge |
|---|---|
| `window.openai.toolOutput` | `app.ontoolresult = (result) => result.structuredContent` |
| `window.openai.callTool(name, args)` | `app.callServerTool({ name, arguments: args })` |
| `window.openai.setWidgetState(state)` | `localStorage` keyed by `result._meta.viewUUID` |
| `window.openai.notifyIntrinsicHeight()` | `app.notifyIntrinsicHeight()` |
| `window.openai.sendFollowUpMessage(...)` | `app.sendMessage(...)` |
| `window.openai.locale` | `app.getHostContext().locale` |
| `window.openai.theme` | `useHostStyles(app)` injects CSS variables |
| `openai:set_globals` event | `app.onhostcontextchanged` |

---

## Pre-Implementation

Read `doc/OPERATIONS_PREDEPLOY.md` before starting. No backend changes.

Read these files before writing any code:
- `mcp_server/priority_guardian/handlers/resources.py` — existing resource handler (copy-adjust)
- `mcp_server/priority_guardian_claude/server_dupl.py` — to find where to register resource handlers
- `mcp_server/priority_guardian/widget-react/src/types.ts` — data contract
- `mcp_server/priority_guardian/widget-react/src/utils.ts` — utility functions to copy
- `mcp_server/priority_guardian/widget-react/src/constants.ts` — color values
- `mcp_server/priority_guardian/widget-react/src/components/HourRing.tsx` — ring geometry
- `mcp_server/priority_guardian/widget-react/src/components/DeadlineCard.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/FlexibleCard.tsx`
- `mcp_server/priority_guardian/widget-react/src/components/TimeAllocationBar.tsx`

---

## CRITICAL: Copy-Adjust, Never Rewrite

All new files follow the `_dupl` pattern. Copy source files verbatim and make only listed changes.

**For the widget specifically:** The visual components already exist and are correct in `priority_guardian/widget-react/src/`. Copy them directly. The only permitted changes are:
1. Replace `window.openai.*` bridge calls with `@modelcontextprotocol/ext-apps` equivalents
2. Remove CRUD handlers (edit/delete/save) — display only in this increment
3. Remove `@import "@openai/apps-sdk-ui/css"` and replace with `useHostStyles(app)`

Do not redesign, reimagine, or improve any component. If it works in ChatGPT, copy it and translate the bridge. The goal is visual parity, not a better widget.

---

## What Gets Built

| File/Dir | Action |
|---|---|
| `mcp_server/priority_guardian_claude/widget-react/` | New React project using `@modelcontextprotocol/ext-apps` |
| `mcp_server/priority_guardian_claude/widgets/pg-dashboard-claude.html` | Built output (single HTML file) |
| `mcp_server/priority_guardian_claude/handlers/resources_dupl.py` | New resource handler for Claude |
| `mcp_server/priority_guardian_claude/server_dupl.py` | Register resource list/read handlers |
| `mcp_server/priority_guardian_claude/response_adapter_dupl.py` | Add `_meta.ui.resourceUri` for `get_priorities` |

---

## Part A: Widget React App

Create `mcp_server/priority_guardian_claude/widget-react/` as a new project.

**Do NOT copy from `priority_guardian/widget-react/`** — the bridge API is completely different. The visual components can be copied, the bridge layer must be rewritten.

### Dependencies

Install using latest versions — do not pin:
```
npm install @modelcontextprotocol/ext-apps
npm install -D vite vite-plugin-singlefile @vitejs/plugin-react typescript tsx
```

### `vite.config.ts`

Copy from `priority_guardian/widget-react/vite.config.ts` and adjust:
- Output dir: `../widgets`
- Output filename: `pg-dashboard-claude.html`
- Use `vite-plugin-singlefile` to inline all JS/CSS into a single HTML file

```typescript
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import { viteSingleFile } from "vite-plugin-singlefile"

export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: {
    outDir: "../widgets",
    rollupOptions: {
      input: "index.html",
      output: { entryFileNames: "pg-dashboard-claude.html" }
    }
  }
})
```

### App entry — `src/App.tsx`

Core bridge pattern:

```typescript
import { useApp, useHostStyles } from "@modelcontextprotocol/ext-apps/react"
import { useState } from "react"
import type { DashboardData } from "./types"  // copy types.ts from ChatGPT widget

export function App() {
  const [data, setData] = useState<DashboardData | null>(null)

  const { app } = useApp({
    appInfo: { name: "Priority Guardian", version: "1.0.0" },
    capabilities: {},
    onAppCreated: (app) => {
      // Register BEFORE connect (useApp calls connect internally)
      app.ontoolresult = async (result) => {
        // structuredContent shape from backend: { success: true, data: { ...DashboardData } }
        // Must access .data, NOT cast structuredContent directly as DashboardData
        const incoming = (result.structuredContent as { data?: DashboardData })?.data
        if (incoming?.priorities) {
          setData(incoming)
        }
      }
    }
  })

  // Injects host CSS variables into document for theming
  useHostStyles(app)

  if (!data) {
    return <div className="loading">Loading...</div>
  }

  return <Dashboard data={data} />
}
```

### Visual components

**Copy directly from ChatGPT widget source, translating only what the bridge change requires:**

Files to copy and translate:
- `types.ts` — copy verbatim (no bridge code)
- `utils.ts` — copy verbatim (no bridge code)
- `constants.ts` — copy verbatim (no bridge code)
- `components/HourRing.tsx` — copy verbatim, remove `import { t } from '../i18n'`, replace `t('hoursUnit')` with `"h"`
- `components/DeadlineCard.tsx` — copy, remove edit/delete/save handlers (display only), keep visual structure
- `components/FlexibleCard.tsx` — copy, remove edit/delete/save handlers (display only), keep visual structure
- `components/TimeAllocationBar.tsx` — copy, remove `onRefresh`/`isRefreshing` props (display only)
- `components/DeliverableItem.tsx` — copy, remove toggle/rename/delete handlers (display only)
- `components/GoalItem.tsx` — copy, remove toggle/rename/delete handlers (display only)
- `components/GoalSection.tsx` — copy, remove add/edit handlers (display only)
- `components/ChevronIcon.tsx` — copy verbatim

**CSS:** Remove `@import "@openai/apps-sdk-ui/css"` — not available. Use `useHostStyles(app)` instead which injects the equivalent CSS variables from the host. Keep `var(--*)` token references where the host is likely to provide them. However: **do not assume all OpenAI SDK token names exist in Claude's host.** Where a token may be missing, add a CSS fallback value — e.g. `var(--color-background-primary, #ffffff)`. This prevents invisible rendering if a token is absent.

**For this increment (display only):**
- No CRUD: no add/edit/delete buttons, no form inputs
- No `app.callServerTool()` calls
- Collapsible sections (deliverables, goals) — collapsed by default, toggle works

### `i18n` replacement

The ChatGPT widget uses `i18n.ts`. Copy it as-is, or replace `t()` calls with English strings inline for the Claude widget — simpler and sufficient for this increment.

---

## Part B: Resource Handler — `handlers/resources_dupl.py`

Copy `mcp_server/priority_guardian/handlers/resources.py` verbatim. Make only these changes:

**Header comment:**
```python
# (duplicate) — exists because Claude uses MCP Apps standard (text/html+mcp MIME type,
# no openai/* keys in _meta). ChatGPT uses text/html;profile=mcp-app and openai/* keys.
# Post-OpenAI-approval refactor: consolidate into mcp_server/shared/ and delete this file.
```

**Change 1 — Imports:**
```python
from mcp_server.priority_guardian_claude.config import (
    BACKEND_URL,
    MCP_SERVER_URL,
)
```

**Change 2 — Widget path, URI, MIME type constants:**
```python
WIDGET_MIME_TYPE = "text/html+mcp"  # MCP Apps standard
WIDGET_URI = "ui://pg-claude/dashboard-v1.html"
WIDGET_PATH = Path(__file__).parent.parent.joinpath("widgets/pg-dashboard-claude.html")

# Claude app domain for CSP (SHA-256 of MCP server URL, first 32 hex chars)
import hashlib
_hash = hashlib.sha256(MCP_SERVER_URL.encode()).hexdigest()[:32]
WIDGET_APP_DOMAIN = f"{_hash}.claudemcpcontent.com"
```

**Change 3 — `list_resources`:** Update `mimeType` to `WIDGET_MIME_TYPE`. Remove all `openai/*` keys from `_meta`. Keep `ui.domain` and `ui.csp`.

**Change 4 — `list_resource_templates`:** Same — update `mimeType`, remove `openai/*` keys.

**Change 5 — `handle_read_resource`:** Update MIME type in `TextResourceContents`. Remove all `openai/*` keys from `resource_meta`. Set `ui.domain` to `WIDGET_APP_DOMAIN`.

Example resource `_meta` for Claude:
```python
resource_meta = {
    "ui": {
        "domain": WIDGET_APP_DOMAIN,
        "csp": {
            "connectDomains": [],   # No direct HTTP from widget in 07A
            "resourceDomains": [],  # Self-contained HTML
        },
    },
}
```

No other changes.

---

## Part C: Adapter Change — `response_adapter_dupl.py`

The adapter currently strips `_meta` from `structuredContent` (correct). For `get_priorities`, the Claude server also needs to set the top-level `CallToolResult._meta` with the widget resource URI so the host knows which resource to render.

**Per the verified spec:** the `_meta` structure is `{ "ui": { "resourceUri": "ui://..." } }` — nested under `"ui"`, not a flat key.

**Add one constant at module level:**
```python
_GET_PRIORITIES_WIDGET_URI = "ui://pg-claude/dashboard-v1.html"
```

**Add a new public function:**
```python
def adapt_get_priorities_meta(result: mcp_types.CallToolResult) -> mcp_types.CallToolResult:
    """
    Set top-level _meta for get_priorities to reference the Claude widget resource.

    Per MCP Apps standard (SEP-1865), the host reads _meta.ui.resourceUri from
    the top-level CallToolResult _meta to determine which UI resource to render.
    Structure: { "ui": { "resourceUri": "ui://..." } }

    Called by the dispatcher after adapt_tool_result() for get_priorities only.
    """
    existing_meta = dict(result.meta) if result.meta else {}
    existing_ui = dict(existing_meta.get("ui", {}))
    existing_ui["resourceUri"] = _GET_PRIORITIES_WIDGET_URI
    existing_meta["ui"] = existing_ui

    return mcp_types.CallToolResult(
        content=result.content,
        structuredContent=result.structuredContent,
        isError=result.isError,
        _meta=existing_meta,
    )
```

---

## Part D: Dispatcher Change — `handlers/tools_dupl.py`

After `result = adapt_tool_result(result)`, add:

```python
# Set top-level _meta for widget-linked tools
if name == "get_priorities":
    from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_get_priorities_meta
    result = adapt_get_priorities_meta(result)
```

---

## Part E: Server Registration — `server_dupl.py`

Read `server_dupl.py` to find the NOTE comment about resources returning empty lists. Use the **exact same decorator style already used in `server_dupl.py` for tool registration** — do not introduce a different pattern. Replace the empty resource implementations with the equivalent pattern pointing to the Claude resource handler.

The following is illustrative only — adapt decorator syntax to match what already exists in `server_dupl.py`:

```python
# Example only — match the actual decorator style in server_dupl.py
from mcp_server.priority_guardian_claude.handlers.resources_dupl import (
    list_resources as _list_resources,
    list_resource_templates as _list_resource_templates,
    handle_read_resource as _handle_read_resource,
)

@mcp.list_resources()
async def _resources():
    return await _list_resources()

@mcp.list_resource_templates()
async def _resource_templates():
    return await _list_resource_templates()

@mcp.read_resource()
async def _read_resource(req):
    return await _handle_read_resource(req)
```

---

## What NOT to Touch

- Any file in `mcp_server/priority_guardian/` — ChatGPT widget, shared tools, existing resources handler
- Any file in `backend/`
- `adapt_tool_result()` core logic (Steps 1–6) in `response_adapter_dupl.py`

---

## Tests

Add to `tests/unit/mcp_pg_claude/test_scaffold.py`:

**`test_adapt_get_priorities_meta_sets_widget_uri`**
```python
from mcp_server.priority_guardian_claude.response_adapter_dupl import adapt_get_priorities_meta

result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="3 priorities")],
    structuredContent={"success": True, "data": {"priorities": []}},
)
adapted = adapt_get_priorities_meta(result)
assert adapted.meta is not None
# Correct nested structure per MCP Apps spec
assert adapted.meta.get("ui", {}).get("resourceUri") == "ui://pg-claude/dashboard-v1.html"
# Content and structuredContent unchanged
assert adapted.content == result.content
assert adapted.structuredContent == result.structuredContent
```

**`test_adapt_get_priorities_meta_preserves_existing_meta`**
```python
result = mcp_types.CallToolResult(
    content=[mcp_types.TextContent(type="text", text="3 priorities")],
    structuredContent={"success": True},
    _meta={"existing_key": "existing_value", "ui": {"other": "value"}},
)
adapted = adapt_get_priorities_meta(result)
# resourceUri added to existing ui dict
assert adapted.meta["ui"]["resourceUri"] == "ui://pg-claude/dashboard-v1.html"
# Other ui fields preserved
assert adapted.meta["ui"]["other"] == "value"
# Non-ui keys preserved
assert adapted.meta["existing_key"] == "existing_value"
```

Run after implementation:
```
pytest tests/unit/mcp_pg_claude/test_scaffold.py -v
```
All existing tests must continue to pass.

---

## Definition of Done

- [ ] `widget-react/` React project uses `@modelcontextprotocol/ext-apps` (NOT `window.openai`)
- [ ] Widget receives data via `app.ontoolresult` using `result.structuredContent.data` (not `result.structuredContent` directly)
- [ ] `useHostStyles(app)` called for theming — no hardcoded colors
- [ ] Widget renders display-only: TimeAllocationBar, DeadlineCard, FlexibleCard
- [ ] Visual output matches ChatGPT widget (same components, same logic, same structure)
- [ ] `widgets/pg-dashboard-claude.html` built as single self-contained HTML file via `vite-plugin-singlefile`
- [ ] `handlers/resources_dupl.py` serves widget at `ui://pg-claude/dashboard-v1.html` with MIME type `text/html+mcp`
- [ ] No `openai/*` keys anywhere in Claude resource handler
- [ ] `adapt_get_priorities_meta()` sets `_meta.ui.resourceUri` (nested under `ui`)
- [ ] Dispatcher calls `adapt_get_priorities_meta()` for `get_priorities`
- [ ] Resources registered on Claude server
- [ ] Both new unit tests pass
- [ ] All existing scaffold tests pass
- [ ] Manual test: ask Claude "show me my priorities" — widget renders inline in Claude.ai

