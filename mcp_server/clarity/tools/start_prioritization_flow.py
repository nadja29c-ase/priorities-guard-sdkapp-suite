"""
Start Prioritization Flow Tool.

Single authority for ALL priority mutations across the board.
Handles clusters, subclusters, AND thought item priorities.

Allows user to mark MAX 3 entities as P1/P2/P3.
Updates widget to visually highlight priorities and reorder display.

Self-registers at import time.

Role boundaries:
- LLM: Facilitates goal elicitation, prompts user to identify priorities
- User: Decides WHAT is prioritized
- Tool: Receives final decisions, updates widget (execution only)
"""

from typing import List, Optional

import structlog
from mcp import types as mcp_types

from .base import ToolDefinition
from . import register_tool
from ..handlers.resources import WIDGET_URI
from ..tool_logic import enrich_clusters
from .board_utils import (
    MAX_PRIORITIES,
    PriorityInput,
    apply_priorities as _apply_priorities,
    compute_content_hash,
    normalize_name,
)
from ..persistence import get_cluster, persist_cluster

logger = structlog.get_logger(__name__)

# ============================================================================
# Error Messages
# ============================================================================

ERROR_TOO_MANY_PRIORITIES = "Maximum 3 priorities allowed. Please select up to 3 clusters or subclusters."
ERROR_DUPLICATE_RANK = "Each priority rank (P1, P2, P3) can only be assigned once."
ERROR_INVALID_CLUSTER = "Cluster or subcluster not found. Please reference a valid name from the current board."
ERROR_NO_BOARD = "No board available. Use organize_thoughts first to create a board."
ERROR_PARENT_AND_CHILD = "Cannot prioritize both a cluster and its subcluster. Choose one."
ERROR_INVALID_RANK = "Invalid rank. Must be P1, P2, or P3."
ERROR_AMBIGUOUS_NAME = "'{name}' exists as both a cluster and subcluster. Please rename one to make it unique."
ERROR_INVALID_PARENT = "Parent '{parent}' not found. Please reference a valid cluster or subcluster name."
ERROR_ITEM_INDEX_OUT_OF_BOUNDS = "Item index {index} is out of bounds for '{parent}' (has {count} items)."
# >1 SAME-TYPE match after normalization. Covers case variants ("Foo"/"foo") and exact
# duplicates ("Tasks"/"Tasks" under different parents) — one normalized key, several
# stored entries. Distinct from ERROR_AMBIGUOUS_NAME, which is the CROSS-type case.
ERROR_DUPLICATE_NAME = (
    "More than one cluster or subcluster on your board matches '{name}'. Names that "
    "differ only by capitalisation or surrounding spaces are treated as the same name. "
    "Rename one so they are distinct, then try again."
)
ERROR_RANK_ALREADY_ASSIGNED = "{rank} is already assigned to {entity}. Clear it first or choose a different rank."

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "start_prioritization_flow"

DESCRIPTION = """Help the user identify the prioritization criterion and based on it what matters most on their board IN THIS MOMENT — user can nameup to 3 focus areas (priority 1, priority 2, priority 3) and this reduces overwhelm/overload. Board is fetched automatically.


WHEN TO CALL:
- User wants to identify priorities on their MindSort board
- User needs help with finding focus with the help of the MindSort board
- User names a priority 

Call iteratively: once when user names their first priority, again only if user volunteers a second, again only if user volunteers a third. Maximum 3. NEVER push the user to name more than they offer.

CALL PRECONDITION: 
Before helping the user identify priorities, help the user identify the prioritization criterion - user_prioritization_criterion_verbatim must be non-empty. Ask once: "What matters most right now — progress toward a goal, removing a blocker, or getting some relief?"
Then facilitate the prioritization process by using the user's prioritization criterion. This will make it easier for the user to identify what their priorities are, and it will help you subsequently facilitate the trade-offs involved in prioritization. Store the user's exact answer in user_prioritization_criterion_verbatim and use it to frame your facilitation of priority identification.

MINDSORT MODE — BINDING RULES (not guidelines):
When user engages MindSort AI, your default assistant behavior is SUSPENDED. YOUR ROLE instead is: Empathic Facilitator of the MindSort process.

SUSPENDED BEHAVIORS:
- Never evaluating user's choices, priorities, or feelings as correct or incorrect.
- NEVER suggest what the user "should" do or how they "should" feel/decide unprompted.
- NEVER infer or guess priorities unprompted. NEVER advise on what to prioritize unprompted.
- NEVER explore root causes of emotional distress unprompted. 

TARGETING:
1. Clusters/subclusters → use "name": { name: "Work Projects", rank: "P1" }
2. Individual thought items → use "item_index" + "parent_name": { item_index: 0, parent_name: "Work Projects", rank: "P1" }

"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "user_prioritization_criterion_verbatim": {
            "type": "string",
            "description": (
                "Copy the user's exact words stating what criterion matters most right now — "
                "e.g. 'relief', 'I want to unblock the project', 'make progress on my goal'. "
                "Do NOT call this tool until the user has answered: "
                "'What matters most right now — progress toward a goal, removing a blocker, or getting some relief?' "
                "Never infer the criterion. Store their exact answer here."
            ),
            "minLength": 1,
        },
        "user_priorities_verbatim": {
            "type": "string",
            "description": (
                "Copy-paste the user's exact words explicitly naming their priorities. "
                "Must be non-empty. "
                "Examples: 'my P1 is the client project', 'I want to focus on health first, work second'. "
                "Do NOT call this tool until the user has explicitly stated which clusters or items "
                "are their priorities. Never infer priorities from context or conversation history."
            ),
            "minLength": 1,
        },
        "priorities": {
            "type": "array",
            "description": "Priority assignments (max 3). Use name for clusters/subclusters, or item_index + parent_name for thought items.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The cluster_name or subcluster_name to prioritize (for cluster/subcluster targeting)"
                    },
                    "item_index": {
                        "type": "integer",
                        "description": "0-based position in parent's thought_items array (for thought item targeting)"
                    },
                    "parent_name": {
                        "type": "string",
                        "description": "Required when targeting a thought item - the cluster or subcluster name containing the item"
                    },
                    "rank": {
                        "type": "string",
                        "enum": ["P1", "P2", "P3"],
                        "description": "Priority rank"
                    },
                    "reason": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Required. The user's criterion for this priority. Use 'blocker' when the user's criterion is removing something blocking progress, 'goal-aligned' when it is progress toward a specific goal, 'relief' when it is reducing mental load or stress."
                    }
                },
                "required": ["rank", "reason"],
                "additionalProperties": False,
            },
            "maxItems": 3
        }
    },
    "required": ["user_prioritization_criterion_verbatim", "user_priorities_verbatim", "priorities"],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["clarity.write"]

# ============================================================================
# Helper Functions
# ============================================================================


def _find_all_names(clusters: List[dict]) -> tuple[dict, dict, dict]:
    """
    Build the normalized -> stored[] name indexes for this board.

    ========================================================================
    THIS IS THE ROOT OF THE FIX FOR THIS HANDLER. Read before changing it.
    ========================================================================
    It used to return raw name SETS, and every check downstream inherited exact,
    case-sensitive matching from them — including the one that raises the reported
    "Cluster or subcluster not found" error. Normalizing _find_container_by_name alone
    does NOT fix that error: that function is only on the item-target parent path, not
    the container-target path where the error is raised. Measured.

    The value is a LIST, not a scalar, and that is load-bearing. One normalized key
    mapping to several stored names IS the ambiguity condition, and it covers two cases
    that a scalar map would silently collapse into "last one wins":
      - case variants        "Foo" / "foo"
      - exact duplicates     "Tasks" / "Tasks"   (different parents)
    After normalization these are the same condition, so they get the same handling.
    Ambiguity detection and canonicalization are therefore one operation over one
    structure, rather than two checks that can drift apart.

    Returns:
        - cluster_index:        normalized name -> [stored cluster names]
        - subcluster_index:     normalized name -> [stored subcluster names]
        - subcluster_to_parent: stored subcluster name -> stored parent cluster name
    """
    cluster_index: dict = {}
    subcluster_index: dict = {}
    subcluster_to_parent: dict = {}

    for cluster in clusters:
        name = cluster.get("cluster_name", "")
        if name:
            cluster_index.setdefault(normalize_name(name), []).append(name)

        for subcluster in cluster.get("subclusters", []):
            sub_name = subcluster.get("subcluster_name", "")
            if sub_name:
                subcluster_index.setdefault(normalize_name(sub_name), []).append(sub_name)
                # Last-wins on duplicate stored names. Harmless now: the >1 rule rejects
                # any board where a targeted name is duplicated, so no resolution ever
                # reaches this map through an ambiguous key. Before the >1 rule this
                # silently mis-keyed the parent+child guard below.
                subcluster_to_parent[sub_name] = name

    return cluster_index, subcluster_index, subcluster_to_parent


def _resolve_stored_name(index: dict, name: str) -> tuple:
    """
    Apply the 0 / 1 / >1 rule against a normalized -> stored[] index.

    Returns (stored_name, error):
        zero -> (None, None)                 caller decides which not-found error fits
        one  -> (stored_name, None)          the canonical handle for Requirement 3
        many -> (None, ERROR_DUPLICATE_NAME) fail closed, never first-match-wins
    """
    stored = index.get(normalize_name(name))
    if not stored:
        return None, None
    if len(stored) > 1:
        return None, ERROR_DUPLICATE_NAME.format(name=name)
    return stored[0], None


def _get_thought_item_count(container: dict) -> int:
    """Get the count of thought items in a container (cluster or subcluster)."""
    return len(container.get("thought_items", []))


def _find_container_by_name(clusters: List[dict], name: str) -> tuple:
    """
    Find a container (cluster or subcluster) by NORMALIZED name, applying the >1 rule.

    Returns (container, container_type, error):
        zero matches -> (None, "", None)                caller picks its not-found error
        one  match   -> (container, "cluster"/"subcluster", None)
        many matches -> (None, "", ERROR_DUPLICATE_NAME) fail closed

    THE >1 RULE LIVES HERE, NOT IN THE CALLER, and that is the point. An earlier
    revision of this fix normalized this function but returned the FIRST match, which
    silently reintroduced exactly the bug the increment exists to remove — one level
    down, on the item-target path. Two failures were reproducible:

      - exact-duplicate parents ("Tasks" under two clusters): the item priority fanned
        out to BOTH, because apply_priorities keys items (parent_name, index) and
        matches board-wide;
      - case-variant parents ("TASKS"): BEFORE normalization this errored with
        "Parent not found"; after normalization it silently first-matched and then
        fanned out — a hard error turned into a silent double write, which is strictly
        worse than the bug being fixed.

    Enforcing the rule inside the resolver means a future second caller inherits it
    rather than having to remember it. Do not "simplify" this back to returning the
    first match.

    SCOPE NOTE, because this function is easy to over-attribute: it is NOT on the
    container-target path. Normalizing it does not fix the "Cluster or subcluster not
    found" error users hit — that is raised from the container-target branch against
    the name indexes. Verified by measurement.
    """
    normalized = normalize_name(name)

    cluster_matches = [
        c for c in clusters
        if normalize_name(c.get("cluster_name")) == normalized
    ]
    subcluster_matches = [
        sc
        for c in clusters
        for sc in c.get("subclusters", [])
        if normalize_name(sc.get("subcluster_name")) == normalized
    ]

    # Clusters take precedence, as before — but only once it is established that the
    # name is unambiguous WITHIN that type. Cross-type ambiguity is a separate check
    # the caller has already made against ambiguous_keys.
    if len(cluster_matches) > 1:
        return None, "", ERROR_DUPLICATE_NAME.format(name=name)
    if cluster_matches:
        return cluster_matches[0], "cluster", None

    if len(subcluster_matches) > 1:
        return None, "", ERROR_DUPLICATE_NAME.format(name=name)
    if subcluster_matches:
        return subcluster_matches[0], "subcluster", None

    return None, "", None


def _validate_priorities(
    priorities: List[PriorityInput],
    clusters_data: List[dict],
    cluster_index: dict,
    subcluster_index: dict,
    subcluster_to_parent: dict
) -> Optional[str]:
    """
    Validate priority assignments across all entity types.

    Returns error message if invalid, None if valid.

    ====================================================================
    THIS FUNCTION MUTATES `priorities` — that is Requirement 3, shape (i).
    ====================================================================
    On success it REWRITES each PriorityInput's `name` / `parent_name` to the
    container's STORED name. That is not a side effect to be tidied away; it is the
    canonicalization boundary for this handler, and _apply_priorities immediately
    downstream depends on it.

    _apply_priorities is an exact matcher (see board_utils.apply_priorities). Validate
    with normalization but leave the caller's string on the model, and the result is
    error=None with the priority silently NOT applied — measured, and worse than the
    not-found error this replaces, because it reports success.

    Canonicalization and ambiguity detection are the SAME operation here: resolving a
    normalized key against the stored[] index yields either one stored name (canonical)
    or several (ambiguous). Do not split them into two passes — a second traversal is a
    second place to drift out of agreement with the first.
    """
    # Check max priorities
    if len(priorities) > MAX_PRIORITIES:
        return ERROR_TOO_MANY_PRIORITIES

    # Check for duplicate ranks in incoming request
    ranks_used = set()
    for p in priorities:
        if p.rank in ranks_used:
            return ERROR_DUPLICATE_RANK
        ranks_used.add(p.rank)

    # CROSS-TYPE ambiguity, computed over NORMALIZED keys so a cluster "X" and a
    # subcluster "x" collide exactly as "X"/"X" would. Left as a raw-name intersection,
    # this check would silently stop firing the moment the rest of the handler started
    # matching case-insensitively — the sets simply would not intersect.
    ambiguous_keys = set(cluster_index) & set(subcluster_index)
    for p in priorities:
        if p.is_container_target() and normalize_name(p.name) in ambiguous_keys:
            return ERROR_AMBIGUOUS_NAME.format(name=p.name)

    # Validate each priority target.
    # These two sets accumulate CANONICAL stored names, never the caller's strings —
    # the parent+child guard at the bottom compares them against subcluster_to_parent,
    # which is keyed by stored names. Mixing raw and stored here is what would silently
    # disable that guard.
    prioritized_clusters = set()
    prioritized_subclusters = set()

    for p in priorities:
        if p.is_item_target():
            # Targeting a thought item - validate parent_name and item_index
            if not p.parent_name:
                return ERROR_INVALID_PARENT.format(parent="(empty)")

            # Check for ambiguous parent name
            if normalize_name(p.parent_name) in ambiguous_keys:
                return ERROR_AMBIGUOUS_NAME.format(name=p.parent_name)

            container, container_type, dup_error = _find_container_by_name(
                clusters_data, p.parent_name
            )
            if dup_error:
                return dup_error
            if container is None:
                return ERROR_INVALID_PARENT.format(parent=p.parent_name)

            item_count = _get_thought_item_count(container)
            if p.item_index < 0 or p.item_index >= item_count:
                return ERROR_ITEM_INDEX_OUT_OF_BOUNDS.format(
                    index=p.item_index,
                    parent=p.parent_name,
                    count=item_count
                )

            # Requirement 3 — canonical parent forward. _apply_priorities keys items
            # (parent_name, index); a raw string here misses and silently sets nothing.
            p.parent_name = (
                container.get("subcluster_name") if container_type == "subcluster"
                else container.get("cluster_name")
            )

        elif p.is_container_target():
            # Targeting a cluster or subcluster.
            # THIS IS THE PATH THAT RAISES THE REPORTED ERROR (ERROR_INVALID_CLUSTER
            # below) — not _find_container_by_name, which this branch never calls.
            stored, dup_error = _resolve_stored_name(cluster_index, p.name)
            if dup_error:
                return dup_error
            if stored is not None:
                p.name = stored                    # Requirement 3 — canonical forward
                prioritized_clusters.add(stored)
            else:
                stored, dup_error = _resolve_stored_name(subcluster_index, p.name)
                if dup_error:
                    return dup_error
                if stored is not None:
                    p.name = stored                # Requirement 3 — canonical forward
                    prioritized_subclusters.add(stored)
                else:
                    return ERROR_INVALID_CLUSTER
        else:
            # Neither name nor item_index provided
            return "Priority must have either 'name' (for cluster/subcluster) or 'item_index' + 'parent_name' (for thought item)."

    # ========================================================================
    # Q5 — parent + child conflict guard. THIS ONE FAILS OPEN IF GOT WRONG.
    # ========================================================================
    # Forbids prioritizing a cluster and its own subcluster together. Unlike every other
    # failure mode in this handler — which fail CLOSED, returning an error and mutating
    # nothing — a break here fails OPEN: no error, and the board accepts a state this
    # guard exists to forbid. That is silent and strictly worse than the bug this
    # increment fixes, so it gets called out rather than buried in the site list.
    #
    # It is correct only because all three inputs are STORED names:
    #   prioritized_subclusters  canonical, set above
    #   subcluster_to_parent     keyed and valued by stored names
    #   prioritized_clusters     canonical, set above
    # Reintroduce a raw caller string into any one of them and a case-variant input
    # stops matching here — the conflict goes undetected and the write proceeds.
    # Whatever else changes, these three must stay in the same namespace.
    for sub_name in prioritized_subclusters:
        parent_name = subcluster_to_parent.get(sub_name)
        if parent_name and parent_name in prioritized_clusters:
            return ERROR_PARENT_AND_CHILD

    return None


# ============================================================================
# Provenance Guidance
# ============================================================================

GUIDANCE_EMPTY_PRIORITIES_VERBATIM = (
    "user_priorities_verbatim is empty. Do not call this tool yet. "
    "The user has stated their criterion. Now ask which cluster fits it best — "
    "that becomes their priority number 1. "
    "Only continue if the user volunteers more priorities."
)


def _build_provenance_error(error_code: str, instruction: str) -> mcp_types.CallToolResult:
    """Build a structured error response for provenance validation failure."""
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Provenance validation failed: {error_code}"
        )],
        structuredContent={
            "success": False,
            "error": error_code,
            "assistant_guidance": {
                "action": "ASK_CLARIFYING",
                "instruction": instruction,
            },
        },
        isError=True,
    )


# ============================================================================
# Malformed-Input Guards (fail-closed, self-correcting)
# ============================================================================
# A malformed invocation used to resolve `priorities` to [] (missing key, unknown
# keys, or a non-list value), and apply_priorities([]) takes the CLEAR-ALL branch
# which is then persisted — so a call meant to SET a priority silently ERASED the
# board's priorities. These guards fail closed BEFORE any fetch/mutate/persist.

# Derived from the published schema, never hand-written, so it cannot drift.
ALLOWED_TOP_LEVEL_KEYS = set(INPUT_SCHEMA["properties"])

# Shared tail for all three guards: states that nothing changed, then exactly how
# to retry. The CUMULATIVE reminder is required — without it the model may retry
# with only the new priority and overwrite the others, turning a destructive-clear
# bug into a destructive-overwrite bug.
_RETRY_INSTRUCTION = (
    "NO existing priorities were modified — the board is unchanged. "
    "Reissue this call with the canonical `priorities` array. Each entry is either "
    '{"name": "<cluster or subcluster name>", "rank": "P1"|"P2"|"P3", "reason": "<the user\'s criterion>"} '
    "for a cluster or subcluster, or "
    '{"item_index": <0-based integer>, "parent_name": "<containing cluster or subcluster name>", '
    '"rank": "P1"|"P2"|"P3", "reason": "<the user\'s criterion>"} '
    "for a thought item. The array must contain the FULL CUMULATIVE set of priorities — every "
    "already-set P1/P2/P3 PLUS the new one — because the array REPLACES the board's priorities, it "
    "does not append to them. Do not tell the user their board changed."
)


def _build_malformed_input_error(
    error_code: str,
    invalid_fields: List[str],
    problem: str,
) -> mcp_types.CallToolResult:
    """
    Build a structured error response for a malformed-input guard.

    Extends the provenance-error shape with `state_modified` and `invalid_fields`
    so the model knows the board was NOT touched and which fields to fix.
    """
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Malformed input: {error_code}"
        )],
        structuredContent={
            "success": False,
            "error": error_code,
            "state_modified": False,
            "invalid_fields": invalid_fields,
            "assistant_guidance": {
                "action": "retry_with_canonical_priorities",
                "instruction": f"{problem} {_RETRY_INSTRUCTION}",
            },
        },
        isError=True,
    )


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Apply priority rankings to clusters/subclusters.

    Args:
        user_id: Authenticated user ID from JWT
        correlation_id: Request correlation ID for tracing
        arguments: { priorities: [...], user_prioritization_criterion_verbatim: "...", user_priorities_verbatim: "..." }

    Returns:
        CallToolResult with prioritized board and widget metadata
    """
    logger.debug("start_prioritization_flow.handle.start",
                user_id=user_id,
                correlation_id=correlation_id)

    # ============================================================
    # PROVENANCE CHECK (behavioral gate)
    # ============================================================
    user_priorities_verbatim = arguments.get("user_priorities_verbatim", "")
    if not user_priorities_verbatim or not user_priorities_verbatim.strip():
        logger.info("start_prioritization_flow.provenance_failed",
                    user_id=user_id,
                    field="user_priorities_verbatim")
        return _build_provenance_error(
            "empty_priorities_verbatim",
            GUIDANCE_EMPTY_PRIORITIES_VERBATIM,
        )

    # ============================================================
    # PROVENANCE CHECK — criterion gate
    # ============================================================
    user_prioritization_criterion_verbatim = arguments.get("user_prioritization_criterion_verbatim", "")
    if not user_prioritization_criterion_verbatim or not user_prioritization_criterion_verbatim.strip():
        logger.info("start_prioritization_flow.provenance_failed",
                    user_id=user_id,
                    field="user_prioritization_criterion_verbatim")
        return _build_provenance_error(
            "empty_prioritization_criterion_verbatim",
            "Do not call this tool yet. Ask the user: "
            "'What matters most right now — progress toward a goal, removing a blocker, or getting some relief?' "
            "Wait for their answer before calling this tool.",
        )

    # ============================================================
    # MALFORMED-INPUT GUARDS (fail-closed) — order is fixed: A -> B -> C.
    # These run AFTER the provenance gates (so an existing provenance failure
    # still gets its existing instruction) and BEFORE any fetch/mutate/persist.
    # ============================================================

    # Guard A — unknown top-level argument key.
    unknown_keys = sorted(set(arguments) - ALLOWED_TOP_LEVEL_KEYS)
    if unknown_keys:
        logger.info("start_prioritization_flow.malformed_input",
                    user_id=user_id,
                    error="unknown_top_level_fields",
                    invalid_fields=unknown_keys)
        return _build_malformed_input_error(
            "unknown_top_level_fields",
            unknown_keys,
            f"Unknown top-level field(s) were sent: {', '.join(unknown_keys)}. "
            "They are not part of this tool's schema, so the call was rejected.",
        )

    # Guard B — `priorities` key absent. Presence, NOT truthiness: an explicit
    # `priorities: []` is present and must reach the existing clear-all path.
    if "priorities" not in arguments:
        logger.info("start_prioritization_flow.malformed_input",
                    user_id=user_id,
                    error="missing_priorities",
                    invalid_fields=["priorities"])
        return _build_malformed_input_error(
            "missing_priorities",
            ["priorities"],
            "The required `priorities` field was missing from the call, so the call was rejected.",
        )

    # Guard C — `priorities` present but not a list. `[]` IS a list and passes
    # through untouched; wrong-type is not the same as empty-list.
    if not isinstance(arguments["priorities"], list):
        logger.info("start_prioritization_flow.malformed_input",
                    user_id=user_id,
                    error="invalid_priorities_type",
                    invalid_fields=["priorities"])
        return _build_malformed_input_error(
            "invalid_priorities_type",
            ["priorities"],
            "`priorities` must be an array, but a "
            f"{type(arguments['priorities']).__name__} was sent, so the call was rejected.",
        )

    # ============================================================
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
    # NOTE: Guards B and C above already returned for an absent or non-list
    # `priorities`, so the default and the isinstance coercion below are no longer
    # reachable for those cases. Retained deliberately as defence in depth — do not
    # "clean up" as dead code.
    raw_priorities = arguments.get("priorities", [])
    if not isinstance(raw_priorities, list):
        raw_priorities = []

    try:
        priorities = [PriorityInput.model_validate(p) for p in raw_priorities]
    except Exception as e:
        logger.warning("start_prioritization_flow.priority_parse_failed",
                      user_id=user_id, error=str(e))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Invalid priority format. Please specify rank and target name."
            )],
            isError=True,
        )

    # Find all valid names
    cluster_index, subcluster_index, subcluster_to_parent = _find_all_names(clusters_data)

    # Validate priorities
    error = _validate_priorities(
        priorities,
        clusters_data,
        cluster_index,
        subcluster_index,
        subcluster_to_parent
    )
    if error:
        logger.info("start_prioritization_flow.validation_error",
                   user_id=user_id,
                   error=error)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=error
            )],
            isError=True,
        )

    # Apply priorities to clusters
    prioritized_clusters = _apply_priorities(clusters_data, priorities)

    # ============================================================
    # AUTO-PERSIST UPDATED BOARD TO DB (fatal on failure)
    # ============================================================
    # TRUTHFULNESS FIX (2026-07-05): persist_cluster returns None on failure instead
    # of raising, so we must check the return value. See organize_thoughts.py.
    try:
        storage_data = {"clusters": prioritized_clusters}
        content_hash = compute_content_hash(prioritized_clusters)
        cluster_id = await persist_cluster(
            user_id=user_id,
            cluster_data=storage_data,
            thoughts_exhausted=False,
            correctly_clustered=None,
            correlation_id=correlation_id,
            content_hash=content_hash,
        )
        if cluster_id is None:
            logger.error("start_prioritization_flow.persist_returned_none", user_id=user_id)
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
        logger.info("start_prioritization_flow.auto_persisted", user_id=user_id, cluster_id=cluster_id)
    except Exception as e:
        logger.error("start_prioritization_flow.persist_failed", user_id=user_id, error=str(e))
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

    # Enrich with sum_thought_items for widget
    enriched_clusters = enrich_clusters(prioritized_clusters)

    # Build response
    priority_count = len(priorities)
    if priority_count == 0:
        message = "Priorities cleared from board."
    else:
        ranks = [p.rank for p in priorities]
        message = f"Applied {priority_count} priorit{'y' if priority_count == 1 else 'ies'} ({', '.join(sorted(ranks))}) to board."

    logger.info("start_prioritization_flow.success",
               user_id=user_id,
               priority_count=priority_count)

    meta = {
        "ui": {"resourceUri": WIDGET_URI},
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Applying priorities...",
        "openai/toolInvocation/invoked": message,
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }

    if priority_count == 0:
        guidance = """No priorities yet. Facilitate discovery with FUTURE-ORIENTED questions.

Examples:
- "Which of these would bring the most relief if you made progress on it?"
- "Is anything here blocking the others?"

NOT allowed: "Why do you feel overwhelmed?" or "What's causing this stress?" Stay forward-focused."""

    elif priority_count == 1:
        guidance = """Priority number 1 is set. Acknowledge it in context of the criterion the user stated.

Then present the trade-off explicitly — do not just ask if they want to add more:
- Adding a second priority splits attention and reduces the quality of focus on priority number 1
- Staying with one priority means deeper, higher-quality execution toward the criterion they named

Frame this against their actual criterion. Examples:
- If criterion was 'progress toward a goal': "That's your priority number 1 toward [goal]. One focused priority usually moves a goal faster than two split ones. Does full attention on this feel right, or is there something else that also directly serves [goal]?"
- If criterion was 'remove a blocker': "That's your priority number 1 to unblock things. Staying focused here gives it the best chance of actually clearing. Is this the only blocker, or is there a second one that would still leave you stuck if you cleared this?"
- If criterion was 'relief': "That's your priority number 1 for peace of mind. One clear focus often brings more relief than two. Does this feel like enough, or is there something else weighing on you equally?"

Always name the criterion and the trade-off. Make it a conscious choice, not a default yes/no.
If user says one is enough: close warmly. Your board has been updated.
If user names another: call start_prioritization_flow again with P1 + P2. Update user_prioritization_criterion_verbatim if the user stated a different criterion for this priority.
TARGETING REMINDER: If the user names a thought item (not a cluster), use item_index + parent_name, NOT name.
Example: { "item_index": 0, "parent_name": "Admin and delivery upkeep", "rank": "P2" }
Never target a thought item by its text as a cluster name — it will fail."""

    elif priority_count == 2:
        guidance = """Two priorities set. Acknowledge, then present the same trade-off for a third — frame it against the criterion.

Adding a third priority further divides attention. The question is whether a third is necessary to serve the criterion, or whether two focused priorities already cover it.

Example if criterion was 'progress toward a goal': "Two clear focus areas toward [goal]. A third would split your attention further — is there something that would directly block [goal] if left out, or do these two cover it?"
Example if criterion was 'relief': "Two priorities — that already takes a lot off the mental pile. Is there a third that's still weighing on you, or does this feel like enough to breathe?"
Example if criterion was 'remove a blocker': "Two focus areas to unblock. Would a third still leave you stuck, or are these two enough to clear the path?"

Always name the criterion. Make adding a third a conscious trade-off, not a default.
If user says two is enough: close warmly. Your board has been updated.
If user names another: call start_prioritization_flow again with P1 + P2 + P3. Update user_prioritization_criterion_verbatim if the user stated a different criterion for this priority.
TARGETING REMINDER: If the user names a thought item (not a cluster), use item_index + parent_name, NOT name.
Example: { "item_index": 0, "parent_name": "Admin and delivery upkeep", "rank": "P3" }
Never target a thought item by its text as a cluster name — it will fail."""

    else:  # 3
        guidance = """All priorities set. Acknowledge warmly, then let user lead.

Example: "You've got your focus areas. Your board has been updated."

Now follow user's lead — they may want to discuss next steps, or they may be done."""

    return mcp_types.CallToolResult(
        content=[],
        structuredContent={
            "clusters": enriched_clusters,
            "assistant_guidance": guidance,
        },
        _meta=meta,
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Auto-persists to DB
    destructive_hint=False,  # Priorities are reversible — can be changed or cleared at any time
    open_world_hint=False,  # Only affects internal backend
))
