# Clarity Increment 25: edit_board New Operations

## Overview

Extend `edit_board` with three new operations:

- `add_thought_item` — append item to cluster/subcluster
- `add_tag` — add tag to cluster/subcluster
- `remove_tag` — remove tag from cluster/subcluster

---

## Problem Context

User says "add dentist appointment to Long-Term Planning" → LLM currently uses `organize_thoughts` which strips priorities. Need `add_thought_item` in `edit_board` for surgical additions that preserve board state.

---

## Design Principle: Tool Separation

| Tool | Purpose | Priorities |
|------|---------|------------|
| `organize_thoughts` | Create/restructure board (LLM clustering) | Stripped (intentional) |
| `edit_board` | Surgical mutations | Preserved |

Merging boards or creating clusters/subclusters requires LLM judgment → `organize_thoughts`.
Adding items, tags, or priorities is deterministic → `edit_board`.

**Invariant:** All `edit_board` operations are non-destructive with respect to existing priorities. These operations must not modify, clear, or reassign any existing priority fields on clusters, subclusters, or items.

---

## Scope Clarifications

**Container types:** Tags can be added to and removed from both clusters and subclusters.

**Ambiguous names:** If `parent_name` or `target_name` matches both a cluster AND a subcluster, return error: `"'{name}' exists as both a cluster and subcluster. Please rename one to make it unique."` (Same behavior as existing `prioritize_clusters` tool.)

---

## New Operations

### `add_thought_item`

**Input:**
```json
{
  "board": [...],
  "operation": "add_thought_item",
  "parent_name": "Long-Term Planning",
  "text": "Make a dentist appointment"
}
```

**Logic:**
1. Find container (cluster or subcluster) by `parent_name`
2. If ambiguous (name exists as both cluster and subcluster) → error
3. Append `text` to container's `thought_items` array (as string, not object)
4. Return updated board (priorities untouched)

**Validation:**
- `parent_name` required
- `text` required, max 500 chars
- Container must exist
- Name must not be ambiguous

---

### `add_tag`

**Input:**
```json
{
  "board": [...],
  "operation": "add_tag",
  "target_name": "Financial Hygiene",
  "tag": "research"
}
```

**Logic:**
1. Find container (cluster or subcluster) by `target_name`
2. If ambiguous → error
3. Add `tag` to container's `tags` array (if not already present)
4. Return updated board (priorities untouched)

**Validation:**
- `target_name` required
- `tag` required, must be in `ALLOWED_TAGS`
- Container must exist
- Name must not be ambiguous
- Max 3 tags per container (reject if already at limit)
- No duplicates (silently skip if tag already present)

---

### `remove_tag`

**Input:**
```json
{
  "board": [...],
  "operation": "remove_tag",
  "target_name": "Financial Hygiene",
  "tag": "research"
}
```

**Logic:**
1. Find container (cluster or subcluster) by `target_name`
2. If ambiguous → error
3. Remove `tag` from container's `tags` array
4. Return updated board (priorities untouched)

**Validation:**
- `target_name` required
- `tag` required
- Container must exist
- Name must not be ambiguous
- Tag must exist on container (error if not present)

---

## Files to Modify

**File:** `mcp_server/clarity/tools/edit_board.py`

1. Add to `VALID_OPERATIONS`:
   ```python
   VALID_OPERATIONS = {
       # existing...
       "add_thought_item",
       "add_tag",
       "remove_tag",
   }
   ```

2. Add constants (schema enum MUST be derived from these, not duplicated):
   ```python
   ALLOWED_TAGS = {"decide", "research", "test", "delegate", "automate", "learn", "align"}
   MAX_TAGS_PER_CONTAINER = 3
   MAX_ITEM_LENGTH = 500
   ```

3. Add to `INPUT_SCHEMA.properties` (derive enum from `ALLOWED_TAGS`):
   ```python
   "text": {
       "type": "string",
       "description": "For add_thought_item: the thought item text to add",
       "maxLength": 500
   },
   "tag": {
       "type": "string",
       "enum": list(ALLOWED_TAGS),  # Derived, not hardcoded
       "description": "For add_tag/remove_tag operations"
   }
   ```

4. Add error messages:
   ```python
   ERROR_MISSING_TEXT = "text required for add_thought_item operation."
   ERROR_MISSING_TAG = "tag required for add_tag/remove_tag operation."
   ERROR_INVALID_TAG = "Invalid tag. Must be: decide, research, test, delegate, automate, learn, align"
   ERROR_TAG_LIMIT = "'{name}' already has 3 tags (maximum). Remove a tag first."
   ERROR_TAG_NOT_FOUND = "Tag '{tag}' not found on '{name}'."
   ERROR_AMBIGUOUS_NAME = "'{name}' exists as both a cluster and subcluster. Please rename one to make it unique."
   ERROR_TEXT_TOO_LONG = "Text exceeds maximum length of 500 characters."
   ```

5. Add to `EditBoardRequest`:
   ```python
   text: Optional[str] = None
   tag: Optional[str] = None
   ```

6. Add ambiguity check helper (reuse from `prioritize_clusters` or import from `board_utils`):
   ```python
   def _check_ambiguous_name(clusters: List[dict], name: str) -> Optional[str]:
       """Return error message if name is ambiguous, None if OK."""
       cluster_names = {c.get("cluster_name") for c in clusters}
       subcluster_names = set()
       for c in clusters:
           for s in c.get("subclusters", []):
               subcluster_names.add(s.get("subcluster_name"))
       
       if name in cluster_names and name in subcluster_names:
           return ERROR_AMBIGUOUS_NAME.format(name=name)
       return None
   ```

7. Add operation handlers:
   ```python
   def _op_add_thought_item(clusters, parent_name, text) -> tuple:
       """Add thought item to container. Returns (updated_clusters, error)."""
   
   def _op_add_tag(clusters, target_name, tag) -> tuple:
       """Add tag to container. Returns (updated_clusters, error)."""
   
   def _op_remove_tag(clusters, target_name, tag) -> tuple:
       """Remove tag from container. Returns (updated_clusters, error)."""
   ```

8. Update `DESCRIPTION` to include new operations:
   ```
   WHEN TO CALL:
   - User says "add X to Y" (use add_thought_item)
   - User says "tag X as research" (use add_tag)
   - User says "remove the research tag from X" (use remove_tag)
   - ... existing triggers ...
   ```

9. Add to `operation_messages`:
   ```python
   "add_thought_item": f"Added '{request.text}' to '{request.parent_name}'.",
   "add_tag": f"Added tag '{request.tag}' to '{request.target_name}'.",
   "remove_tag": f"Removed tag '{request.tag}' from '{request.target_name}'.",
   ```

10. Route new operations in handler:
    ```python
    elif request.operation == "add_thought_item":
        result, error = _op_add_thought_item(clusters_data, request.parent_name, request.text)
    elif request.operation == "add_tag":
        result, error = _op_add_tag(clusters_data, request.target_name, request.tag)
    elif request.operation == "remove_tag":
        result, error = _op_remove_tag(clusters_data, request.target_name, request.tag)
    ```

---

## DO NOT TOUCH

- `organize_thoughts` — stays string-only, no priority support (intentional)
- `prioritize_clusters` — unchanged
- `save_board` — unchanged
- Widget — no changes needed

---

## Acceptance Criteria

### add_thought_item
- [ ] Appends item to cluster's thought_items
- [ ] Appends item to subcluster's thought_items
- [ ] Rejects if parent_name not found
- [ ] Rejects if parent_name is ambiguous (exists as both cluster and subcluster)
- [ ] Rejects if text missing
- [ ] Rejects if text > 500 chars
- [ ] Does NOT modify any existing priority fields

### add_tag
- [ ] Adds tag to cluster
- [ ] Adds tag to subcluster
- [ ] Rejects invalid tag values
- [ ] Rejects if target_name is ambiguous
- [ ] Rejects if already at 3 tags
- [ ] Silently succeeds if tag already present (no duplicate)
- [ ] Does NOT modify any existing priority fields

### remove_tag
- [ ] Removes tag from cluster
- [ ] Removes tag from subcluster
- [ ] Rejects if tag not present
- [ ] Rejects if target_name is ambiguous
- [ ] Does NOT modify any existing priority fields

---

## Unit Tests

**File:** `tests/unit/mcp_clarity/test_edit_board.py` (extend)

### add_thought_item
1. `test_add_thought_item_to_cluster` — adds item to cluster
2. `test_add_thought_item_to_subcluster` — adds item to subcluster
3. `test_add_thought_item_missing_parent` — rejects missing parent_name
4. `test_add_thought_item_missing_text` — rejects missing text
5. `test_add_thought_item_parent_not_found` — rejects invalid parent_name
6. `test_add_thought_item_text_too_long` — rejects > 500 chars
7. `test_add_thought_item_ambiguous_parent` — rejects if name is both cluster and subcluster

### add_tag
8. `test_add_tag_to_cluster` — adds valid tag
9. `test_add_tag_to_subcluster` — adds valid tag
10. `test_add_tag_invalid_value` — rejects invalid tag
11. `test_add_tag_at_limit` — rejects when already 3 tags
12. `test_add_tag_duplicate_silent` — succeeds silently if already present
13. `test_add_tag_ambiguous_target` — rejects if name is both cluster and subcluster

### remove_tag
14. `test_remove_tag_from_cluster` — removes existing tag
15. `test_remove_tag_from_subcluster` — removes existing tag
16. `test_remove_tag_not_found` — rejects if tag not present
17. `test_remove_tag_ambiguous_target` — rejects if name is both cluster and subcluster

---

## Integration Tests

**File:** `tests/integration/clarity/test_edit_board_operations.py` (create)

**Invariant under test:** All `edit_board` operations are non-destructive with respect to existing priorities.

1. `test_add_thought_item_preserves_priorities` — add item to board with P1/P2, verify priorities unchanged
2. `test_add_tag_preserves_priorities` — add tag to board with priorities, verify priorities unchanged
3. `test_remove_tag_preserves_priorities` — remove tag from board with priorities, verify priorities unchanged
4. `test_add_then_save_persists` — add_thought_item → save_board → load_saved_board shows new item
