Increment 61 — Delete Confirmation Focus Trap (revised)
File: mcp_server/priority_guardian/widget-react/src/components/DeleteConfirmation.tsx
No other files change. No backend. No migration.

Context
DeleteConfirmation renders with role="dialog" and aria-modal="true" — the correct ARIA contract for a modal. However, Tab and Shift+Tab can currently escape the dialog into background content, breaking the contract. The component is conditionally mounted by its parent (unmounted when closed), so lifecycle cleanup handles deactivation correctly — no isOpen guard is needed.

What to implement
Add a focus trap useEffect. On keydown while the modal is open:

Query all focusable elements inside modalRef using: button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])
Filter to only visible elements: el.offsetParent !== null
Guard: if (!modalRef.current) return and if (focusable.length === 0) return
Attach listener to document, but only act when modalRef.current.contains(document.activeElement) — this keeps it consistent with the existing ESC listener pattern and prevents the trap firing when modal doesn't have focus
If Tab on last element → focus first, preventDefault()
If Shift+Tab on first element → focus last, preventDefault()
Clean up listener on unmount

The existing ESC useEffect and auto-focus useEffect remain unchanged.

Constraints

No new dependencies
No prop changes
No other files
No backend


Pre-deploy
No DB changes. No backend changes. No migration. No OAuth changes. Standard widget build + deploy:

npm run build in widget-react/
Verify widgets/pg-dashboard.html is updated
Deploy to Render (manual trigger)


Unit tests (DeleteConfirmation.test.tsx — create if not exists)

Tab on last focusable element wraps focus to first and calls preventDefault
Shift+Tab on first focusable element wraps focus to last and calls preventDefault
Tab on a middle element does not call preventDefault
When isDeleting=true (both buttons disabled): no focusable elements matched, no error thrown
ESC still calls onCancel (existing behaviour unchanged)
Cancel button receives focus on mount (existing behaviour unchanged)
