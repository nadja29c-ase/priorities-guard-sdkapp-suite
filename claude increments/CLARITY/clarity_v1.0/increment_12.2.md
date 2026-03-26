Claude Code Briefing: Fix "✓ Saved" Indicator After Widget Save
Problem
When user clicks Save button in widget, "✓ Saved" appears briefly then disappears. The openai:set_globals event triggers re-render, and getToolOutput() fails to extract saved_board_hash from save_board's response.
Root Cause
getToolOutput() extraction paths don't cover save_board's response structure when called via window.openai.callTool().
Fix in mcp_server/clarity/widgets/clarity-clusters.html
1. Add debug logging temporarily (remove after fix verified):
javascriptconst getToolOutput = () => {
  const t = window.openai?.toolOutput;
  console.log("getToolOutput raw:", JSON.stringify(t, null, 2));  // TEMP DEBUG
  // ... rest of function
};
2. Update getToolOutput() to handle callTool response structure:
The current extraction tries these paths for saved_board_hash:
javascriptif (t.result?.structuredContent?.saved_board_hash) { ... }
else if (t.structuredContent?.saved_board_hash) { ... }
else if (t.saved_board_hash) { ... }
Add the path that callTool() returns (likely direct properties on result):
javascriptconst getToolOutput = () => {
  const t = window.openai?.toolOutput;
  if (!t) return { clusters: [], savedBoardHash: null };

  // Try all known paths for clusters
  let clusters = [];
  if (Array.isArray(t.result?.structuredContent?.clusters)) {
    clusters = t.result.structuredContent.clusters;
  } else if (Array.isArray(t.structuredContent?.clusters)) {
    clusters = t.structuredContent.clusters;
  } else if (Array.isArray(t.clusters)) {
    clusters = t.clusters;
  } else if (Array.isArray(t.data?.clusters)) {
    clusters = t.data.clusters;
  } else if (Array.isArray(t.result?.clusters)) {  // ADD
    clusters = t.result.clusters;
  }

  // Get saved_board_hash - try all paths
  let hash = null;
  hash = hash || t.result?.structuredContent?.saved_board_hash;
  hash = hash || t.structuredContent?.saved_board_hash;
  hash = hash || t.saved_board_hash;
  hash = hash || t.result?.saved_board_hash;  // ADD
  hash = hash || t.data?.saved_board_hash;    // ADD

  return { clusters, savedBoardHash: hash };
};
Also Fix: Modal text (from earlier feedback)
Update modal text to be explicit about overwrite:
html<p class="modal-text">This will replace your previously saved board. Continue?</p>
Test

organize_thoughts → widget renders
Click Save → Confirm
"✓ Saved" should appear AND stay visible
Check console for debug output to verify data structure

Remove After Verified
Delete the console.log debug line once fix is confirmed working.