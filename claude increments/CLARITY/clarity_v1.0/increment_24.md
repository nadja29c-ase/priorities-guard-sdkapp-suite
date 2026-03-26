# Clarity Increment 24: edit_board Tool

## Objective

New MCP tool for board mutations. User intent: "change something on my existing board."

Separates concerns:
- `organize_thoughts` → create fresh board from raw thoughts
- `prioritize_clusters` → set priorities on new board
- `edit_board` → mutate existing board (priorities, renames, deletes)
- `save_board` → persist to database

---

## Problem Being Solved

When user says "make X my P2" on an existing board, `prioritize_clusters` fails because:
1. LLM reconstructs board from memory instead of passing exact JSON
2. Priority fields get dropped
3. Existing priorities lost

`edit_board` provides a dedicated tool for mutations with clear intent signaling.

---

## Phase 1: Test LLM Reliability

This increment tests whether LLM can reliably pass full board data when tool name/description clearly signals "edit existing board."

**If reliable** → keep this simple approach  
**If unreliable** → Phase 2 adds `board_id` + backend storage

---

## Supported Operations

| Operation | Target | Payload | Description |
|-----------|--------|---------|-------------|
| `set_priority` | name OR (item_index + parent_name) | rank | Add/change priority |
| `clear_priority` | name OR (item_index + parent_name) | — | Remove priority from entity |
| `rename_cluster` | name | new_name | Rename cluster |
| `rename_subcluster` | name + parent_name | new_name | Rename subcluster |
| `delete_cluster` | name | — | Remove cluster and all contents |
| `delete_subcluster` | name + parent_name | — | Remove subcluster |
| `delete_thought_item` | item_index + parent_name | — | Remove single thought item |
| `clear_all_priorities` | — | — | Remove all priorities from board |

---

## Input Schema

```python
{
    "board": {
        "type": "array",
        "description": "CRITICAL: Pass the EXACT clusters JSON from the previous tool output. Do NOT reconstruct from memory.",
        "items": { ... }  # Same cluster structure as other tools
    },
    "operation": {
        "type": "string",
        "enum": ["set_priority", "clear_priority", "rename_cluster", "rename_subcluster", "delete_cluster", "delete_subcluster", "delete_thought_item", "clear_all_priorities"]
    },
    "target_name": {
        "type": "string",
        "description": "Cluster or subcluster name to target"
    },
    "parent_name": {
        "type": "string",
        "description": "Parent container name (for subclusters and thought items)"
    },
    "item_index": {
        "type": "integer",
        "description": "0-based index for thought item targeting"
    },
    "rank": {
        "type": "string",
        "enum": ["P1", "P2", "P3"],
        "description": "For set_priority operation"
    },
    "new_name": {
        "type": "string",
        "description": "For rename operations"
    }
}
```

---

## Tool Description

```
PURPOSE: Edit an existing board — change priorities, rename clusters, or delete items.
Use this when user wants to MODIFY their current board, not create a new one.

WHEN TO CALL:
- User says "make X my P2" or "change P1 to Y"
- User says "rename X to Y"
- User says "delete X" or "remove X"
- User says "clear my priorities"

CRITICAL INPUT REQUIREMENT:
You MUST pass the EXACT board JSON from the previous tool output.
- Copy the complete clusters array including ALL priority fields
- Do NOT reconstruct the board from memory
- Do NOT summarize or simplify the structure

DOES NOT AUTO-SAVE: Changes are applied to working board only. User must call save_board to persist.

AFTER TOOL RETURNS: Confirm the change was made. If user wants to save, remind them to ask.
```

---

## Tool Logic

1. Validate operation + required fields for that operation
2. Apply single mutation to passed board
3. Return updated board with widget metadata

**No database interaction.** This tool operates on passed data only.

**Priority rules for `set_priority`:**
- Global uniqueness enforced (one P1, one P2, one P3)
- If rank already assigned elsewhere → clear old holder, set new
- Uses same logic as Increment 23 `_apply_priorities`

---

## Files to Create/Modify

**New file:** `mcp_server/clarity/tools/edit_board.py`
- Tool definition and handler
- Operation-specific mutation functions
- Self-registers at import

**Modify:** `mcp_server/clarity/tools/__init__.py`
- Import new tool module

---

## Validation Rules

| Operation | Required Fields | Validation |
|-----------|-----------------|------------|
| set_priority | target_name OR (item_index + parent_name), rank | Target must exist, rank valid |
| clear_priority | target_name OR (item_index + parent_name) | Target must exist |
| rename_cluster | target_name, new_name | Cluster must exist, new_name not empty |
| rename_subcluster | target_name, parent_name, new_name | Subcluster must exist in parent |
| delete_cluster | target_name | Cluster must exist |
| delete_subcluster | target_name, parent_name | Subcluster must exist in parent |
| delete_thought_item | item_index, parent_name | Index in bounds, parent exists |
| clear_all_priorities | — | — |

---

## Error Messages

```python
ERROR_NO_BOARD = "No board provided. Pass the current board to edit."
ERROR_INVALID_OPERATION = "Invalid operation. Supported: set_priority, clear_priority, rename_cluster, rename_subcluster, delete_cluster, delete_subcluster, delete_thought_item, clear_all_priorities"
ERROR_MISSING_TARGET = "Target not specified. Provide target_name or item_index + parent_name."
ERROR_CLUSTER_NOT_FOUND = "Cluster '{name}' not found."
ERROR_SUBCLUSTER_NOT_FOUND = "Subcluster '{name}' not found in '{parent}'."
ERROR_ITEM_NOT_FOUND = "Item index {index} not found in '{parent}'."
ERROR_MISSING_NEW_NAME = "new_name required for rename operation."
ERROR_MISSING_RANK = "rank required for set_priority operation."
```

---

## Acceptance Criteria

### Functional
- [ ] `set_priority` adds/changes priority, enforces global uniqueness
- [ ] `clear_priority` removes priority from target
- [ ] `rename_cluster` changes cluster name
- [ ] `rename_subcluster` changes subcluster name
- [ ] `delete_cluster` removes cluster and contents
- [ ] `delete_subcluster` removes subcluster and contents
- [ ] `delete_thought_item` removes single item
- [ ] `clear_all_priorities` removes all priorities
- [ ] Tool does NOT auto-save
- [ ] Widget re-renders with updated board

### LLM Behavior (Phase 1 Test)
- [ ] LLM calls `edit_board` for mutation intents (not `prioritize_clusters`)
- [ ] LLM passes complete board with priority fields intact
- [ ] Existing priorities preserved when adding new one

---

## Unit Tests

**File:** `tests/unit/mcp_clarity/test_edit_board.py` (new)

1. `test_set_priority_on_cluster` — basic priority assignment
2. `test_set_priority_preserves_existing` — add P3, P1/P2 intact
3. `test_set_priority_global_uniqueness` — moving P1 clears old holder
4. `test_clear_priority` — removes priority from target
5. `test_rename_cluster` — name changes, content intact
6. `test_rename_subcluster` — name changes within parent
7. `test_delete_cluster` — cluster removed from board
8. `test_delete_subcluster` — subcluster removed, cluster intact
9. `test_delete_thought_item` — item removed, others intact
10. `test_clear_all_priorities` — all priorities removed
11. `test_invalid_operation` — returns error
12. `test_missing_target` — returns error
13. `test_cluster_not_found` — returns error
14. `test_no_board_provided` — returns error

---

## Integration Tests

**File:** `tests/integration/clarity/test_edit_board.py` (new)

1. `test_edit_then_save_persists` — edit_board → save_board → load_saved_board shows changes
2. `test_multiple_edits_accumulate` — edit → edit → edit → all changes present
3. `test_edit_loaded_board` — load_saved_board → edit_board → priorities preserved

---

## Out of Scope

- Auto-save (user must explicitly save)
- Backend board storage (Phase 2 if needed)
- Undo/redo
- Batch operations (one mutation per call)

---

## Success Metric for Phase 1

**Test scenario:**
1. Load saved board with P1 and P3
2. Say "make Energy & burnout my P2"
3. LLM calls `edit_board` with full board including P1/P3 priority fields
4. Widget shows P1, P2, and P3

If this works reliably → Phase 1 complete, no backend storage needed.
If this fails → proceed to Phase 2 (board_id + backend storage).
