# Increment: `prioritize_clusters` Tool for Clarity

## Context

**App:** Clarity (Priority Guardian Suite)  
**Existing tools:** `organize_thoughts`, `load_saved_board`, `save_board`  
**This increment:** 4th tool — `prioritize_clusters`

**Increment scope:** MCP tool + widget update only. No database changes. No backend endpoints.

---

## Tool Purpose

Allows user to mark **MAX 3** clusters or subclusters as P1/P2/P3. Updates widget to visually highlight priorities and reorder display.

**Role boundaries (critical):**

| Role | Responsibility |
|------|----------------|
| LLM | Facilitates goal elicitation, prompts user to identify priorities. Process owner. |
| User | Decides WHAT is prioritized. Content owner. |
| Tool | Receives final decisions, updates widget. Execution only. |

---

## Input Schema

```json
{
  "priorities": [
    {
      "cluster_id": "string (cluster or subcluster ID)",
      "rank": "P1" | "P2" | "P3",
      "reason": "blocker" | "goal-aligned" | null  // optional
    }
  ]
}
```

---

## Validation Rules

| Rule | Error Message |
|------|---------------|
| Max 3 priorities | "Maximum 3 priorities allowed. Please select up to 3 clusters or subclusters." |
| Each rank unique | "Each priority rank (P1, P2, P3) can only be assigned once." |
| Valid cluster_id | "Cluster or subcluster not found. Please reference a valid ID from the current board." |
| No board in context | "No board available. Use organize_thoughts first to create a board." |
| Cannot prioritize both parent and child | "Cannot prioritize both a cluster and its subcluster. Choose one." |
| cluster_id must reference cluster or subcluster, not thought_item | "Priorities can only be assigned to clusters or subclusters, not individual thought items." |
| Empty array | Valid — clears all priorities |

---

## Board Identity Rule

Tool operates on the **most recent board** emitted by `organize_thoughts` or `load_saved_board` in the current conversation.

Add to tool description:
> "This tool applies priorities to the most recent board in this conversation."

---

## Priority & Ordering Rules

### Visual Treatment

- **Green highlight + rank badge (P1/P2/P3)** applies ONLY to explicitly prioritized clusters/subclusters
- No visual inheritance up or down
- Thought items never receive priority visual treatment

### Ordering Logic (widget-computed)

**Step 1: Calculate effective rank per cluster**
```
cluster.effective_rank = min(cluster.own_rank, best_subcluster_rank)
```
Where: P1 < P2 < P3 < null

**Step 2: Sort clusters for display**
1. By effective rank (P1 → P2 → P3 → unranked)
2. Within same effective rank: preserve original order

**Step 3: Sort subclusters within each cluster for display**
1. By own rank (P1 → P2 → P3 → unranked)
2. Within same rank: preserve original order

### Example

**User prioritizes:**
- Subcluster A1 = P1
- Cluster B = P2

**Result:**

| Item | Display Position | Green? | Badge |
|------|------------------|--------|-------|
| Cluster A | 1st (effective rank = P1 from A1) | ❌ | — |
| → Subcluster A1 | 1st within A | ✅ | P1 |
| → Subcluster A2 | 2nd within A | ❌ | — |
| Cluster B | 2nd | ✅ | P2 |
| Cluster C | 3rd | ❌ | — |

---

## Output Structure

Tool returns board with priority metadata added. **Order unchanged** — widget handles reordering at render time.

```json
{
  "clusters": [
    {
      "id": "cluster-a",
      "name": "Marketing",
      "priority": null,
      "subclusters": [
        {
          "id": "subcluster-a1",
          "name": "Launch Campaign",
          "priority": { "rank": "P1", "reason": "blocker" },
          "thought_items": [...]
        }
      ],
      "thought_items": [...]
    }
  ]
}
```

**Fields added:**
- `cluster.priority` — explicit priority if assigned, else null
- `subcluster.priority` — explicit priority if assigned, else null

**NOT in output:**
- `effective_rank` — widget computes this at render time (derived state, not persisted)

---

## Widget Requirements

### Visual Changes
- Prioritized clusters/subclusters: green border or background (pick one, not both)
- Rank badge: text label "P1" / "P2" / "P3" next to name
- Non-prioritized items: no visual change

### Display Order
- Widget computes `effective_rank` per cluster: `min(cluster.own_rank, best_subcluster_rank)`
- Widget reorders clusters by effective_rank for display
- Widget reorders subclusters by own rank within parent
- Original data order preserved — ordering is render-only

### Graceful Handling
- Missing `priorities` field → render as before (no priorities)
- Empty `priorities` array → clear all priority visuals

### SDK Compliance
- No browser storage APIs (localStorage, sessionStorage, IndexedDB)
- No `<form>` tags
- System fonts only
- Must handle missing/malformed data gracefully

---

## LLM Facilitation Guidance

**Add to tool description:**

> "Do NOT infer or guess priorities. Only call this tool after the user explicitly names clusters/subclusters and confirms ranking."

**Facilitation sequence (for ChatGPT):**

1. Ask about goals: "What are you trying to achieve right now?"
2. If no goals: Ask about blockers: "What's stuck? What would unblock the most?"
3. Prompt identification: "Based on what you've shared, which clusters feel most important? Pick up to 3."
4. Prompt ranking: "Of those, which is #1?"
5. Only call tool after explicit user decisions

---

## Unit Tests

| # | Test Case | Expected |
|---|-----------|----------|
| 1 | Valid input, 1 priority | Success, board updated |
| 2 | Valid input, 3 priorities (P1, P2, P3) | Success |
| 3 | 4+ priorities | Validation error |
| 4 | Duplicate ranks (two P1s) | Validation error |
| 5 | Invalid cluster_id | Validation error |
| 6 | Empty priorities array | Success, clears priorities |
| 7 | Priority on thought_item ID | Validation error |
| 8 | Priority on both parent cluster and its subcluster | Validation error |
| 9 | Subcluster prioritized → parent cluster order unchanged | Original order preserved |
| 10 | Reason field present | Success, stored |
| 11 | Reason field absent | Success, null |
| 12 | No board in context | Error |

---

## Integration Tests

| # | Test Case | Expected |
|---|-----------|----------|
| 1 | `organize_thoughts` → `prioritize_clusters` → widget renders | Priorities visible, correct order |
| 2 | `prioritize_clusters` without prior board | Error returned |
| 3 | Valid priorities → verify `_meta` contains widget template | Correct _meta |
| 4 | Multiple clusters, mixed priorities → verify display order | P1 cluster first, then P2, then P3, then rest |
| 5 | Subcluster P1, Cluster P2 → verify ordering | Cluster with P1 subcluster first |
| 6 | Clear priorities (empty array) → widget renders | No green, no badges, original order |
| 7 | Priorities applied → verify data order unchanged | Cluster array order matches input |

---

## Files Expected

**MCP Server:**
- Tool registration with input schema
- Validation logic (all rules above)
- Board transformation logic:
  - Add priority metadata to clusters/subclusters
  - Preserve original order (no reordering)

**Widget:**
- Compute `effective_rank` per cluster at render time
- Apply green styling to prioritized items only
- Render rank badges
- Reorder display by effective_rank / own rank (render-only)

---

## Out of Scope

- Database persistence of priorities (use `save_board`)
- Backend endpoints
- Deadline/urgency tagging (separate concept)
- Auto-detection or inference of priorities by LLM
- Multi-board management
- Cross-chat priority merging

---

## Production Readiness Context

**This increment scope:**
- MCP tool + widget only
- Chat-local state (ephemeral unless user calls `save_board`)
- No new OAuth scopes
- No backend changes

**Compliant with:**
- Shared Backend Architecture (MCP stateless, no direct DB access)
- SDK Compliance Checklist (no browser storage, proper error messages, `_meta` template)
- GDPR (no new data collection, priorities ephemeral)