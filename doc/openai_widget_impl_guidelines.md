# OpenAI Apps SDK — Widget Implementation Reference

> Source: developers.openai.com/apps-sdk — fetched March 2026  
> Purpose: Canonical reference for building ChatGPT SDK app widgets (MCP Apps standard + ChatGPT extensions)

---

## 1. Architecture Overview

A ChatGPT App has three components:

- **MCP server** — defines tools, enforces auth, returns data, points tools to UI bundles
- **Widget/UI bundle** — renders inside ChatGPT's iframe, communicates with the host via the MCP Apps bridge (JSON-RPC over `postMessage`)
- **The model** — decides when to call tools and narrates results using `structuredContent`

```
User prompt
   ↓
ChatGPT model ──► MCP tool call ──► Your server ──► Tool response (structuredContent, _meta, content)
   │                                                        │
   └───── renders narration ◄──── widget iframe ◄───────────┘
                              (HTML template + MCP Apps bridge)
```

---

## 2. Foundational Principle: MCP Apps Standard vs ChatGPT Extensions

**Build with the MCP Apps standard by default. Use `window.openai` only for ChatGPT-specific capabilities.**

| Layer | What it is | When to use |
|---|---|---|
| MCP Apps standard | JSON-RPC 2.0 over `postMessage`, `ui/*` methods | Always — portable across all MCP App hosts |
| `window.openai` extensions | ChatGPT-specific APIs | Only when the capability has no MCP standard equivalent |

**Feature-detect before calling any `window.openai` extension. Always degrade gracefully:**

```js
if (window.openai?.requestModal) {
  await window.openai.requestModal({ /* ... */ });
} else {
  // fallback for hosts without this extension
}
```

---

## 3. MCP Apps Host Bridge (`ui/*`)

Standard iframe bridge. Use these by default.

| Method/Notification | Direction | Purpose |
|---|---|---|
| `ui/notifications/tool-input` | host → widget | Latest tool input that invoked the UI |
| `ui/notifications/tool-result` | host → widget | Latest tool result (structuredContent, content, _meta) |
| `tools/call` | widget → host | Call an MCP tool directly from the UI |
| `ui/message` | widget → host | Ask host to post a follow-up message |
| `ui/update-model-context` | widget → host | Update model-visible context from UI state |

**Receiving tool results (standard):**

```js
window.addEventListener("message", (event) => {
  if (event.source !== window.parent) return;
  const message = event.data;
  if (!message || message.jsonrpc !== "2.0") return;
  if (message.method !== "ui/notifications/tool-result") return;
  const data = message.params?.structuredContent;
  // update UI from data
}, { passive: true });
```

---

## 4. `window.openai` — ChatGPT Extensions Reference

ChatGPT provides `window.openai` as an Apps SDK compatibility layer. These are **optional extensions**, not part of the MCP Apps standard.

### 4.1 State & Data

| API | Purpose |
|---|---|
| `window.openai.toolInput` | Arguments supplied when the tool was invoked |
| `window.openai.toolOutput` | Your `structuredContent`. Keep fields concise — the model reads them verbatim |
| `window.openai.toolResponseMetadata` | The `_meta` payload — only the widget sees it, never the model |
| `window.openai.widgetState` | Snapshot of UI state persisted between renders |
| `window.openai.setWidgetState(state)` | Stores a new snapshot synchronously — call after every meaningful UI interaction |

### 4.2 Widget Runtime APIs

| API | Purpose |
|---|---|
| `window.openai.callTool(name, args)` | Invoke another MCP tool from the widget |
| `window.openai.sendFollowUpMessage({ prompt, scrollToBottom })` | Ask ChatGPT to post a message. `scrollToBottom` defaults to `true` |
| `window.openai.uploadFile(file)` | Upload a user-selected file, receive a `fileId` |
| `window.openai.getFileDownloadUrl({ fileId })` | Retrieve a temporary download URL for a file |
| `window.openai.requestDisplayMode(...)` | Request PiP or fullscreen mode (see Section 5) |
| `window.openai.requestModal({ params, template })` | Spawn a host-controlled modal |
| `window.openai.requestClose()` | Ask ChatGPT to close the current widget |
| `window.openai.notifyIntrinsicHeight(...)` | Report dynamic widget height to avoid scroll clipping |
| `window.openai.openExternal({ href, redirectUrl })` | Open a vetted external link in the user's browser |
| `window.openai.setOpenInAppUrl({ href })` | Override the fullscreen "Open in App" target |

### 4.3 Environment Context (read-only)

```
window.openai.theme
window.openai.displayMode
window.openai.maxHeight
window.openai.safeArea
window.openai.view
window.openai.userAgent
window.openai.locale
```

Subscribe to changes via `openai:set_globals` event:

```ts
window.addEventListener("openai:set_globals", (event) => {
  const globals = event.detail?.globals;
  // globals.displayMode, globals.theme, etc.
}, { passive: true });
```

---

## 5. Display Modes

### 5.1 The Three Modes

| Mode | Description | When to use |
|---|---|---|
| **Inline** | Default. Widget appears in conversation flow | All widgets start here |
| **Fullscreen** | Immersive, takes over the viewport. Composer stays overlaid | Rich tasks, multi-step workflows, maps, editors |
| **Picture-in-picture (PiP)** | Persistent floating window. Scrolls with conversation | Ongoing parallel sessions (games, live data, quizzes) |

> **Note:** On mobile, PiP may be coerced to fullscreen by the host.

### 5.2 `requestDisplayMode` — Critical Implementation Rules

`requestDisplayMode` is a **ChatGPT extension** (not MCP Apps standard). It may not be available on all platforms/hosts.

**Official example (from docs):**
```ts
await window.openai?.requestDisplayMode({ mode: "fullscreen" });
// Note: on mobile, PiP may be coerced to fullscreen
```

**Only `fullscreen` is documented as a valid mode in examples.** The docs list "inline, PiP, or fullscreen" as possible negotiation values but only show `fullscreen` in code.

**Production-safe pattern:**
```ts
// Always feature-detect. Never assume the API exists.
// Guard on current displayMode to avoid redundant calls.
// Use optimistic UI update (setDisplayMode) unconditionally.
// Make the host call fire-and-forget — do NOT block UI on it.

const handleExpandToFullscreen = () => {
  // Optimistic update — runs regardless of host API availability
  setDisplayMode('fullscreen')

  // Host call — fire-and-forget, guarded
  try {
    if (
      window.openai?.requestDisplayMode &&
      (window.openai as { displayMode?: string }).displayMode !== 'fullscreen'
    ) {
      window.openai.requestDisplayMode({ mode: 'fullscreen' })
    }
  } catch { /* noop — host may reject or not support */ }

  notifyHeight()
}
```

**Do NOT use `async`/`await` on desktop** — the desktop ChatGPT web app may not implement `requestDisplayMode` or may implement it as a no-op. Awaiting it can cause layout regressions (e.g., overlay panels instead of inline expand).

**Sync host `displayMode` back to widget state on `set_globals`:**
```ts
const handleSetGlobals = () => {
  // Only sync after init to avoid layout flicker
  if (isInitializedRef.current) {
    const hostMode = (window.openai as { displayMode?: string } | undefined)?.displayMode
    if (hostMode === 'fullscreen' || hostMode === 'inline') {
      setDisplayMode(prev => prev !== hostMode ? hostMode : prev)
    }
  }
}
window.addEventListener('openai:set_globals', handleSetGlobals, { passive: true })
```

This is critical on iOS: the native "X" button dismisses fullscreen at the host level without calling widget code. Without this sync, the widget stays in fullscreen layout while the host is already inline.

### 5.3 `set_globals` Event Firing Conditions

`openai:set_globals` fires on **all** of these, not just tool output changes:
- New tool output (new `toolOutput` reference)
- Theme change
- Display mode change (host-initiated)
- Locale change
- Any other global context change

**Always guard `toolOutput` updates with a reference check:**
```ts
if (!currentToolOutput || currentToolOutput === lastToolOutputRef.current) return
// only then process the update
```

---

## 6. MCP Server: Registering the Widget

### 6.1 Register a Component Template

```ts
registerAppResource(
  server,
  "my-widget",
  "ui://widget/my-widget-v1.html",  // URI is the cache key — version it on breaking changes
  {},
  async () => ({
    contents: [{
      uri: "ui://widget/my-widget-v1.html",
      mimeType: "text/html;profile=mcp-app",  // CRITICAL: exact MIME type required
      text: widgetHtml,
      _meta: {
        ui: {
          prefersBorder: true,
          domain: "https://myapp.example.com",  // Required for app submission — unique per app
          csp: {
            connectDomains: ["https://api.myapp.example.com"],
            resourceDomains: ["https://*.oaistatic.com"],
            // frameDomains: only if iframes are core to your UX — triggers stricter review
          },
        },
        "openai/widgetDescription": "Short description — reduces redundant model narration.",
      },
    }],
  })
);
```

> **Widget domain:** `_meta.ui.domain` is required for app submission. It must be unique per app. ChatGPT renders the widget under `<domain>.web-sandbox.oaiusercontent.com`. This also enables the fullscreen punch-out button.

> **URI versioning:** Treat the URI as a cache key. Change it on every breaking update. Never reuse the same URI for different content.

### 6.2 Register a Tool with Widget

```ts
registerAppTool(
  server,
  "my_tool",
  {
    title: "My Tool",
    description: "What this tool does. The model reads this to decide when to call it.",
    inputSchema: { /* zod or JSON schema */ },
    annotations: {
      readOnlyHint: true,      // required — true if tool only reads data
      openWorldHint: false,    // required for write tools — false if bounded target
      destructiveHint: false,  // required for write tools — true if irreversible
    },
    _meta: {
      ui: { resourceUri: "ui://widget/my-widget-v1.html" },
      // ChatGPT compatibility alias (optional):
      // "openai/outputTemplate": "ui://widget/my-widget-v1.html",
      "openai/toolInvocation/invoking": "Loading…",   // max 64 chars
      "openai/toolInvocation/invoked": "Ready.",       // max 64 chars
    },
  },
  async (args) => ({
    structuredContent: { /* concise — model reads this verbatim */ },
    content: [{ type: "text", text: "Narration for the model response." }],
    _meta: { /* large/sensitive data — widget only, never reaches model */ },
  })
);
```

### 6.3 Tool Visibility

Control whether a tool is callable by the model, the widget, or both:

```json
"_meta": {
  "ui": {
    "resourceUri": "ui://widget/my-widget.html",
    "visibility": ["model", "app"]  // default — both can call it
  }
}
```

To make a tool widget-only (hidden from model):
```json
"visibility": ["app"]
```

### 6.4 Response Payload Rules

| Field | Who sees it | Rule |
|---|---|---|
| `structuredContent` | Model + widget | Keep concise. Model reads verbatim. Avoid large arrays or verbose text. |
| `content` | Model + widget | Narration text for the model response. |
| `_meta` | Widget only | Large lookup tables, sensitive data, anything the model shouldn't see. |

**Only `outputTemplate`/`resourceUri` on the tool that initiates the widget should carry the widget URI.** CRUD tools that update widget state should NOT include `outputTemplate` or `resourceUri` — this prevents unnecessary widget remounts.

---

## 7. Widget Initialization Pattern (React)

```ts
// First load
const loadData = useCallback(() => {
  if (isInitializedRef.current) return
  const t = window.openai?.toolOutput
  if (!t) return  // wait for set_globals event

  const { data: parsed, error } = getToolOutput()
  setData(parsed)
  setIsInitialized(true)
  isInitializedRef.current = true
  lastToolOutputRef.current = window.openai?.toolOutput
  notifyHeight()
}, [notifyHeight])

// Subsequent updates
const handleToolOutputUpdate = useCallback(() => {
  if (!isInitializedRef.current) return
  const currentToolOutput = window.openai?.toolOutput
  // Guard: same reference = no new tool result, just theme/displayMode/locale change
  if (!currentToolOutput || currentToolOutput === lastToolOutputRef.current) return
  // ... parse and update
  lastToolOutputRef.current = currentToolOutput
}, [])

// Event listener
useEffect(() => {
  loadData()
  const handleSetGlobals = () => {
    if (isInitializedRef.current) {
      // Sync displayMode from host
      const hostMode = (window.openai as any)?.displayMode
      if (hostMode === 'fullscreen' || hostMode === 'inline') {
        setDisplayMode(prev => prev !== hostMode ? hostMode : prev)
      }
      handleToolOutputUpdate()
    } else {
      loadData()
    }
  }
  window.addEventListener('openai:set_globals', handleSetGlobals, { passive: true })
  return () => window.removeEventListener('openai:set_globals', handleSetGlobals)
}, [loadData, handleToolOutputUpdate])
```

---

## 8. `structuredContent` Design Rules

- **Concise.** The model reads every field verbatim. Oversized payloads degrade model performance and slow rendering.
- **Idempotent.** The model may retry tool calls. Results should be consistent.
- **Widget-only data goes in `_meta`.** Full lookup tables, detailed records, anything that doesn't need to be in the conversation — put in `_meta`.
- **CRUD tools return updated state.** After a write operation, return the updated full state in `structuredContent` so the widget can re-render without a separate fetch.

---

## 9. `notifyIntrinsicHeight`

Call `window.openai?.notifyIntrinsicHeight?.()` whenever widget height changes:
- After initial load
- After data updates
- After form open/close
- After error state changes
- After add/delete operations

Wrap in `requestAnimationFrame` to let the DOM settle first:

```ts
const notifyHeight = useCallback(() => {
  requestAnimationFrame(() => {
    window.openai?.notifyIntrinsicHeight?.()
  })
}, [])
```

---

## 10. `widgetState` — Persisting UI State

`widgetState` survives widget re-renders and OAuth redirects. Write to it after every meaningful interaction.

```ts
// Read on init (lazy initializer in useState)
const [editingId, setEditingId] = useState<string | null>(() => {
  const ws = window.openai?.widgetState as MyWidgetState | undefined
  return ws?.editingId ?? null
})

// Write on change
useEffect(() => {
  window.openai?.setWidgetState?.({ editingId, formOpen })
}, [editingId, formOpen])
```

---

## 11. Tool Annotations (Required)

All tools must include annotations. Omitting them is a validation error.

| Annotation | Type | Required | Meaning |
|---|---|---|---|
| `readOnlyHint` | boolean | Yes | Tool only reads — no create/update/delete/send |
| `openWorldHint` | boolean | Yes (write tools) | Tool can write to arbitrary resources (not just bounded target) |
| `destructiveHint` | boolean | Yes (write tools) | Tool may delete or overwrite with irreversible effects |
| `idempotentHint` | boolean | No | Same args = same result, no extra side effects |

---

## 12. CSP Rules

```json
"_meta": {
  "ui": {
    "csp": {
      "connectDomains": ["https://api.example.com"],
      "resourceDomains": ["https://cdn.example.com"],
      "frameDomains": ["https://embed.example.com"]  // AVOID — triggers strict review
    }
  }
}
```

- `connectDomains` — domains the widget may fetch from (XHR, fetch)
- `resourceDomains` — domains for static assets (images, fonts, scripts, CSS)
- `frameDomains` — optional. Allows iframes. **Strongly discouraged** unless iframes are core. Triggers stricter app review and likely rejection for broad distribution.

---

## 13. Submission Requirements

- `_meta.ui.domain` — required, unique per app
- `mimeType: "text/html;profile=mcp-app"` — exact string, required
- Tool annotations (`readOnlyHint`, `openWorldHint`, `destructiveHint`) — required on all tools
- HTTPS endpoint — required

---

## 14. Common Pitfalls

| Problem | Cause | Fix |
|---|---|---|
| Widget doesn't render | Wrong MIME type, or JS/CSS URL doesn't resolve inside sandbox | Verify `mimeType: "text/html;profile=mcp-app"` and all asset URLs |
| No `ui/*` messages arrive | MIME type wrong — bridge only activates for `text/html;profile=mcp-app` | Fix MIME type |
| CSP/CORS failures | Missing `connectDomains` or `resourceDomains` | Add exact domains to `_meta.ui.csp` |
| Stale bundle loading | URI reused after breaking change | Version the URI on every breaking change |
| State overwrite on display mode change (iOS) | `openai:set_globals` fires with new `toolOutput` reference on mode transitions | Reference-guard `lastToolOutputRef` + sync `displayMode` from `set_globals` |
| Desktop fullscreen regression | `await requestDisplayMode` blocks when API is unsupported | Make host call fire-and-forget, optimistic `setDisplayMode` unconditionally |
| Model narration redundant with widget | Missing `openai/widgetDescription` | Add description to resource `_meta` |
| CRUD remounting widget | `outputTemplate`/`resourceUri` on CRUD tool responses | Only the render/read tool should carry the widget URI |

---

## 15. `useOpenAiGlobal` Helper Pattern

For subscribing to a single `window.openai` global in React:

```ts
export function useOpenAiGlobal<K extends keyof WebplusGlobals>(key: K): WebplusGlobals[K] {
  return useSyncExternalStore(
    (onChange) => {
      const handler = (event: SetGlobalsEvent) => {
        if (event.detail.globals[key] !== undefined) onChange()
      }
      window.addEventListener("openai:set_globals", handler, { passive: true })
      return () => window.removeEventListener("openai:set_globals", handler)
    },
    () => window.openai[key]
  )
}
```
