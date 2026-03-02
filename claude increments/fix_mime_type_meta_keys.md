# Claude Code Briefing: Fix Widget MIME Type + _meta Key Migration

## Context

Both PG and Clarity MCP servers use **stale** widget metadata from an older OpenAI SDK version. The current OpenAI Apps SDK docs (March 2026) specify different MIME types and `_meta` key structures. The MIME type mismatch will **block widget rendering** in ChatGPT — the host only enables the MCP Apps bridge for `text/html;profile=mcp-app` resources.

**Source of truth:** https://developers.openai.com/apps-sdk/build/mcp-server/#step-1--register-a-component-template

## Scope

Three files across two apps:

1. `mcp_server/priority_guardian/handlers/resources.py`
2. `mcp_server/clarity/handlers/resources.py`
3. `mcp_server/priority_guardian/tools/__init__.py`

---

## Fix 1: MIME Type (BLOCKER)

**Current (wrong):** `mimeType="text/html+skybridge"`
**Required:** `mimeType="text/html;profile=mcp-app"`

Replace ALL occurrences in both resources.py files. This string appears in:
- `list_resources()` — Resource declaration
- `list_resource_templates()` — ResourceTemplate declaration
- `handle_read_resource()` — TextResourceContents in read response
- `embedded_widget_resource()` — TextResourceContents in embed helper

**PG resources.py:** 4 occurrences
**Clarity resources.py:** 4 occurrences

---

## Fix 2: _meta Key Structure on Widget Resources

The `_meta` keys on widget resource declarations have changed from `openai/*` flat keys to a nested `ui` object.

### Key mapping (old → new)

| Old Key (currently in code) | New Key (per current docs) | Notes |
|---|---|---|
| `openai/widgetDomain` | `ui.domain` | Required for submission. Must be an **origin** (scheme + host, no path). Must be unique per app. |
| `openai/widgetCSP` with `connect_domains` | `ui.csp` with `connectDomains` | camelCase, NOT snake_case. |
| `openai/widgetCSP` with `redirect_domains` | Keep as `openai/widgetCSP.redirect_domains` if `openExternal` is used | Legacy compat key still supported for `window.openai.openExternal`. See note below. |
| `openai/widgetAccessible` | Remove from resources | Replaced by `ui.visibility` on **tool** descriptors (not resources). |
| `openai/resultCanProduceWidget` | Remove from resources | Implied by `ui.resourceUri` on **tool** descriptors. |
| `openai/widgetDescription` | `openai/widgetDescription` | Stays — ChatGPT extension, valid on resources. |

**IMPORTANT — Do NOT put `openai/outputTemplate` on resource _meta.** That key is for tool descriptors (as a compat alias for `ui.resourceUri`). Resource _meta only uses `ui.domain`, `ui.csp`, optional `ui.prefersBorder`, and optional `openai/widgetDescription`.

### About `redirect_domains`

PG's widget calls `window.openai.openExternal({ href: connectUrl })` in `ConnectionStatus.tsx` for the Google OAuth flow. The legacy key `openai/widgetCSP.redirect_domains` is still supported for this purpose. Options:

- **Keep it** as a separate ChatGPT extension alongside the new `ui.csp`:
  ```python
  "openai/widgetCSP": {
      "redirect_domains": ["https://priorities-guard-sdkapp-suite.onrender.com"],
  },
  ```
- **Remove it** if testing confirms `openExternal` works without it.

For Clarity: no `openExternal` usage, so no `redirect_domains` needed.

### About `ui.domain`

Must be a **pure origin** (scheme + host only, no path):
- ✅ `https://pg-mcp.priority-guard.com`
- ❌ `https://pg-mcp.priority-guard.com/mcp`

Currently `MCP_SERVER_URL` is used. Verify it resolves to a pure origin in production. If it includes a path, strip it or use a dedicated constant.

### PG resources.py — target _meta structure

For `list_resources()`, `list_resource_templates()`, and `handle_read_resource()`:

```python
_meta={
    "ui": {
        "domain": MCP_SERVER_URL,  # Must be pure origin, no path
        "csp": {
            "connectDomains": [],  # Widget does NOT make HTTP calls — all via callTool/postMessage
        },
    },
    # Legacy ChatGPT extension — keep for openExternal support
    "openai/widgetCSP": {
        "redirect_domains": ["https://priorities-guard-sdkapp-suite.onrender.com"],
    },
    "openai/widgetDescription": "Shows user's priorities and Google Calendar connection status.",
},
```

Remove: `openai/widgetAccessible`, `openai/resultCanProduceWidget`, `openai/widgetDomain`, `openai/outputTemplate`.

Remove the module-level `WIDGET_CSP` constant (with its `connect_domains` snake_case key). Replace with inline `ui.csp` above.

### Clarity resources.py — target _meta structure

```python
_meta={
    "ui": {
        "domain": "https://clarity.priority-guard.com",  # Pure origin
        "csp": {
            "connectDomains": [],
            "resourceDomains": [],
        },
    },
    "openai/widgetDescription": "Shows all user's thought clusters. User decides which to prioritize.",
},
```

Remove: `openai/widgetAccessible`, `openai/resultCanProduceWidget`, `openai/widgetDomain`, `openai/widgetCSP`, `openai/outputTemplate`.

---

## Fix 3: Tool _meta Keys in PG tools/__init__.py

The `list_tools()` function builds `_meta` dicts for each tool. Two additions needed, legacy keys can be kept or cleaned up.

### a) Add `ui.resourceUri` for widget-producing tools

For tools that produce widgets, add `ui.resourceUri` pointing to the widget URI:
```python
"ui": {"resourceUri": tool_def.widget_uri},
```

### b) Add `ui.visibility` for all tools

Controls who can call the tool:
- `["model", "app"]` — model and widget can call (e.g., `get_priorities`)
- `["model"]` — model only (e.g., `create_priority`)
- `["app"]` — widget only, hidden from model (e.g., `delete_priority`, all private tools)

### c) Keep `openai/*` ChatGPT extensions

These stay as-is on tool _meta:
- `openai/outputTemplate` — compatibility alias (keep alongside `ui.resourceUri`)
- `openai/toolInvocation/invoking` — ChatGPT-specific UX (keep)
- `openai/toolInvocation/invoked` — ChatGPT-specific UX (keep)

### d) Legacy keys: optional cleanup

These old keys can be removed after migrating, but removal is NOT required for compliance:
- `openai/widgetAccessible` — superseded by `ui.visibility` containing `"app"`
- `openai/resultCanProduceWidget` — superseded by `ui.resourceUri`
- `openai/visibility` — superseded by `ui.visibility`

Recommendation: remove them to keep _meta clean, but this is cosmetic not blocking.

### Target _meta for a public widget-producing + widget-callable tool (e.g., get_priorities):

```python
meta = {
    "ui": {
        "resourceUri": tool_def.widget_uri,
        "visibility": ["model", "app"],
    },
    "openai/outputTemplate": tool_def.widget_uri,
    "openai/toolInvocation/invoking": invoking_msg,
    "openai/toolInvocation/invoked": invoked_msg,
    "annotations": annotations,
    "securitySchemes": security_schemes,
}
```

### Target _meta for a private widget-only tool (e.g., delete_priority):

```python
meta = {
    "ui": {
        "visibility": ["app"],
    },
    "annotations": annotations,
    "securitySchemes": security_schemes,
}
```

### Target _meta for a public model-only tool with widget (e.g., create_priority):

```python
meta = {
    "ui": {
        "resourceUri": tool_def.widget_uri,
        "visibility": ["model"],
    },
    "openai/outputTemplate": tool_def.widget_uri,
    "openai/toolInvocation/invoking": invoking_msg,
    "openai/toolInvocation/invoked": invoked_msg,
    "annotations": annotations,
    "securitySchemes": security_schemes,
}
```

### Target _meta for a public model-only tool WITHOUT widget (e.g., inspect_adapt):

```python
meta = {
    "ui": {
        "visibility": ["model"],
    },
    "openai/toolInvocation/invoking": invoking_msg,
    "openai/toolInvocation/invoked": invoked_msg,
    "annotations": annotations,
    "securitySchemes": security_schemes,
}
```

---

## Summary of Changes

| File | What Changes |
|------|-------------|
| `mcp_server/priority_guardian/handlers/resources.py` | MIME type (4x), _meta restructure (resources: `ui.domain`, `ui.csp`, remove `openai/outputTemplate` + `openai/widgetAccessible` + `openai/resultCanProduceWidget` + `openai/widgetDomain`), CSP key casing, remove module-level `WIDGET_CSP` constant, keep `openai/widgetCSP.redirect_domains` for `openExternal` |
| `mcp_server/clarity/handlers/resources.py` | MIME type (4x), _meta restructure (same pattern minus `redirect_domains`) |
| `mcp_server/priority_guardian/tools/__init__.py` | Add `ui.resourceUri` + `ui.visibility` to `list_tools()` _meta builder. Optionally remove legacy `openai/widgetAccessible`, `openai/resultCanProduceWidget`, `openai/visibility`. |

---

## Unit Test Instructions

Update existing tests that assert on `_meta` contents:

- Any test checking for `text/html+skybridge` → update to `text/html;profile=mcp-app`
- Any test checking for `openai/widgetDomain` → update to check `_meta["ui"]["domain"]`
- Any test checking for `openai/widgetCSP` with `connect_domains` → update to check `_meta["ui"]["csp"]["connectDomains"]`
- Any test checking for `openai/outputTemplate` on **resource** _meta → remove that assertion (key should not be on resources)
- Any test checking `openai/widgetAccessible` or `openai/resultCanProduceWidget` on resources → remove
- Any test checking tool _meta for `openai/widgetAccessible` → update to check `_meta["ui"]["visibility"]` contains `"app"`
- Any test checking tool _meta for `openai/resultCanProduceWidget` → update to check `_meta["ui"]["resourceUri"]` is present

Search for affected test files:
```bash
grep -rn "skybridge\|widgetAccessible\|resultCanProduceWidget\|widgetDomain\|widgetCSP\|openai/visibility\|openai/outputTemplate" tests/
```

---

## Integration Test Instructions

After deployment:
1. Start MCP server locally
2. Use MCP Inspector to call `resources/list` — verify MIME type is `text/html;profile=mcp-app`
3. Use MCP Inspector to call `resources/read` with the widget URI — verify `_meta.ui.domain` is present, `openai/outputTemplate` is NOT present on resource _meta
4. Use MCP Inspector to call `tools/list` — verify tools have `ui.resourceUri` and `ui.visibility`
5. Test in ChatGPT dev mode — verify widget renders (if MIME type is wrong, widget won't load at all)
6. Test Google Calendar connect flow — verify `openExternal` still works (redirect_domains)

---

## Do NOT Change

- Widget HTML/React code — no changes needed
- Tool handlers (handle functions) — no business logic changes
- `structuredContent._meta["openai/outputTemplate"]` in tool **response** payloads — that stays (it's tool response context, not resource metadata)
- Backend API endpoints
- OAuth discovery endpoints
