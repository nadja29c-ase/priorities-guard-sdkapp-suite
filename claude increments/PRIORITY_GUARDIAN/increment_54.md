Increment 54 — Optimistic Toggle for Deliverables and Goals
Problem
DeliverableItem and GoalItem set isLoading(true) on toggle and wait for the full MCP→backend round-trip before visually updating the checkbox. The user sees a dimmed, unresponsive checkbox for the entire network duration. This is a pure perception problem — the operation virtually never fails.
Files to change

mcp_server/priority_guardian/widget-react/src/components/DeliverableItem.tsx
mcp_server/priority_guardian/widget-react/src/components/GoalItem.tsx

No other files. No backend changes. No MCP server changes. No App.tsx changes.

What to change in each component
Optimistic state
Add a local optimistic state variable alongside existing state:

DeliverableItem: const [optimisticDone, setOptimisticDone] = useState<boolean | null>(null)
GoalItem: const [optimisticAchieved, setOptimisticAchieved] = useState<boolean | null>(null)

The displayed value is the optimistic state when set, falling back to the prop:

DeliverableItem: const displayedDone = optimisticDone !== null ? optimisticDone : deliverable.done
GoalItem: const displayedAchieved = optimisticAchieved !== null ? optimisticAchieved : goal.achieved

Use displayedDone / displayedAchieved everywhere the component currently reads deliverable.done / goal.achieved for rendering (checkbox visual state, strikethrough text, aria-checked).
Prop-sync reset
Add a useEffect that resets optimistic state when the server-driven prop changes. This handles the case where the parent re-renders with new props before the async success handler runs:
ts// DeliverableItem
useEffect(() => { setOptimisticDone(null) }, [deliverable.done])

// GoalItem
useEffect(() => { setOptimisticAchieved(null) }, [goal.achieved])
Pending guard
Add const isPendingRef = useRef(false) (not state — no re-render needed). In handleToggle:

If isPendingRef.current is true, return early (ignore the tap)
Set isPendingRef.current = true before the async call
Set isPendingRef.current = false in finally

This blocks double-taps while a request is in flight without adding any loading UI.
Revised handleToggle logic for both components

If isPendingRef.current || disabled → return early
Capture current displayed value
Set optimistic state to the flipped value (instant visual update)
Set isPendingRef.current = true
Call onToggle / await it
On success: set optimistic state back to null (prop-sync useEffect will also handle this as a safety net)
On error: revert optimistic state to original captured value, show error message
In finally: set isPendingRef.current = false

Do not set isLoading(true) for the toggle path. The checkbox must never appear dimmed or disabled during a toggle. Remove isLoading from the checkbox disabled prop for toggle — only disabled (parent-level) remains as a guard.
Preserve existing isLoading behavior for rename and delete — those are non-idempotent operations and must retain the loading indicator. Only the toggle gets optimistic treatment.

Error behavior

Revert optimistic state to the pre-tap value
Show existing inline error (3s timeout) — no change to existing error display logic


Build & deploy
After changes: npm run build in widget-react/, verify widgets/pg-dashboard.html is updated. Standard Render deploy.

Acceptance criteria

Tapping a deliverable checkbox updates it visually immediately — no delay, no dimming
Tapping a goal checkbox updates it visually immediately — no delay, no dimming
Double-tapping a checkbox while a request is in flight is ignored
If the network call fails, the checkbox reverts to its pre-tap state and the error message appears
When the server response arrives and props update, optimistic state is cleared cleanly — no flicker, no stuck state
Rename and delete still show loading state as before
No regressions on other interactions (edit, delete, add)
