Claude Code Briefing: Freeze Widget Clusters on First Render
Problem
All widgets share window.openai.toolOutput. When new board is saved:

Old widget overwrites its clusters with new data → incorrectly shows "✓ Saved"
New widget gets stale re-render → loses "✓ Saved"

Fix in mcp_server/clarity/widgets/clarity-clusters.html
Replace the entire render() function with:
javascriptlet isInitialized = false;

const render = () => {
  applyTheme();
  const { clusters, savedBoardHash: newHash } = getToolOutput();

  if (!isInitialized) {
    // First render - freeze our clusters
    currentClusters = clusters;
    savedBoardHash = newHash;
    isInitialized = true;
    
    // Render DOM (existing code below)
    rootEl.innerHTML = "";

    if (!clusters.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "No clusters yet. Ask in chat to organize your brain dump into clusters.";
      rootEl.appendChild(empty);
      updateSaveButtonState();
      return;
    }

    const grid = document.createElement("div");
    grid.className = "cluster-grid";

    // ... keep ALL existing cluster rendering code unchanged ...
    
    rootEl.appendChild(grid);
    updateSaveButtonState();
    
  } else {
    // Subsequent renders - only update saved indicator
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
};
Logic
EventisInitializedActionFirst renderfalse → trueStore clusters, render DOMopenai:set_globalstrueCompare hashes only, update indicatorWidget button savetruehandleSave updates savedBoardHash directly
Test

Create board A → Save → "✓ Saved" appears
Add items → organize_thoughts → new widget B appears (no "✓ Saved")
Save widget B → "✓ Saved" appears on B
Scroll up → widget A should NOT show "✓ Saved"
Wait 10 seconds → widget B should KEEP "✓ Saved"