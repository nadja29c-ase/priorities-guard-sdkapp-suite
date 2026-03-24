Increment 59 — hasCrudDataRef Fix
Purpose: Fix the iOS state-overwrite bug. After a CRUD action, the iOS host fires openai:set_globals with a new window.openai.toolOutput object reference, bypassing the reference guard and overwriting CRUD state with stale data.
Root cause confirmed: Inc 58-debug overlay on iPhone showed toolOutputChanged:true with hostMode:inline after CRUD — before any expand was tapped. The host replaces toolOutput reference post-CRUD regardless of display mode. Exact ordering within the CRUD cycle is unknown but irrelevant to the fix.
Scope: App.tsx only. No backend, no migration, no other files.

Changes
1. Add ref near the other refs (isInitializedRef, lastToolOutputRef):
tsconst hasCrudDataRef = useRef(false)
2. Set flag in updateDataFromResponse — at the very end of the if (content?.data) block, after notifyHeight() and the lastToolOutputRef advancement:
tshasCrudDataRef.current = true
Only set when data was actually written — not in the error path.
3. Guard in handleToolOutputUpdate — immediately after the if (!isInitializedRef.current) return check, before everything else including debug logging:
tsif (hasCrudDataRef.current) return
4. Reset in refreshData — at the very start, before setIsRefreshing(true):
tshasCrudDataRef.current = false
5. Reset in loadData — at the start of loadData, before the isInitializedRef.current guard check:
tshasCrudDataRef.current = false
Safety measure for widget remount edge case.

Invariant enforced
CRUD result wins over host toolOutput. Host can fire set_globals with new references as many times as it wants after a CRUD action — the widget ignores it. The flag clears only on explicit user refresh (refreshData) or widget remount (loadData).
All other update paths (callTool → updateDataFromResponse) are unaffected — they bypass handleToolOutputUpdate entirely.

Keep from Inc 58-debug
Keep PG_DEBUG = true and the overlay in this increment. After deploy, verify on iPhone:

Toggle deliverable/goal → overlay shows toolOutputChanged:true firing → state NOT overwritten ✓
Tap refresh → data reloads correctly ✓

Remove PG_DEBUG in a follow-up micro-increment once confirmed.

Pre-deploy
Read OPERATIONS_PREDEPLOY.md. No DB changes, no Alembic check. After pushing, manually trigger redeploy on Render dashboard.