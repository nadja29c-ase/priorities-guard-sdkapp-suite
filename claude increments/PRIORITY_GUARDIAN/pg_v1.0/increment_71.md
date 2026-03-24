Increment 71 — Mobile edit enters fullscreen
Context: On mobile, tapping a priority card to edit stays inline. This is inconsistent with the add form (Inc 67), which correctly enters fullscreen before opening. Edit should behave identically. Desktop is unaffected — the fullscreen transition is mobile-only and guarded at every point.
File: App.tsx only. No other files.

Change 1 — Add two refs alongside the existing enteredFullscreenForAddRef and wasAddingRef refs:
tsconst enteredFullscreenForEditRef = useRef(false)
const wasEditingRef = useRef<string | null>(null)
enteredFullscreenForEditRef must only ever be set in the onStartEdit handler and reset inside the close effect after calling handleMinimizeToInline(). Do not reset it anywhere else.

Change 2 — Wrap onStartEdit in PriorityCardWrapper:
ts// before
onStartEdit={() => setEditingPriorityId(priority.id)}

// after
onStartEdit={() => {
  if (isMobile && displayMode !== 'fullscreen') {
    enteredFullscreenForEditRef.current = true
    handleExpandToFullscreen()
  }
  setEditingPriorityId(priority.id)
}}

Change 3 — Add close effect, placed immediately after the existing Inc 67 add-form effect and before the widgetState persist effect:
ts// On mobile: when edit mode closes, return to inline — only if fullscreen was entered
// specifically for editing. Does not collapse user-initiated fullscreen. (Inc 71)
useEffect(() => {
  if (!isInitialized) return

  // Only act on non-null → null transition
  if (wasEditingRef.current === null || editingPriorityId !== null) {
    wasEditingRef.current = editingPriorityId
    return
  }

  wasEditingRef.current = editingPriorityId

  if (isMobile && enteredFullscreenForEditRef.current) {
    enteredFullscreenForEditRef.current = false
    handleMinimizeToInline()
  }
}, [editingPriorityId, isInitialized, isMobile, handleMinimizeToInline])

Constraints:

This increment handles close only (non-null → null). Switching directly between two edited priorities is not possible — canEdit is false when any editingPriorityId is set, so onStartEdit is replaced with () => {} on all cards while one is being edited.
Desktop: isMobile is false, enteredFullscreenForEditRef is never set, the effect never calls handleMinimizeToInline. Zero impact on desktop.
No card component changes. No i18n changes. No test changes — host display mode transitions are not testable in JSDOM.

Read OPERATIONS_PREDEPLOY.md before committing. Build with npm run build inside widget-react/ and verify output lands in ../widgets/pg-dashboard.html. Verify manually on iPhone after deploy.