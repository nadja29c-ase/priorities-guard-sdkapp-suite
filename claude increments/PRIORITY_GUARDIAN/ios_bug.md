# iOS Widget Bug Investigation
**Priority Guardian — App.tsx**
**Status: ✅ RESOLVED — Inc 59 deployed and confirmed fixed on iPhone**

---

## Problem Description

On iPhone (ChatGPT iOS app), after a user performs a CRUD action in inline mode (e.g. toggling a deliverable or goal), the widget state reverted to the original `get_priorities` data. The CRUD update was visually lost.

**Observed behaviour:**
- User toggles a deliverable/goal → widget updates optimistically, tool call succeeds, CRUD response updates widget state ✓
- Widget state reverts to stale `get_priorities` data ✗
- On expand to fullscreen, the revert was especially visible

**Not observed on desktop** (separate unrelated issues exist on desktop — deferred).

**Backend was not involved** — data was correct server-side throughout. Pure client-side state management issue in the widget.

---

## Architecture Context

The widget runs inside a WKWebView sandbox. The host (ChatGPT iOS) communicates with the widget via `window.openai` globals and a custom DOM event `openai:set_globals`. This event fires whenever the host updates any global — including theme, locale, display mode transitions, and new tool output.

Key references in `App.tsx`:
- `lastToolOutputRef` — tracks the last seen `window.openai.toolOutput` reference
- `handleToolOutputUpdate` — fires on every `set_globals` event; guards against re-processing by comparing `currentToolOutput !== lastToolOutputRef.current`
- `updateDataFromResponse` — called after every CRUD tool call; advances `lastToolOutputRef` to the current `window.openai.toolOutput`

---

## Hypothesis 1 — New Object Reference on Display Mode Transition

**Status: ❌ DISPROVEN as primary cause**

### Claim
When the user expands to fullscreen, iOS fires `openai:set_globals` with a new `toolOutput` object reference, bypassing the reference guard.

### Evidence against — confirmed by Inc 58-debug overlay on iPhone
```
#2  toolOutputChanged:true   hostMode:inline
#1  toolOutputChanged:false  hostMode:inline
displayMode: inline
```
Both events fired while still in `inline` mode. The expand button had **not been tapped** when `toolOutputChanged:true` appeared. Display mode transition is not the primary trigger.

May still occur as a secondary trigger (not separately tested) but is not the root cause.

---

## Hypothesis 2 — Host Replaces toolOutput After CRUD

**Status: ✅ CONFIRMED as root cause. Fix verified on iPhone.**

### Claim
The iOS host fires `openai:set_globals` and replaces `window.openai.toolOutput` with a new object reference after `callTool` completes — while still in inline mode. This bypasses the reference guard regardless of display mode.

### Evidence — Inc 58-debug overlay on iPhone
```
#2  toolOutputChanged:true   hostMode:inline
#1  toolOutputChanged:false  hostMode:inline
displayMode: inline
```
- `toolOutputChanged:true` fired while `hostMode` was still `inline`
- Expand button had **not been tapped** at the time of logging
- Happened after toggling a goal and a deliverable (two CRUD actions)
- Case D (outputTemplate triggering host refresh) ruled out: all CRUD tools confirmed to have `widget_uri=None`

### What was proven
- iOS host replaces `window.openai.toolOutput` reference after CRUD
- Happens in inline mode — not display mode related
- Reference guard fails → stale data overwrites CRUD state

### What was NOT proven (and not needed for the fix)
Exact ordering of `set_globals` relative to `updateDataFromResponse`:
- **Case A (race):** `set_globals` fires before `updateDataFromResponse` completes
- **Case B (post-CRUD):** host updates globals after `callTool` resolves, after `updateDataFromResponse` runs
- **Case C (multiple events):** host fires multiple `set_globals` during the CRUD cycle

The exact case did not affect the fix — the invariant was the same regardless.

---

## Hypothesis 3 — displayMode Sync Overwrites State

**Status: ❌ Ruled out**

`setDisplayMode` and `setData` are independent state slices. React batches these updates. Overlay confirmed events happen in inline mode with no display mode change involved.

---

## Root Cause (Confirmed)

The iOS host serialises and deserialises `window.openai.toolOutput` on every `set_globals` event, creating a new object reference each time — including after `callTool` completes. This means:

1. CRUD completes → `updateDataFromResponse` writes CRUD data to state, advances `lastToolOutputRef` to reference A
2. Host fires `set_globals` → creates reference B (new object, stale `get_priorities` data)
3. `handleToolOutputUpdate` runs: `B !== A` → guard fails → stale data overwrites CRUD state

The reference-equality guard (`lastToolOutputRef`) is fundamentally insufficient against a host that creates new object references on every event.

---

## Fix — `hasCrudDataRef` (Inc 59)

**Invariant:** CRUD result always wins over host toolOutput. Once CRUD data has been written, ignore all `set_globals` toolOutput updates until an explicit user refresh.

### Implementation

```ts
const hasCrudDataRef = useRef(false)
```

**Set** in `updateDataFromResponse` — at end of `if (content?.data)` block, after state write:
```ts
hasCrudDataRef.current = true
```

**Guard** in `handleToolOutputUpdate` — immediately after `isInitializedRef` check, before everything else:
```ts
if (hasCrudDataRef.current) return
```

**Reset** in `refreshData` — at the very start, before `setIsRefreshing`:
```ts
hasCrudDataRef.current = false
```

**Reset** in `loadData` — at the very start, before `isInitializedRef` check (handles widget remount):
```ts
hasCrudDataRef.current = false
```

### Why this is correct
All update paths that should continue working (`callTool` → `updateDataFromResponse`, explicit `refreshData`, widget remount via `loadData`) are unaffected. The host's post-CRUD `set_globals` is the only path blocked — and it should be blocked because it carries stale data.

---

## Verification Results (iPhone)

| Test | Result |
|------|--------|
| Toggle goal/deliverable in inline mode → wait 3-5 seconds → check state | ✅ State held, no revert |
| Toggle goal/deliverable → call get_priorities → new widget shows change | ✅ Backend data correct |
| Toggle goal/deliverable → expand to fullscreen | ✅ State held in fullscreen |

**Bug confirmed fixed on iPhone.**

---

## What Was Done

| Increment | Change | Status |
|-----------|--------|--------|
| 56a | `lastToolOutputRef` advanced in `updateDataFromResponse` | Deployed — insufficient alone |
| 56b | `outputTemplate` removed from all CRUD tool responses | Deployed |
| 57 | `handleSetGlobals` syncs `displayMode` from host; `requestDisplayMode` fire-and-forget | Deployed |
| 58-debug | `PG_DEBUG = true` in-widget overlay; logs `set_globals` events with `toolOutputChanged` and `hostDisplayMode` | Deployed — confirmed root cause |
| 59 | `hasCrudDataRef` guard — CRUD state wins over host toolOutput | **Deployed — bug fixed ✅** |
| 59-cleanup | Remove `PG_DEBUG` overlay (`PG_DEBUG = false`) | **Next** |

---

## Key Learnings

1. **Reference equality is not a reliable guard against iOS host bridge behaviour.** The WKWebView host recreates `window.openai.toolOutput` as a new object on every `set_globals` event. Reference comparison will always fail after any host-side update.

2. **The correct invariant is semantic, not structural:** "CRUD data wins over host data" — not "only process when reference changes."

3. **In-widget debug overlays are the only practical debugging tool** for iOS WKWebView widgets. Safari Remote Inspector requires USB + Mac. Chrome DevTools cannot cross the iframe origin boundary. The overlay must be baked into the build with a hardcoded flag.

4. **`position: fixed` inside WKWebView** may overlap interactive elements (blocked the expand button in this investigation). Use `position: relative` for debug overlays in future.

5. **Diagnostic logging before guards** — place debug capture before any early-return guards so all events are visible in the overlay, including blocked ones.

---

## Open Questions (Non-blocking)

- Does the host also create new references on display mode transitions? (Hypothesis 1 may apply as secondary trigger — not tested, not needed)
- Exact ordering of `set_globals` within the CRUD cycle (Cases A/B/C) — irrelevant to fix but would complete the picture
