Claude Code Briefing: Fix Stale "Saved" Indicator
Problem
Stale widgets incorrectly show "✓ Saved" after a different board version is saved. This is a trust-destroying bug.
Goal
False positives must be impossible. Missing "Saved" is acceptable; false "Saved" is not.
Fix in mcp_server/clarity/widgets/clarity-clusters.html
1. Add renderVersion guard (near top of script, after let isInitialized = false;):
javascriptlet renderVersion = 0;
2. Replace the else branch in render() (the "subsequent renders" section):
Current:
javascript} else {
  // Subsequent renders (isInitialized=true) - only update saved indicator
  if (newHash) {
    computeContentHash(currentClusters).then(ourHash => {
      if (ourHash === newHash) {
        savedBoardHash = newHash;
        savedIndicator.classList.add("visible");
      } else {
        savedBoardHash = null;
        savedIndicator.classList.remove("visible");
      }
    });
  }
  // Don't re-render DOM or change currentClusters
}
Replace with:
javascript} else {
  // Subsequent renders - conservatively verify saved state
  // ALWAYS hide first to prevent false positives
  savedIndicator.classList.remove("visible");
  
  const currentVersion = ++renderVersion;
  
  if (newHash) {
    computeContentHash(currentClusters).then(ourHash => {
      // Guard: ignore if a newer render happened
      if (currentVersion !== renderVersion) return;
      
      if (ourHash === newHash) {
        savedBoardHash = newHash;
        savedIndicator.classList.add("visible");
      } else {
        savedBoardHash = null;
      }
    });
  } else {
    // No hash to verify against - stay hidden
    savedBoardHash = null;
  }
}
Logic
ScenarioResultStale widget, new save happensHash mismatch → hidden ✓Current widget, save succeedsHash matches → visible ✓organize_thoughts (no hash)No hash → hidden (acceptable)Async race (old hash completes late)Version mismatch → ignored ✓
Trade-off (accepted)
If organize_thoughts runs after a save, widgets may lose "✓ Saved" until next save. This is acceptable because:

False negative = UX imperfection
False positive = trust failure

Test

Save board → "✓ Saved" appears
Modify board → new widget, save again
Scroll to old widget → must NOT show "✓ Saved"
New widget → shows "✓ Saved"