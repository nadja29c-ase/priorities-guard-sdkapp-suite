Quick-Fix Briefing: requestDisplayMode + Two Minor Fixes

Fix 1: requestDisplayMode (SDK Contract Violation)
Problem
handleExpandToFullscreen and handleMinimizeToInline only set local React state. The ChatGPT host is never notified. In production, the iframe container won't resize.
SDK Contract
From OpenAI docs:
tsawait window.openai?.requestDisplayMode({ mode: "fullscreen" })
```
The host controls the actual display mode. The widget requests it, then reads the result from `window.openai.displayMode`.

### What to change in App.tsx

**`handleExpandToFullscreen`** — call the SDK API, then sync local state:
```
const handleExpandToFullscreen = useCallback(async () => {
  await window.openai?.requestDisplayMode?.({ mode: 'fullscreen' })
  setDisplayMode('fullscreen')
  notifyHeight()
}, [notifyHeight])
```

**`handleMinimizeToInline`** — same pattern:
```
const handleMinimizeToInline = useCallback(async () => {
  await window.openai?.requestDisplayMode?.({ mode: 'inline' })
  setDisplayMode('inline')
  notifyHeight()
}, [notifyHeight])
TypeScript: Add requestDisplayMode to the window.openai type declaration in types.ts if not already present:
tsrequestDisplayMode?: (opts: { mode: 'inline' | 'fullscreen' | 'pip' }) => Promise<void>
What NOT to change

Initial state reads window.openai.displayMode on mount — that's correct, keep it
Don't add a listener for displayMode changes — the widget is the only one requesting changes, so setting local state after await is sufficient
Don't remove the local displayMode state — it still drives conditional rendering


Fix 2: Double Submit Guard (One Line)
Problem
handleSubmit in AddPriorityForm.tsx doesn't early-return when isSubmitting is true. Rapid Enter presses can fire before React batches the state update.
What to change in AddPriorityForm.tsx
Add early return as first line of handleSubmit:
tsconst handleSubmit = async () => {
  if (isSubmitting) return  // ← add this line
  if (!priorityType || !validateForm()) return
  // ... rest unchanged
}

Fix 3: Type Narrowing (Type-Only Change)
Problem
PriorityCardWrapperProps types onSavePriority as (priorityId: string, data: Record<string, unknown>) => Promise<void>. The actual handler is already typed. The wrapper loses type safety.
What to change in App.tsx
Replace in PriorityCardWrapperProps:
ts// Before:
onSavePriority: (priorityId: string, data: Record<string, unknown>) => Promise<void>

// After:
onSavePriority: (priorityId: string, data: {
  name?: string
  deadline?: string
  weekly_hour_target?: number
  checkpoint_date?: string
}) => Promise<void>
This matches handleUpdatePriority's signature. No runtime changes.

Acceptance Criteria

 handleExpandToFullscreen calls window.openai.requestDisplayMode({ mode: 'fullscreen' }) before setting local state
 handleMinimizeToInline calls window.openai.requestDisplayMode({ mode: 'inline' }) before setting local state
 requestDisplayMode is typed in the window.openai declaration
 handleSubmit in AddPriorityForm early-returns when isSubmitting is true
 PriorityCardWrapperProps.onSavePriority uses typed update object instead of Record<string, unknown>
 All existing tests pass
 npm run build succeeds with zero errors
