Claude Code Briefing: Sticky Bottom Save Button

Problem:
When board has many clusters, user scrolls down and loses sight of the Save button (currently in header at top). User has to scroll back up to save.
Requirement:
Move Save button to bottom of widget, make it sticky so it's always visible while scrolling. This aligns with OpenAI guidelines: "Primary actions placed at bottom of card."
File to modify:
/mcp_server/clarity/widget-react/src/App.tsx
Changes:

Remove Save button from Header component (or keep it but hide on scroll)
Add sticky bottom Save section after the cluster grid, inside <main>:

jsx{/* Sticky Save button - always visible at bottom */}
<div className="sticky bottom-0 pt-4 pb-2 bg-gray-100 flex justify-end">
  {showSaved && (
    <span className="flex items-center gap-1 text-xs text-success font-medium mr-3">
      <Check className="w-3.5 h-3.5" aria-hidden="true" />
      Saved
    </span>
  )}
  <Button
    ref={saveButtonRef}
    color="primary"
    variant="solid"
    onClick={() => setIsModalOpen(true)}
    disabled={clusters.length === 0}
  >
    Save
  </Button>
</div>

Update Header component to remove Save button (just show title and description)

File to modify:
/mcp_server/clarity/widget-react/src/components/Header.tsx
Remove canSave, showSaved, onSaveClick props and the button JSX.
Acceptance criteria:

Save button visible at bottom of widget at all times
Button stays sticky when scrolling through large boards
"Saved ✓" indicator appears next to button after successful save
Works on mobile and desktop