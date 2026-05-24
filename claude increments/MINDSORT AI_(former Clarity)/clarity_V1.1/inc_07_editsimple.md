Increment Briefing — Edit Board: Text-Based Thought Item Targeting
Context
edit_board requires item_index + parent_name to target individual thought items for set_priority, clear_priority, and delete_thought_item. The LLM never knows item_index — it only knows item text. In production this caused 3 tool calls and a failed priority set: the LLM passed the item text as target_name (not found), then invented a subcluster_name field (schema rejection). This increment adds text-based targeting as a fallback. item_index remains the primary path and takes precedence.
Affected operations: set_priority, clear_priority, delete_thought_item — thought item targeting only. All other operations untouched.
Backward compatibility: Full. item_index + parent_name works as before. Text is an additional path.
Implementation approach: Copy and adjust, never rewrite. Make only the listed changes. Do not restructure, rename, or improve anything not explicitly listed.

File 1: mcp_server/clarity/tools/edit_board.py
Change 1 — Add error constant after the existing error constants block:
pythonERROR_ITEM_TEXT_NOT_FOUND = "Thought item '{text}' not found on board."
ERROR_ITEM_TEXT_AMBIGUOUS = "'{text}' found in multiple containers ({parents}). Provide parent_name to disambiguate."
Change 2 — Add helper function after _check_ambiguous_name and before the # Operation Handlers section:
pythondef _find_thought_item_by_text(
    clusters: List[dict],
    text: str,
    parent_name: Optional[str] = None,
) -> tuple:
    """
    Find a thought item by text (normalized: stripped, lowercased).

    Precedence:
    - If parent_name provided: search that container first.
      If found there, return immediately.
      If not found there, fall through to board-wide search.
    - Board-wide search: collect all matches.
      Single match → return it.
      Multiple matches → return disambiguation error.

    Returns: (item_index, resolved_parent_name, error_message)
      On success: (int, str, None)
      On failure: (None, None, str)
    """
    def normalize(s: str) -> str:
        return s.strip().lower()

    normalized_text = normalize(text)

    def search_container(container: dict, container_name: str) -> Optional[tuple]:
        for i, item in enumerate(container.get("thought_items", [])):
            item_text = item if isinstance(item, str) else item.get("text", "")
            if normalize(item_text) == normalized_text:
                return (i, container_name)
        return None

    # If parent_name provided — search that container first
    if parent_name:
        for cluster in clusters:
            if cluster.get("cluster_name") == parent_name:
                match = search_container(cluster, parent_name)
                if match:
                    return match[0], match[1], None
            for sub in cluster.get("subclusters", []):
                if sub.get("subcluster_name") == parent_name:
                    match = search_container(sub, parent_name)
                    if match:
                        return match[0], match[1], None
        # parent_name provided but item not found in it — fall through to board-wide

    # Board-wide search
    matches = []
    for cluster in clusters:
        match = search_container(cluster, cluster.get("cluster_name", ""))
        if match:
            matches.append(match)
        for sub in cluster.get("subclusters", []):
            match = search_container(sub, sub.get("subcluster_name", ""))
            if match:
                matches.append(match)

    if not matches:
        return None, None, ERROR_ITEM_TEXT_NOT_FOUND.format(text=text)
    if len(matches) == 1:
        return matches[0][0], matches[0][1], None

    parents = ", ".join(f"'{m[1]}'" for m in matches)
    return None, None, ERROR_ITEM_TEXT_AMBIGUOUS.format(text=text, parents=parents)
Change 3 — Update _op_set_priority signature and add text resolution:
Current signature:
pythondef _op_set_priority(clusters: List[dict], target_name: Optional[str],
                     parent_name: Optional[str], item_index: Optional[int],
                     rank: Optional[str]) -> tuple:
New signature:
pythondef _op_set_priority(clusters: List[dict], target_name: Optional[str],
                     parent_name: Optional[str], item_index: Optional[int],
                     rank: Optional[str], text: Optional[str] = None) -> tuple:
After the rank validation block and before if item_index is not None:, add:
python    # Text-based thought item targeting (fallback when item_index not known).
    # item_index takes precedence if both provided.
    if item_index is None and text:
        resolved_index, resolved_parent, error = _find_thought_item_by_text(
            clusters, text, parent_name
        )
        if error:
            return None, error
        item_index = resolved_index
        parent_name = resolved_parent
Change 4 — Update _op_clear_priority signature and add text resolution:
Current signature:
pythondef _op_clear_priority(clusters: List[dict], target_name: Optional[str],
                       parent_name: Optional[str], item_index: Optional[int]) -> tuple:
New signature:
pythondef _op_clear_priority(clusters: List[dict], target_name: Optional[str],
                       parent_name: Optional[str], item_index: Optional[int],
                       text: Optional[str] = None) -> tuple:
After result = copy.deepcopy(clusters) and before if item_index is not None:, add:
python    # Text-based thought item targeting. item_index takes precedence if both provided.
    if item_index is None and text:
        resolved_index, resolved_parent, error = _find_thought_item_by_text(
            clusters, text, parent_name
        )
        if error:
            return None, error
        item_index = resolved_index
        parent_name = resolved_parent
Change 5 — Update _op_delete_thought_item signature and add text resolution:
Current signature:
pythondef _op_delete_thought_item(clusters: List[dict], parent_name: Optional[str],
                            item_index: Optional[int]) -> tuple:
New signature:
pythondef _op_delete_thought_item(clusters: List[dict], parent_name: Optional[str],
                            item_index: Optional[int],
                            text: Optional[str] = None) -> tuple:
Replace the current early-return guard:
python    if item_index is None:
        return None, ERROR_MISSING_TARGET
    if not parent_name:
        return None, ERROR_MISSING_TARGET
With:
python    # Text-based thought item targeting. item_index takes precedence if both provided.
    if item_index is None and text:
        resolved_index, resolved_parent, error = _find_thought_item_by_text(
            clusters, text, parent_name
        )
        if error:
            return None, error
        item_index = resolved_index
        parent_name = resolved_parent

    if item_index is None:
        return None, ERROR_MISSING_TARGET
    if not parent_name:
        return None, ERROR_MISSING_TARGET
Change 6 — Update _dispatch_operation to pass op.text to the three affected operations:
python    if op.operation == "set_priority":
        return _op_set_priority(clusters, op.target_name, op.parent_name, op.item_index, op.rank, op.text)
    elif op.operation == "clear_priority":
        return _op_clear_priority(clusters, op.target_name, op.parent_name, op.item_index, op.text)
    ...
    elif op.operation == "delete_thought_item":
        return _op_delete_thought_item(clusters, op.parent_name, op.item_index, op.text)
All other dispatch cases unchanged.
Change 7 — Update INPUT_SCHEMA text field description in both single mode properties.text and batch mode operations.items.properties.text:
Single mode:
python"text": {
    "type": "string",
    "description": (
        "For add_thought_item: the text to add. "
        "For set_priority, clear_priority, delete_thought_item: "
        "the exact text of the thought item to target — use this instead of item_index. "
        "Matching is case-insensitive and whitespace-tolerant. "
        "If item_index is also provided, item_index takes precedence. "
        "Add parent_name if the same text might appear in multiple clusters."
    ),
    "maxLength": MAX_ITEM_LENGTH
}
Batch mode:
python"text": {
    "type": "string",
    "description": (
        "For add_thought_item: text to add. "
        "For set_priority, clear_priority, delete_thought_item: "
        "exact text of the thought item to target. Case-insensitive. "
        "item_index takes precedence if both provided."
    )
}
```

**Change 8 — Update DESCRIPTION** — add one line to WHEN TO CALL after the `set_priority` bullet:
```
- To target a specific thought item by text (set/clear priority, delete): 
  pass text="exact item text". No need for item_index. 
  Add parent_name if the same text might appear in multiple clusters.

File 2: mcp_server/clarity/tests/test_edit_board_text_targeting.py — new file
Unit tests (pure function, no DB):
python# _find_thought_item_by_text
test_find_item_in_cluster()
# item in cluster thought_items → returns correct (index, cluster_name, None)

test_find_item_in_subcluster()
# item in subcluster thought_items → returns correct (index, subcluster_name, None)

test_find_item_case_insensitive()
# stored "Follow Up On Payments" → query "follow up on payments" → matches

test_find_item_whitespace_tolerant()
# stored "  Follow up  " → query "Follow up" → matches

test_find_item_object_format()
# item stored as {"text": "Follow up", "priority": {...}} → matches on text field

test_find_item_not_found()
# text not on board → returns (None, None, error string containing the text)

test_find_item_ambiguous_no_parent()
# same text in two different containers, no parent_name →
# returns (None, None, error listing both container names)

test_find_item_ambiguous_with_parent()
# same text in two containers, parent_name matches one →
# returns the correct (index, parent_name, None)

test_find_item_parent_not_found_falls_through()
# parent_name provided but doesn't exist on board →
# falls through to board-wide search and finds the item

# _op_set_priority with text targeting
test_set_priority_by_text_success()
# text provided, no item_index → resolves and sets priority correctly

test_set_priority_item_index_wins()
# both text and item_index provided → item_index used, text ignored

test_set_priority_cluster_target_unchanged()
# target_name provided (cluster) → existing path works, text ignored

test_set_priority_text_not_found()
# text not on board → returns error, board unchanged

# _op_clear_priority with text targeting
test_clear_priority_by_text_success()
test_clear_priority_item_index_wins()

# _op_delete_thought_item with text targeting
test_delete_thought_item_by_text_success()
# text provided → item found and deleted

test_delete_thought_item_text_not_found()
# text not on board → returns error, board unchanged

test_delete_thought_item_item_index_wins()
# both provided → item_index used
Integration test (requires DB, one test):
pythontest_edit_board_set_priority_by_text_e2e()
# 1. Seed DB with a board containing a known thought item
# 2. Call handle() with set_priority + text="<known item text>" + rank="P2"
# 3. Assert response is not isError
# 4. Assert persisted board has priority set on the correct item
# 5. Assert other items unchanged

What does NOT change:

All other operation handlers
board_utils.py
All other tool files
SingleOperation and EditBoardRequest Pydantic models — text field already exists on both
Any persistence, auth, or routing logic

Before deploying: Read OPERATIONS_PREDEPLOY.md.