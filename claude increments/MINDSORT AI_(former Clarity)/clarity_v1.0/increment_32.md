# Increment: Widget UX Fixes (Height, State, Types)

**Date:** 2025-12-25  
**Component:** Clarity Widget (React)  
**Priority:** High (user experience)

---

## Context

Testing revealed several UX issues caused by incomplete SDK integration:
1. iOS scroll clipping — widget height not reported to host
2. State lost on re-render — scroll position, user interactions reset
3. Invalid CSS token — `border-danger` not a valid SDK utility
4. Incomplete TypeScript types — prevents using additional SDK APIs

---

## Objectives

1. Report dynamic widget height to ChatGPT host via `notifyIntrinsicHeight`
2. Persist widget state between renders via `setWidgetState` / `widgetState`
3. Fix invalid `border-danger` token
4. Extend `window.openai` types for full API coverage

---

## Requirements

### 1. Intrinsic Height Reporting

**Problem:** Widget starts short (loading state), then grows (clusters loaded). Host iframe may not resize correctly → scroll clipping on iOS.

**Solution:** Call `window.openai.notifyIntrinsicHeight()` after content changes.

**Implementation notes:**
- Call after `setIsInitialized(true)` when clusters load
- Call after any content that changes widget height
- Use `requestAnimationFrame` or `setTimeout(..., 0)` to ensure DOM has rendered
- No height argument needed — host computes iframe size automatically
- Check if API exists before calling: `window.openai?.notifyIntrinsicHeight?.()`

**When to call:**
- After initial clusters load (in `loadClusters` or effect after `isInitialized` becomes true)
- After error state appears/disappears (height changes)
- After "Saved" feedback appears (minor, optional)

### 2. Widget State Persistence

**Problem:** If user scrolls down, then types in main chat composer, widget re-renders with fresh state. Scroll position lost.

**Solution:** Use `setWidgetState` to persist meaningful UI state; read from `widgetState` on mount.

**What to persist:**
- Nothing complex needed for Clarity's current UI
- Future: expanded/collapsed cluster state, scroll position
- For now: just wire up the infrastructure so it's ready

**Implementation notes:**
- Read `window.openai.widgetState` on mount to restore state
- Call `window.openai.setWidgetState(state)` after meaningful interactions
- Keep state payload small and serializable
- State is scoped to this widget instance only

**Minimal implementation for now:**
- Add `widgetState` to types
- Read it on mount (log it, prepare for future use)
- Don't persist anything yet — just infrastructure

### 3. Fix Invalid Border Token

**File:** `App.tsx`

**Current (invalid):**
```tsx
<div className="mb-4 p-3 text-sm text-danger bg-surface rounded-lg border border-danger">
```

**Fixed (valid SDK token):**
```tsx
<div className="mb-4 p-3 text-sm text-danger bg-surface rounded-lg border border-danger-outline">
```

**Reason:** `border-danger` is not a valid SDK utility. SDK provides `border-danger-outline` (red-500) and `border-danger-surface` (red-a25/a50).

### 4. Extend TypeScript Types

**File:** `types.ts`

Add missing `window.openai` API types:

```typescript
declare global {
  interface Window {
    openai?: {
      // Existing
      theme?: 'light' | 'dark'
      toolOutput?: { /* existing */ }
      callTool?: <T = unknown>(name: string, args: Record<string, unknown>) => Promise<{
        structuredContent?: T
        result?: { structuredContent?: T }
      }>
      
      // Add these
      locale?: string
      userAgent?: string
      displayMode?: 'inline' | 'pip' | 'fullscreen'
      maxHeight?: number
      safeArea?: { top: number; bottom: number; left: number; right: number }
      view?: 'default' | 'launcher'
      
      // Widget state
      widgetState?: Record<string, unknown>
      setWidgetState?: (state: Record<string, unknown>) => void
      
      // Layout & height
      notifyIntrinsicHeight?: (height?: number) => void
      requestDisplayMode?: (options: { mode: 'inline' | 'pip' | 'fullscreen' }) => Promise<void>
      requestClose?: () => void
      requestModal?: (options: unknown) => Promise<unknown>
      
      // User actions
      sendFollowUpMessage?: (options: { prompt: string }) => Promise<void>
      uploadFile?: (file: File) => Promise<{ fileId: string }>
      getFileDownloadUrl?: (options: { fileId: string }) => Promise<{ downloadUrl: string }>
      openExternal?: (options: { href: string }) => void
    }
  }
}
```

---

## Implementation Order

1. **Types first** — enables TypeScript to validate API usage
2. **Border fix** — one-line change
3. **notifyIntrinsicHeight** — add calls after height-changing events
4. **widgetState infrastructure** — wire up but don't persist yet

---

## Unit Tests

### Height notification
- Mock `window.openai.notifyIntrinsicHeight`
- Render App with clusters
- Verify `notifyIntrinsicHeight` was called after render

### Border token
- Render App with `saveError` state set
- Verify error div uses `border-danger-outline` class

### Types
- No runtime test needed — TypeScript compilation validates

---

## Integration Tests

### Height reporting flow
- Load widget with clusters from `toolOutput`
- Verify `notifyIntrinsicHeight` called
- Simulate error state appearing
- Verify `notifyIntrinsicHeight` called again

---

## Validation Criteria

- [ ] `notifyIntrinsicHeight` called after clusters load
- [ ] `notifyIntrinsicHeight` called after error state changes
- [ ] Error banner uses `border-danger-outline` (not `border-danger`)
- [ ] No TypeScript errors with extended types
- [ ] `widgetState` type available for future use
- [ ] Widget still renders correctly in light and dark mode
- [ ] All existing tests pass

---

## Out of Scope

- Actually persisting scroll position (future increment)
- Persisting expanded/collapsed cluster state (future increment)
- Locale handling / i18n (future increment)
- Modal removal (separate increment: INCREMENT_REMOVE_SAVE_MODAL.md)

---

## Reference

- SDK docs: "Build a Custom UX" — `notifyIntrinsicHeight`, `setWidgetState`
- SDK source: `node_modules/@openai/apps-sdk-ui/dist/es/styles/tailwind-utilities.css`
- Current App.tsx: `mcp_server/clarity/widget-react/src/App.tsx`
- Current types.ts: `mcp_server/clarity/widget-react/src/types.ts`