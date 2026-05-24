# edit_board: Add Batch Mode

## Context

Increment 25 is implemented. `edit_board` currently handles one operation per call. Add batch mode to reduce tool calls and LLM state-passing failures.

User says: *"Rename Work to Career and make it my P1"*
- Current: 2 tool calls, 2 board pass-throughs
- With batch: 1 tool call, 1 board pass-through

---

## Schema Change

Add `operations` array to `INPUT_SCHEMA.properties`:

```python
"operations": {
    "type": "array",
    "description": "Batch mode: multiple operations applied in order. Use EITHER 'operation' (single) OR 'operations' (batch), not both.",
    "items": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": list(VALID_OPERATIONS)  # Derive from constant
            },
            "target_name": {"type": "string"},
            "parent_name": {"type": "string"},
            "item_index": {"type": "integer"},
            "rank": {"type": "string", "enum": ["P1", "P2", "P3"]},
            "new_name": {"type": "string"},
            "text": {"type": "string"},
            "tag": {"type": "string", "enum": sorted(ALLOWED_TAGS)}
        },
        "required": ["operation"]
    }
}
```

Update `required` — board is always required, but operation vs operations is conditional (validated in handler).

---

## Pydantic Model Change

Add to `EditBoardRequest`:

```python
class SingleOperation(BaseModel):
    """One edit operation."""
    operation: str
    target_name: Optional[str] = None
    parent_name: Optional[str] = None
    item_index: Optional[int] = None
    rank: Optional[str] = None
    new_name: Optional[str] = None
    text: Optional[str] = None
    tag: Optional[str] = None


class EditBoardRequest(BaseModel):
    """Request structure — single or batch mode."""
    board: List[ClusterInput]
    # Single mode
    operation: Optional[str] = None
    target_name: Optional[str] = None
    parent_name: Optional[str] = None
    item_index: Optional[int] = None
    rank: Optional[str] = None
    new_name: Optional[str] = None
    text: Optional[str] = None
    tag: Optional[str] = None
    # Batch mode
    operations: Optional[List[SingleOperation]] = None
```

---

## Error Messages

Add:

```python
ERROR_MIXED_MODE = "Use 'operation' (single) OR 'operations' (batch), not both."
ERROR_NO_OPERATION = "Provide 'operation' (single) or 'operations' (batch)."
ERROR_EMPTY_BATCH = "Batch operations list cannot be empty."
```

---

## Handler Logic Change

Replace single-dispatch with loop:

```python
async def handle(user_id, correlation_id, arguments):
    # ... existing validation ...
    
    # CRITICAL: Check empty batch FIRST (before mode detection)
    if request.operations is not None and len(request.operations) == 0:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=ERROR_EMPTY_BATCH)],
            isError=True,
        )
    
    # Determine mode
    if request.operations and request.operation:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=ERROR_MIXED_MODE)],
            isError=True,
        )
    
    if not request.operations and not request.operation:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=ERROR_NO_OPERATION)],
            isError=True,
        )
    
    # Build ops list
    if request.operations:
        ops = request.operations
    else:
        # Wrap single op
        ops = [SingleOperation(
            operation=request.operation,
            target_name=request.target_name,
            parent_name=request.parent_name,
            item_index=request.item_index,
            rank=request.rank,
            new_name=request.new_name,
            text=request.text,
            tag=request.tag,
        )]
    
    # Execute in order — fail fast
    clusters_data = [c.model_dump() for c in request.board]
    completed = []
    
    for i, op in enumerate(ops):
        result, error = _dispatch_operation(clusters_data, op)
        if error:
            # Report which operation failed (1-indexed for user clarity)
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text=f"Operation {i+1} ({op.operation}) failed: {error}"
                )],
                isError=True,
            )
        clusters_data = result
        completed.append(op.operation)
    
    # Success
    enriched = enrich_clusters(clusters_data)
    
    if len(completed) == 1:
        message = operation_messages.get(completed[0], "Edit complete.")
    else:
        message = f"Completed {len(completed)} edits: {', '.join(completed)}."
    
    # ... return success response with guidance ...
```

Extract dispatch logic to helper:

```python
def _dispatch_operation(clusters: List[dict], op: SingleOperation) -> tuple:
    """Route operation to handler. Returns (updated_clusters, error)."""
    if op.operation == "set_priority":
        return _op_set_priority(clusters, op.target_name, op.parent_name, op.item_index, op.rank)
    elif op.operation == "clear_priority":
        return _op_clear_priority(clusters, op.target_name, op.parent_name, op.item_index)
    elif op.operation == "add_thought_item":
        return _op_add_thought_item(clusters, op.parent_name, op.text)
    elif op.operation == "add_tag":
        return _op_add_tag(clusters, op.target_name, op.tag)
    elif op.operation == "remove_tag":
        return _op_remove_tag(clusters, op.target_name, op.tag)
    elif op.operation == "rename_cluster":
        return _op_rename_cluster(clusters, op.target_name, op.new_name)
    elif op.operation == "rename_subcluster":
        return _op_rename_subcluster(clusters, op.target_name, op.parent_name, op.new_name)
    elif op.operation == "delete_cluster":
        return _op_delete_cluster(clusters, op.target_name)
    elif op.operation == "delete_subcluster":
        return _op_delete_subcluster(clusters, op.target_name, op.parent_name)
    elif op.operation == "delete_thought_item":
        return _op_delete_thought_item(clusters, op.parent_name, op.item_index)
    elif op.operation == "clear_all_priorities":
        return _op_clear_all_priorities(clusters)
    else:
        return None, ERROR_INVALID_OPERATION
```

---

## DESCRIPTION Update

Add to WHEN TO CALL:

```
- User requests multiple changes at once (use operations array)
  Example: "Rename X to Y and make it P1" → batch with rename_cluster + set_priority
```

---

## Failure Semantics

- First error stops execution
- No partial results applied
- Error message indicates which operation failed (1-indexed for user clarity)
- User fixes and retries entire batch

---

## Unit Tests

Add to `tests/unit/mcp_clarity/test_edit_board.py`:

1. `test_batch_two_operations` — rename + set_priority in one call
2. `test_batch_first_fails` — first op fails, nothing applied
3. `test_batch_second_fails` — second op fails, returns error with index
4. `test_batch_empty_array` — empty operations array returns ERROR_EMPTY_BATCH
5. `test_mixed_mode_rejected` — both operation and operations provided → ERROR_MIXED_MODE
6. `test_single_op_still_works` — existing single-op calls unchanged

---

## DO NOT CHANGE

- Operation handlers (_op_set_priority, _op_add_thought_item, etc.) — no changes needed
- Widget — no changes needed
- Existing single-op behavior must remain backward compatible