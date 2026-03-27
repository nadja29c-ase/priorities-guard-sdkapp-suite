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
)
from ..persistence import get_cluster, persist_cluster

logger = structlog.get_logger(__name__)

# ============================================================================
# Constants (local - not shared)
# ============================================================================

VALID_REASONS = {"blocker", "goal-aligned", None}

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
ERROR_RANK_ALREADY_ASSIGNED = "{rank} is already assigned to {entity}. Clear it first or choose a different rank."

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "start_prioritization_flow"

DESCRIPTION = """Requires a board to exist in DB. Use organize_thoughts to create one. load_saved_board only displays the board — it does not create DB state.
The board is fetched automatically — do NOT pass clusters. Only pass priorities and provenance fields.

WHEN TO CALL:
- As soon as the user names ANY single priority — call immediately, do not wait for more.
- When user wants to change or clear priorities.

Call iteratively: once when user names their first priority, again only if user volunteers a second, again only if user volunteers a third. Maximum 3. Never push the user to name more than they offer.

CALL PRECONDITION: user_prioritization_criterion_verbatim must be non-empty.
Ask once: "What matters most right now — progress toward a goal, removing a blocker, or getting some relief?"
The user may give a single criterion, or they may name different motivations for different priorities — that is valid. Do NOT force them to pick one criterion for the whole session. If they say "P1 is about getting unstuck and P2 is about progress toward my goal", accept both. Store their overall answer in user_prioritization_criterion_verbatim.

MINDSORT MODE — BINDING RULES (not guidelines):
When user engages MindSort AI, your default assistant behavior is SUSPENDED. YOUR ROLE instead is: Empathic Facilitator of the MindSort process.

SUSPENDED BEHAVIORS:
- Never evaluating user's choices, priorities, or feelings as correct or incorrect.
- NEVER suggest what the user "should" do or how they "should" feel/decide
- NEVER infer or guess priorities. NEVER advise on what to prioritize.
- NEVER push the user toward naming more priorities. One priority is complete.
- NEVER use "P1", "P2", "P3" in conversation — say "priority number 1", "priority number 2", "priority number 3".
- NEVER explore root causes of emotional distress. Acknowledge and stay future-oriented.

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
                        "enum": ["blocker", "goal-aligned"],
                        "description": "Optional reason for prioritization"
                    }
                },
                "required": ["rank"],
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


def _find_all_names(clusters: List[dict]) -> tuple[set, set, dict]:
    """
    Extract all cluster names and subcluster names from board.

    Returns:
        - cluster_names: Set of all cluster names
        - subcluster_names: Set of all subcluster names
        - subcluster_to_parent: Map of subcluster_name -> parent cluster_name
    """
    cluster_names = set()
    subcluster_names = set()
    subcluster_to_parent = {}

    for cluster in clusters:
        name = cluster.get("cluster_name", "")
        if name:
            cluster_names.add(name)

        for subcluster in cluster.get("subclusters", []):
            sub_name = subcluster.get("subcluster_name", "")
            if sub_name:
                subcluster_names.add(sub_name)
                subcluster_to_parent[sub_name] = name

    return cluster_names, subcluster_names, subcluster_to_parent


def _get_thought_item_count(container: dict) -> int:
    """Get the count of thought items in a container (cluster or subcluster)."""
    return len(container.get("thought_items", []))


def _find_container_by_name(clusters: List[dict], name: str) -> tuple[Optional[dict], str]:
    """
    Find a container (cluster or subcluster) by name.

    Returns:
        - container: The cluster or subcluster dict, or None if not found
        - container_type: "cluster", "subcluster", or "" if not found
    """
    # Check clusters first
    for cluster in clusters:
        if cluster.get("cluster_name") == name:
            return cluster, "cluster"

    # Check subclusters
    for cluster in clusters:
        for subcluster in cluster.get("subclusters", []):
            if subcluster.get("subcluster_name") == name:
                return subcluster, "subcluster"

    return None, ""


def _validate_priorities(
    priorities: List[PriorityInput],
    clusters_data: List[dict],
    cluster_names: set,
    subcluster_names: set,
    subcluster_to_parent: dict
) -> Optional[str]:
    """
    Validate priority assignments across all entity types.

    Returns error message if invalid, None if valid.
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

    # Check for ambiguous names (exists as both cluster and subcluster)
    ambiguous_names = cluster_names & subcluster_names
    for p in priorities:
        if p.is_container_target() and p.name in ambiguous_names:
            return ERROR_AMBIGUOUS_NAME.format(name=p.name)

    # Validate each priority target
    prioritized_clusters = set()
    prioritized_subclusters = set()

    for p in priorities:
        if p.is_item_target():
            # Targeting a thought item - validate parent_name and item_index
            if not p.parent_name:
                return ERROR_INVALID_PARENT.format(parent="(empty)")

            # Check for ambiguous parent name
            if p.parent_name in ambiguous_names:
                return ERROR_AMBIGUOUS_NAME.format(name=p.parent_name)

            container, _ = _find_container_by_name(clusters_data, p.parent_name)
            if container is None:
                return ERROR_INVALID_PARENT.format(parent=p.parent_name)

            item_count = _get_thought_item_count(container)
            if p.item_index < 0 or p.item_index >= item_count:
                return ERROR_ITEM_INDEX_OUT_OF_BOUNDS.format(
                    index=p.item_index,
                    parent=p.parent_name,
                    count=item_count
                )

        elif p.is_container_target():
            # Targeting a cluster or subcluster
            if p.name in cluster_names:
                prioritized_clusters.add(p.name)
            elif p.name in subcluster_names:
                prioritized_subclusters.add(p.name)
            else:
                return ERROR_INVALID_CLUSTER
        else:
            # Neither name nor item_index provided
            return "Priority must have either 'name' (for cluster/subcluster) or 'item_index' + 'parent_name' (for thought item)."

    # Check for parent + child conflict (cluster and its subcluster both prioritized)
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
    cluster_names, subcluster_names, subcluster_to_parent = _find_all_names(clusters_data)

    # Validate priorities
    error = _validate_priorities(
        priorities,
        clusters_data,
        cluster_names,
        subcluster_names,
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
        logger.info("start_prioritization_flow.auto_persisted", user_id=user_id)
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
        content=[mcp_types.TextContent(
            type="text",
            text=message
        )],
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
