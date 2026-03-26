Claude Code Briefing: Invalidate Stale "✓ Saved" Indicator
Problem
When user saves a new version of the board, old widgets in the conversation still show "✓ Saved" because their local hash matches their local clusters.
Fix in mcp_server/clarity/widgets/clarity-clusters.html
Update render() function:
javascriptconst render = () => {
  applyTheme();
  const { clusters, savedBoardHash: newHash } = getToolOutput();
  
  // If a different board version was saved, this widget is stale
  if (newHash && savedBoardHash && newHash !== savedBoardHash) {
    savedBoardHash = null;  // Invalidate - our version is no longer saved
  }
  
  // Only update savedBoardHash if we got a new one
  if (newHash) {
    savedBoardHash = newHash;
  }
  
  currentClusters = clusters;
  rootEl.innerHTML = "";
  
  // ... rest of render unchanged
};
Logic
ScenarionewHashsavedBoardHashResultSame board saved"abc""abc"Keep "✓ Saved"Different board saved"xyz""abc"Clear → hide "✓ Saved"No hash in responsenull"abc"Keep existing (organize_thoughts)
Test

Create board → Save → "✓ Saved" appears
Modify board → Save again → new widget shows "✓ Saved"
Scroll up → old widget should NOT show "✓ Saved"