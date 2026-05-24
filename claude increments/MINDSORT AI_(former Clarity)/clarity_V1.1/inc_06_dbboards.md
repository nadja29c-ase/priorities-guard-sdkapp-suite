
Claude Code Briefing: MindSort AI — DB-Only Board (Increment 6)
Context & Product Decision
MindSort AI currently uses an ephemeral board model: boards live in LLM context during a conversation and must be explicitly saved to DB. This forces the LLM to pass the full board JSON as input to prioritize_clusters and edit_board on every call — the LLM must reconstruct and serialize the entire board before the tool fires. This is the primary cause of 8-10 second latency.
This increment migrates to a DB-only model:

Every board mutation auto-persists to DB immediately
Tools fetch board from DB — LLM no longer passes board payload
No explicit save step — save button removed
organize_thoughts immediately overwrites any existing saved board after clustering succeeds — deliberate product decision, no undo
Persist failures are fatal — in a DB-only model a non-fatal persist failure creates a state lie
Known limitation: concurrent tool calls from two open conversations will last-write-wins on the same board. Accepted for v1, no fix in this increment.

Read doc/OPERATIONS_PRESUBMISSION.md before deploying.

Implementation Approach — Copy and Adjust, Never Rewrite
For each file: read verbatim, make only the listed changes, never rewrite, restructure, or improve anything not explicitly listed.

File 1: mcp_server/clarity/tools/board_utils.py
What changes: Add compute_content_hash here so it can be imported without depending on save_board.py.
Check whether hashlib, json, unicodedata, and Union from typing are already imported at the top. Add any that are missing.
Copy the full compute_content_hash function verbatim from save_board.py and append it to the bottom of board_utils.py. Do not modify the function body.

File 2: mcp_server/clarity/tools/save_board.py
What changes: Remove tool registration, handler, and all imports that are only used by the deleted code. Keep helper functions and models.
Remove entirely:

NAME, DESCRIPTION, INPUT_SCHEMA, REQUIRED_SCOPES constants
handle() function
register_tool(ToolDefinition(...)) call at the bottom

Keep: _make_error_response, _count_total_items, _get_item_text, _find_long_item, compute_content_hash, all Pydantic models (SubclusterInput, ClusterInput, SaveBoardRequest).
Imports: After removing the handler and registration, audit which imports are still needed by the retained functions and models. Remove any imports that are exclusively used by the deleted handle() function or registration call and are no longer referenced. Keep only what the retained symbols actually use.
Update module docstring to:
python"""
save_board.py — Deprecated as of Increment 15 (DB-only model).

Tool registration removed. Helper functions retained pending verification
of external callers. compute_content_hash is now canonical in board_utils.py.
"""

File 3: mcp_server/clarity/tools/__init__.py
Remove exactly this line:
pythonfrom . import save_board  # noqa: F401, E402
No other changes.

File 4: mcp_server/clarity/tools/organize_thoughts.py
Add imports alongside existing imports:
pythonfrom ..persistence import persist_cluster
from .board_utils import compute_content_hash
```

Update module docstring from:
```
NOTE: As of Increment 12, this tool is PURE (no DB persistence).
      Use save_board to explicitly save the board.
```
To:
```
NOTE: As of Increment 15, this tool auto-persists to DB after successful clustering (DB-only model).
      Overwrites any existing saved board. No undo. Persist failure is fatal.
In handle(), after result = format_clusters(clusters, thoughts_exhausted=validated_request.thoughts_exhausted) and before building the mcp_types.CallToolResult response, add:
python# ============================================================
# AUTO-PERSIST TO DB — runs only after clustering succeeds (fatal on failure)
# ============================================================
try:
    clusters_for_storage = {"clusters": clusters}
    content_hash = compute_content_hash(clusters)
    await persist_cluster(
        user_id=user_id,
        cluster_data=clusters_for_storage,
        thoughts_exhausted=False,
        correctly_clustered=None,
        correlation_id=correlation_id,
        content_hash=content_hash,
    )
    logger.info("organize_thoughts.auto_persisted", user_id=user_id)
except Exception as e:
    logger.error("organize_thoughts.persist_failed", user_id=user_id, error=str(e))
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Your board could not be saved."
        )],
        structuredContent={
            "success": False,
            "error": "persist_failed",
            "assistant_guidance": {
                "action": "RETRY",
                "instruction": (
                    "Board clustering succeeded but could not be saved to the database. "
                    "Tell the user their board was not saved and ask them to try again. "
                    "Do NOT imply the board was updated."
                ),
            },
        },
        isError=True,
    )
Update ToolDefinition registration:

read_only_hint: True → False
destructive_hint: False → True  # overwrites saved board state in DB
open_world_hint: leave unchanged at False


File 5: mcp_server/clarity/tools/prioritize_clusters.py
Add imports:
pythonfrom ..persistence import get_cluster, persist_cluster
from .board_utils import compute_content_hash
INPUT_SCHEMA:

Remove the entire "clusters" property from INPUT_SCHEMA["properties"]
Update "required" to: ["user_prioritization_criterion_verbatim", "user_priorities_verbatim", "priorities"]

Pydantic models:

Remove SubclusterInput, ClusterInput, PrioritizeClustersRequest class definitions entirely
Keep PriorityInput import from board_utils

handle() — replace validation + board checks block:
Remove everything from # Validate request structure through clusters_data = [c.model_dump() for c in request.clusters] and the total_items == 0 check.
Replace with:
python# ============================================================
# FETCH BOARD FROM DB
# ============================================================
cluster_record = await get_cluster(user_id=user_id, correlation_id=correlation_id)
if not cluster_record:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=ERROR_NO_BOARD)],
        isError=True,
    )

inner_data = cluster_record.get("cluster_data") or {}
clusters_data = inner_data.get("clusters") or []

if not clusters_data:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=ERROR_NO_BOARD)],
        isError=True,
    )

# Parse priorities from arguments
raw_priorities = arguments.get("priorities", [])
if not isinstance(raw_priorities, list):
    raw_priorities = []

try:
    priorities = [PriorityInput.model_validate(p) for p in raw_priorities]
except Exception as e:
    logger.warning("prioritize_clusters.priority_parse_failed",
                  user_id=user_id, error=str(e))
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Invalid priority format. Please specify rank and target name."
        )],
        isError=True,
    )
After prioritized_clusters = _apply_priorities(clusters_data, priorities), add:
python# ============================================================
# AUTO-PERSIST UPDATED BOARD TO DB (fatal on failure)
# ============================================================
try:
    storage_data = {"clusters": prioritized_clusters}
    content_hash = compute_content_hash(prioritized_clusters)
    await persist_cluster(
        user_id=user_id,
        cluster_data=storage_data,
        thoughts_exhausted=False,
        correctly_clustered=None,
        correlation_id=correlation_id,
        content_hash=content_hash,
    )
    logger.info("prioritize_clusters.auto_persisted", user_id=user_id)
except Exception as e:
    logger.error("prioritize_clusters.persist_failed", user_id=user_id, error=str(e))
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Your priorities could not be saved."
        )],
        structuredContent={
            "success": False,
            "error": "persist_failed",
            "assistant_guidance": {
                "action": "RETRY",
                "instruction": (
                    "Priority assignment succeeded but could not be saved to the database. "
                    "Tell the user their priorities were not saved and ask them to try again. "
                    "Do NOT imply the board was updated."
                ),
            },
        },
        isError=True,
    )
```

**DESCRIPTION:** Add at the top of the WHEN TO CALL section:
```
Requires a board to exist in DB (created via organize_thoughts or loaded via load_saved_board).
The board is fetched automatically — do NOT pass clusters. Only pass priorities and provenance fields.
Remove any "suggest saving the board" instruction from all priority_count guidance strings — replace with "Your board has been updated."
ToolDefinition registration:

read_only_hint: True → False
destructive_hint: False → True  # overwrites saved board state in DB
open_world_hint: leave unchanged at False


File 6: mcp_server/clarity/tools/edit_board.py
Add imports:
pythonfrom ..persistence import get_cluster, persist_cluster
from .board_utils import compute_content_hash
INPUT_SCHEMA:

Remove the entire "board" property from INPUT_SCHEMA["properties"]
Update "required" to []

Pydantic models:

Remove SubclusterInput and ClusterInput class definitions entirely
Update EditBoardRequest — remove the board: List[ClusterInput] field:

pythonclass EditBoardRequest(BaseModel):
    """Request structure — single or batch mode."""
    operation: Optional[str] = None
    target_name: Optional[str] = None
    parent_name: Optional[str] = None
    item_index: Optional[int] = None
    rank: Optional[str] = None
    new_name: Optional[str] = None
    text: Optional[str] = None
    tag: Optional[str] = None
    operations: Optional[List[SingleOperation]] = None

    @field_validator("item_index", mode="before")
    @classmethod
    def coerce_item_index(cls, v):
        if v is None:
            return None
        if isinstance(v, float):
            return int(v)
        return v
handle() changes:
Remove the if not request.board: check.
After request = EditBoardRequest.model_validate(arguments), add:
python# ============================================================
# FETCH BOARD FROM DB
# ============================================================
cluster_record = await get_cluster(user_id=user_id, correlation_id=correlation_id)
if not cluster_record:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=ERROR_NO_BOARD)],
        isError=True,
    )

inner_data = cluster_record.get("cluster_data") or {}
clusters_data = inner_data.get("clusters") or []

if not clusters_data:
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=ERROR_NO_BOARD)],
        isError=True,
    )
Remove the line clusters_data = [c.model_dump() for c in request.board].
After the operation loop completes without error — after all completed.append(op.operation) iterations finish — before enriched = enrich_clusters(clusters_data), add:
python# ============================================================
# AUTO-PERSIST MUTATED BOARD TO DB (fatal on failure)
# _dispatch_operation uses deepcopy per op and fails fast, so clusters_data
# here is always the complete result of all successful operations.
# ============================================================
try:
    storage_data = {"clusters": clusters_data}
    content_hash = compute_content_hash(clusters_data)
    await persist_cluster(
        user_id=user_id,
        cluster_data=storage_data,
        thoughts_exhausted=False,
        correctly_clustered=None,
        correlation_id=correlation_id,
        content_hash=content_hash,
    )
    logger.info("edit_board.auto_persisted", user_id=user_id, operations=completed)
except Exception as e:
    logger.error("edit_board.persist_failed", user_id=user_id, error=str(e))
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Your changes could not be saved."
        )],
        structuredContent={
            "success": False,
            "error": "persist_failed",
            "assistant_guidance": {
                "action": "RETRY",
                "instruction": (
                    "Board edit succeeded but could not be saved to the database. "
                    "Tell the user their changes were not saved and ask them to try again. "
                    "Do NOT imply the board was updated."
                ),
            },
        },
        isError=True,
    )
```

**DESCRIPTION:** Remove `CRITICAL INPUT REQUIREMENT` section entirely. Remove `DOES NOT AUTO-SAVE` line. Replace with:
```
Requires a board to exist in DB (created via organize_thoughts or loaded via load_saved_board).
The board is fetched automatically — do NOT pass a board parameter.
All changes are persisted automatically after every successful operation.
ToolDefinition registration:

read_only_hint: True → False
destructive_hint: False → True  # overwrites saved board state in DB
open_world_hint: leave unchanged at False


File 7: mcp_server/clarity/tools/load_saved_board.py
Replace the guidance string in the else branch (board has clusters):
pythonguidance = """Board loaded with existing clusters.

Read the user's intent from what they said BEFORE calling this tool:
- If they asked to FOCUS, PRIORITIZE, or said they're OVERWHELMED/STRESSED → skip any further elicitation. Ask directly: "What matters most right now — progress toward a goal, removing a blocker, or getting some relief?" Then call prioritize_clusters as soon as they answer.
- If they asked to ADD items → proceed with adding via organize_thoughts or edit_board.
- If they just asked to SEE the board → ask "How can I help?" and let them lead.

Do NOT call organize_thoughts if the board already exists and the user just wants to focus or prioritize."""

File 8: mcp_server/clarity/widget-react/src/App.tsx
Remove state declarations: isSaving, showSaved, saveError and their useState calls.
Remove saveButtonRef ref declaration.
Remove the entire handleSave async function.
Remove the saveError display block.
Remove the sticky Save button div at the bottom entirely.
Check whether extractStructuredContent is used anywhere else in App.tsx besides handleSave. If only in handleSave, remove the import.
Check whether Check from @openai/apps-sdk-ui/components/Icon is used anywhere else. If only in the save button, remove the import.
Keep loadError state and its display block.
notifyHeight effect: Do not add a new effect. Find the existing useEffect that calls notifyHeight() in response to state changes — it currently includes saveError in its dependency array. Remove saveError from that dependency array since the state no longer exists. Do not add a duplicate effect.

Files NOT to Touch

mcp_server/clarity/tools/read_saved_board.py
mcp_server/clarity/persistence.py
mcp_server/clarity/tool_logic.py
mcp_server/clarity/tools/delete_my_data.py
Backend — no changes


Known Preserved Behavior
edit_board._op_add_thought_item has a target_name fallback when parent_name is empty. This is in _dispatch_operation. Do not remove it — keep exactly as-is.

Pre-Deploy Checklist
Before deploying, read doc/OPERATIONS_PRESUBMISSION.md in full, then:

Verify save_board not in tool list — GET /mcp tools listing must not include save_board
Verify prioritize_clusters schema — confirm no clusters field in input schema via MCP Inspector
Verify edit_board schema — confirm no board field in input schema via MCP Inspector
DB roundtrip test on test account — call organize_thoughts → verify get_cluster returns the new board → call prioritize_clusters with priorities only → verify get_cluster returns board with priorities persisted
Test fatal persist path — temporarily break BACKEND_URL on Render, call organize_thoughts, verify it returns an error and does not silently succeed, then restore
Recreate connector in ChatGPT developer mode — ChatGPT caches tool schemas per connector. After schema changes, delete the existing connector and create a new one. Test in a fresh conversation, not an existing one
Widget rebuild — run npm run build in mcp_server/clarity/widget-react/ and copy output to mcp_server/clarity/widgets/clarity-clusters.html
Widget height check — verify widget renders correctly without the save button in both inline and fullscreen modes, light and dark
Grep for stale "save" references — run grep -rn "save" mcp_server/clarity/tools/ and grep -rn "save" mcp_server/clarity/widget-react/src/ — update any guidance or widget copy that still refers to manual saving
Known concurrency limitation — concurrent tool calls from two open conversations will last-write-wins. Accepted for v1, no fix needed.
