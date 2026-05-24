You're right that the description line is weak — it tells the LLM what not to do without explaining the conceptual boundary. Let me think through this clearly before agreeing.
The rule you're proposing:

≤ 3 items → edit_board with add_thought_item


3 items → organize_thoughts (reclustering)



Is the count threshold the right boundary?
Not quite — and here's why. The real boundary isn't item count, it's whether the items fit cleanly into existing clusters or represent new themes that require restructuring the board. That said, count IS a reasonable operational proxy because:

1-3 items: user is doing targeted additions — they know where things go
4+ items: user is essentially doing a new brain dump — the board needs to be reconsidered

The right implementation:
Not server-side validation — that's still a brittle gate that blocks legitimate batch edits (e.g. adding 4 items across 4 different clusters in one batch call). The right place is the edit_board DESCRIPTION making the boundary explicit and instructive, combined with a server-side assistant_guidance error when the batch is large.
Proposed approach — two changes:
1. edit_board DESCRIPTION — add to WHEN TO CALL:
- Use this for 1–3 targeted additions to existing clusters where you know exactly which cluster each item belongs to.
- If the user wants to add 4 or more new thoughts, or if the items don't clearly map to existing clusters, use read_saved_board → merge → organize_thoughts instead. Adding many new thoughts is a reclustering operation, not a surgical edit.
2. Server-side guard in edit_board handler — when the total number of add_thought_item operations in a single call exceeds 3, return an instructive isError=True with assistant_guidance:
pythonadd_item_ops = [op for op in ops if op.operation == "add_thought_item"]
if len(add_item_ops) > 3:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Too many items to add via edit_board."
        )],
        structuredContent={
            "success": False,
            "error": "too_many_additions",
            "assistant_guidance": (
                "The user wants to add more than 3 new thought items. "
                "This is a reclustering operation, not a surgical edit. "
                "Use read_saved_board to load the existing board, merge the new items in, "
                "then call organize_thoughts to recluster the full board."
            ),
        },
        isError=True,
    )
The combination of description guidance (prevents the call in the first place) + server-side gate (catches it when description guidance is ignored) is the right dual-layer approach. The threshold of 3 is explicit, documented, and gives the LLM a clear rule.
Does this match what you had in mind? If so I'll write the full briefing.Yes great!7:30 PMReading the current edit_board.py handler to get exact placement for the server-side guard before writing the briefing.Read Text FileRead Text FileNow I have everything. I can see the exact handler structure. The server-side guard needs to go after the ops list is built but before the "Validate all operations" loop. Here's the complete briefing:

Claude Code Briefing — edit_board: session precondition + too-many-additions guard
Context
Two issues found in production testing:

LLM called edit_board assuming a board existed without confirming one in-session
LLM sent 6 add_thought_item operations to edit_board when the correct path was organize_thoughts — this is a reclustering operation, not a surgical edit

Both are addressed with one DESCRIPTION change and one handler guard.

File: mcp_server/clarity/tools/edit_board.py
Change 1 — DESCRIPTION: insert CRITICAL PRECONDITION at the very top, before "PURPOSE:"
pythonDESCRIPTION = """
CRITICAL PRECONDITION: Only call this tool if a board has been confirmed to exist in the current conversation — via a prior successful call to load_saved_board, read_saved_board, or organize_thoughts in THIS session. Do not assume a board exists based on user intent or context. If no board is confirmed, do not call edit_board.

PURPOSE: Targeted, surgical edits to an existing board...
```

**Change 2 — DESCRIPTION: update WHEN TO CALL add_thought_item bullets**

Replace:
```
- User says "add X to Y" (use add_thought_item)
- User says "add these items to my board" or "add these items to [cluster]" with a specific list → use add_thought_item in batch mode via operations array
- Use this for any targeted edits, even when multiple specific edits are requested at once
```

With:
```
- User says "add X to Y" (use add_thought_item) — for 1–3 targeted additions where you know exactly which cluster each item belongs to.
- User says "add these items to my board" with a short specific list of 1–3 items → use add_thought_item in batch mode via operations array.
- If the user wants to add 4 or more new thoughts, or the items don't clearly map to existing clusters, do NOT use edit_board. Use read_saved_board → merge → organize_thoughts instead. Adding many new thoughts is a reclustering operation, not a surgical edit.
- Use this for any targeted edits, even when multiple specific edits are requested at once.
Change 3 — Add error constant after the existing error constants block:
pythonERROR_TOO_MANY_ADDITIONS = (
    "Too many items to add at once. edit_board is for 1–3 targeted additions. "
    "For 4 or more new thoughts, use read_saved_board → merge → organize_thoughts."
)
Change 4 — Add server-side guard in handle()
Insert after the ops list is built (after the else: ops = [SingleOperation(...)] block) and before the # Validate all operations loop:
python# ============================================================
# TOO-MANY-ADDITIONS GUARD
# If more than 3 add_thought_item operations are requested,
# redirect to organize_thoughts via instructive error.
# This is a reclustering operation, not a surgical edit.
# ============================================================
add_item_ops = [op for op in ops if op.operation == "add_thought_item"]
if len(add_item_ops) > 3:
    logger.info("edit_board.too_many_additions",
                user_id=user_id,
                count=len(add_item_ops))
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=ERROR_TOO_MANY_ADDITIONS,
        )],
        structuredContent={
            "success": False,
            "error": "too_many_additions",
            "assistant_guidance": (
                f"The user wants to add {len(add_item_ops)} new thought items. "
                "edit_board is for 1–3 targeted additions only. "
                "This is a reclustering operation. "
                "Call read_saved_board to load the existing board, "
                "merge the new items into the existing clusters in-model, "
                "then call organize_thoughts with the full merged cluster set."
            ),
        },
        isError=True,
    )
```

---

**File: `mcp_server/clarity/tools/organize_thoughts.py`**

**Change 5 — DESCRIPTION: add one bullet to WHEN TO CALL**

Add after the existing trigger bullets:
```
- User provides a list of tasks or thoughts but has NOT yet signaled they are done — do NOT jump to edit_board. Acknowledge what they shared, continue elicitation with open questions, and only call this tool once they unprompted signal completion ("that's it", "done", "nothing else").

What does NOT change:

All existing handler logic
All isError=True error paths
All assistant_guidance strings
All schema fields
All other tool files

Before deploying: Read OPERATIONS_PREDEPLOY.md.