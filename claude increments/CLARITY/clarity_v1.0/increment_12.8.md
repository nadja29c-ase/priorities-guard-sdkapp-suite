Claude Code Briefing: Fix "Saved" Disappearing After Save
Problem
After handleSave succeeds, set_globals fires immediately with toolOutput from organize_thoughts (no hash). The else branch clears savedBoardHash and hides indicator.
Fix in mcp_server/clarity/widgets/clarity-clusters.html
1. Add flag after other state variables:
javascriptlet justSaved = false;
2. In handleSave, after success (where indicator is shown):
javascriptif (content?.saved === true && content?.saved_board_hash) {
  savedBoardHash = content.saved_board_hash;
  savedIndicator.classList.add("visible");
  justSaved = true;  // ADD THIS LINE
  console.log(`[${widgetId}] handleSave success`, {
    newHash: savedBoardHash?.slice(0, 8)
  });
}
3. At the start of the else branch in render():
javascript} else {
  // Widget that just saved: skip one set_globals to preserve "Saved"
  if (justSaved) {
    console.log(`[${widgetId}] skipping set_globals (justSaved)`);
    justSaved = false;
    return;
  }

  // Rest of existing else branch unchanged...
  savedIndicator.classList.remove("visible");
  // ...
}