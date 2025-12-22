# Clarity Increment 22: Thought Item Priority Support

## Objective

Enable users to assign P1/P2/P3 priorities to individual thought items (not just clusters/subclusters). Prioritized items display a visual bar and badge, float up within their container, and contribute to parent container ordering.

---

## Context

**Current state:**
- Clusters and subclusters support `priority: { rank: "P1" | "P2" | "P3" }`
- Thought items are plain strings: `thought_items: string[]`
- Priority visual: neutral `border-l-strong` bar + `<Badge color="secondary">` badge
- Global uniqueness: only ONE P1, ONE P2, ONE P3 allowed across entire board

**After this increment:**
- Thought items can also receive priorities
- Same global uniqueness rule applies (one P1 total, whether on cluster, subcluster, or item)
- Prioritized items float up within their container
- Container inherits priority for board-level ordering (but NOT visual treatment)

---

## Tool Responsibility Clarification

**IMPORTANT:** `prioritize_clusters` is the **single authority** for all priority mutations across the board.

It handles:
- Cluster priorities
- Subcluster priorities  
- Thought item priorities (new in this increment)

**No other tool may mutate priority state.** This is intentional to maintain a single source of truth and prevent fragmented responsibility across future increments.

**CRITICAL**DO NOT TOUCH TOOL DESCRIPTIONS OR STRUCTUREDCONTENT: IF CHANGES ARE NECESSARY NOTE THEM AS A COMMENT ABOVE THE TOOL DESCRIPTION.

---

## Business Rules

### Priority Assignment
1. P1, P2, P3 remain **globally unique** across entire board
2. Priority can be assigned to cluster OR subcluster OR thought item (not multiple)
3. User assigns via conversation: "Make 'Email boss' my P1"

### Visual Treatment
1. **Only the explicitly prioritized entity** gets the colored bar + badge
2. Parent containers do NOT inherit visual treatment
3. Use existing tokens: `border-l-strong` for bar, `<Badge color="secondary">` for badge

### Ordering Logic (recursive bubble-up)
1. Thought items sort within their container (P1 → P2 → P3 → unranked)
2. Subclusters sort within their cluster (by own or best child priority)
3. Clusters sort on board (by own or best descendant priority)
4. **Effective rank** = best priority among self and all descendants

### Clearing Priority
When a priority is cleared from a thought item:
- Object structure remains: `{ text: "...", priority: undefined }`
- Object does NOT collapse back to string
- Widget renders as unprioritized (default `border-l-2 border-default`)

---

## Data Structure

### Thought Item Type (Option B: Accept Both Formats)

```typescript
// types.ts
type ThoughtItemInput = string | { text: string; priority?: { rank: Rank } }

interface ThoughtItem {
  text: string
  priority?: { rank: Rank }
}
```

- `organize_thoughts` continues outputting `string[]` (no change)
- `prioritize_clusters` converts targeted item to object format
- Widget normalizes all formats to `ThoughtItem` objects

### Priority Target in prioritize_clusters

```typescript
// Target can be cluster, subcluster, or thought item
interface PriorityInput {
  name?: string           // cluster_name or subcluster_name (for cluster/subcluster targeting)
  item_index?: number     // 0-based position in parent's thought_items array (for item targeting)
  parent_name?: string    // required when targeting item (cluster or subcluster name)
  rank: "P1" | "P2" | "P3"
  reason?: "blocker" | "goal-aligned"
}
```

**Targeting rules:**
- Cluster: `{ name: "Work", rank: "P1" }`
- Subcluster: `{ name: "Urgent Tasks", rank: "P2" }`
- Thought item: `{ item_index: 0, parent_name: "Work", rank: "P3" }`

---

## Global Uniqueness Validation

### Enforcement Specification

The `_validate_priorities()` function must scan **all entity types** to enforce global uniqueness.

**Algorithm:**

```python
def _validate_priorities(priorities, clusters_data):
    """
    Validate priority assignments across all entity types.
    
    Steps:
    1. Build global rank -> owner map from existing board state
    2. Check incoming priorities don't conflict with existing assignments
    3. Check incoming priorities don't duplicate ranks among themselves
    """
    
    # Step 1: Scan existing board for current priority assignments
    existing_ranks = {}  # rank -> { type: "cluster"|"subcluster"|"item", name: str }
    
    for cluster in clusters_data:
        # Check cluster priority
        if cluster.get("priority", {}).get("rank"):
            rank = cluster["priority"]["rank"]
            existing_ranks[rank] = {"type": "cluster", "name": cluster["cluster_name"]}
        
        # Check subcluster priorities
        for sub in cluster.get("subclusters", []):
            if sub.get("priority", {}).get("rank"):
                rank = sub["priority"]["rank"]
                existing_ranks[rank] = {"type": "subcluster", "name": sub["subcluster_name"]}
            
            # Check thought items in subcluster
            for idx, item in enumerate(sub.get("thought_items", [])):
                if isinstance(item, dict) and item.get("priority", {}).get("rank"):
                    rank = item["priority"]["rank"]
                    existing_ranks[rank] = {"type": "item", "parent": sub["subcluster_name"], "index": idx}
        
        # Check thought items directly in cluster
        for idx, item in enumerate(cluster.get("thought_items", [])):
            if isinstance(item, dict) and item.get("priority", {}).get("rank"):
                rank = item["priority"]["rank"]
                existing_ranks[rank] = {"type": "item", "parent": cluster["cluster_name"], "index": idx}
    
    # Step 2: Validate incoming priorities
    incoming_ranks = set()
    for p in priorities:
        # Check for duplicate in incoming set
        if p.rank in incoming_ranks:
            return f"Duplicate rank {p.rank} in request"
        incoming_ranks.add(p.rank)
        
        # Check if rank already used elsewhere (and not being reassigned to same entity)
        if p.rank in existing_ranks:
            existing = existing_ranks[p.rank]
            is_same_target = _is_same_target(p, existing)
            if not is_same_target:
                return f"{p.rank} is already assigned to {existing['name'] or 'an item'}. Clear it first or choose a different rank."
    
    return None  # Valid
```

**Error messages:**
- `"P1 is already assigned to 'Work' cluster. Clear it first or choose a different rank."`
- `"P2 is already assigned to an item in 'Urgent Tasks'. Clear it first or choose a different rank."`
- `"Duplicate rank P1 in request."`

---

## Files to Modify

### 1. Widget Types
**File:** `mcp_server/clarity/widget-react/src/types.ts`

- Add `ThoughtItem` interface
- Add `ThoughtItemInput` type union
- Update `Subcluster.thought_items` type to `ThoughtItemInput[]`
- Update `Cluster.thought_items` type to `ThoughtItemInput[]`

### 2. Widget Utilities
**File:** `mcp_server/clarity/widget-react/src/utils.ts`

- Add `normalizeThoughtItem(item: ThoughtItemInput): ThoughtItem`
- Add `sortThoughtItemsByPriority(items: ThoughtItem[]): ThoughtItem[]`
- Update `getEffectiveRank()` to scan normalized thought items

### 3. ThoughtItem Component
**File:** `mcp_server/clarity/widget-react/src/components/ThoughtItem.tsx`

- Accept `ThoughtItem` object (not just string)
- Render priority bar (`border-l-4 border-l-strong`) when prioritized
- Render `<PriorityBadge>` when prioritized
- Keep unprioritized style: `border-l-2 border-default`

### 4. ClusterCard Component
**File:** `mcp_server/clarity/widget-react/src/components/ClusterCard.tsx`

- Normalize thought items before rendering
- Sort thought items by priority
- Pass full `ThoughtItem` object to component

### 5. SubclusterCard Component
**File:** `mcp_server/clarity/widget-react/src/components/SubclusterCard.tsx`

- Same changes as ClusterCard

### 6. MCP Tool Schema & Logic
**File:** `mcp_server/clarity/tools/prioritize_clusters.py`

- Update module docstring to clarify single-authority role
- Update `INPUT_SCHEMA` to support `item_index` + `parent_name`
- Update `PriorityInput` pydantic model with new fields
- Add `_scan_existing_priorities()` helper for global scan
- Update `_validate_priorities()` to enforce global uniqueness across all types
- Update `_apply_priorities()` to convert string items to objects when prioritized

---

## Acceptance Criteria

### Functional
- [ ] User can assign P1/P2/P3 to a thought item via conversation
- [ ] Prioritized thought item shows `border-l-strong` bar + gray badge
- [ ] Prioritized items float to top within their container
- [ ] Container with prioritized item floats up on board (ordering inheritance)
- [ ] Container does NOT get visual treatment from child priority
- [ ] Global uniqueness enforced across clusters, subclusters, AND items
- [ ] Clear error message when rank already assigned elsewhere
- [ ] `organize_thoughts` output unchanged (still strings)
- [ ] Clearing priority leaves object structure intact (no collapse to string)

### Visual
- [ ] Priority bar: `border-l-4 border-l-strong` (neutral, not colored)
- [ ] Priority badge: `<Badge color="secondary" variant="solid" size="sm">`
- [ ] Unprioritized items: `border-l-2 border-default` (current behavior)

### Edge Cases
- [ ] Out-of-bounds `item_index` returns clear error
- [ ] Invalid `parent_name` returns clear error
- [ ] Mixed formats (string + object) in same cluster render correctly
- [ ] Re-prioritizing same item with different rank works
- [ ] Clearing all priorities resets ordering to original

---

## Unit Tests

**File:** `mcp_server/clarity/widget-react/src/test/ThoughtItem.test.tsx` (new)

1. Renders string item correctly (after normalization)
2. Renders object item without priority correctly  
3. Renders object item with priority (bar + badge)
4. Priority badge shows correct rank

**File:** `mcp_server/clarity/widget-react/src/test/utils.test.ts` (extend)

1. `normalizeThoughtItem` handles string input
2. `normalizeThoughtItem` handles object input with priority
3. `normalizeThoughtItem` handles object input without priority
4. `sortThoughtItemsByPriority` orders P1 → P2 → P3 → unranked
5. `getEffectiveRank` includes thought item priorities in calculation

**File:** `tests/unit/mcp_clarity/test_prioritize_clusters.py` (extend)

1. Prioritize thought item by `item_index` + `parent_name`
2. Reject when `item_index` out of bounds
3. Reject when `parent_name` doesn't exist
4. Reject duplicate rank when cluster already has P1
5. Reject duplicate rank when another item already has P1
6. String items converted to objects after prioritization
7. Re-prioritizing same item with new rank succeeds
8. Clearing priority (empty priorities array) preserves object structure

---

## Integration Tests

**File:** `tests/integration/mcp_clarity/test_prioritize_thought_items.py` (new)

1. Full flow: organize_thoughts → prioritize item → widget renders correctly
2. Priority on item bubbles up for cluster ordering
3. Clearing item priority restores default display (but keeps object format)
4. Mixed priorities (cluster P1, item P2) render and order correctly
5. Global uniqueness enforced across entity types

---

## Non-Goals (Explicit)

- **No persistence guarantee across reloads** — priority is board-state only unless user saves
- **No UI-based priority assignment** — conversation only for this increment
- **No drag-and-drop reordering**
- **No database schema changes**
- **No priority reason display on thought items** (deferred)

---

## Backward Compatibility

- Boards saved before this increment contain `thought_items: string[]`
- Widget normalization handles both formats transparently
- No migration required — mixed boards work automatically

---

## Reference

**Existing priority colors (DO NOT CHANGE):**
- Bar: `border-l-strong` (neutral)
- Badge: `<Badge color="secondary">` (gray)

**Sorting logic reference:** `utils.ts` → `rankToNumber()`, `getEffectiveRank()`

**Widget output contract:** `structuredContent.clusters[]` in tool response