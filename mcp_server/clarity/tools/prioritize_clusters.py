"""
Prioritize Clusters Tool.

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

from typing import Any, List, Optional, Union
import copy

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, Field, ValidationError, field_validator

from .base import ToolDefinition
from . import register_tool
from ..handlers.resources import WIDGET_URI
from ..tool_logic import enrich_clusters

logger = structlog.get_logger(__name__)

# ============================================================================
# Constants
# ============================================================================

MAX_PRIORITIES = 3
VALID_RANKS = {"P1", "P2", "P3"}
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

NAME = "prioritize_clusters"

DESCRIPTION = """
PURPOSE: Marks up to 3 clusters or subclusters as P1/P2/P3 priorities on the board.
This helps the user focus on what really matters most and reduce overwhelm but also be more .

CRITICAL: NEVER EXPLORE ROOT CAUSES OF USER'S EMOTIONAL DISTRESS - ACKNOWLEDGE IT AND KEEP THE CONVERSATION FUTURE-ORIENTED AND FOCUSED ON IDENTIFIYING PRIORITIES - THIS WILL CREATE CLARITY AND EASE.

WHEN TO CALL:
- After user exhausted ALL thoughts AND ALL thoughts have been organized into a board
- After USER explicitly names which clusters/subclusters are their priorities (e.g. "My P1 is X, P2 is Y")
- When the user asks "what now" or "I have too much to do and I am still overwhelmed" or "I still don't know what to do next"

DO NOT CALL:
- NEVER when you infer or guess priorities or provide priorities on behalf of the user

AFTER TOOL RETURNS: Follow assistant_guidance in structuredContent.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "description": "The current board clusters to prioritize.",
            "items": {
                "type": "object",
                "properties": {
                    "cluster_name": {"type": "string"},
                    "thought_items": {"type": "array", "items": {"type": "string"}},
                    "subclusters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "subcluster_name": {"type": "string"},
                                "thought_items": {"type": "array", "items": {"type": "string"}},
                                "tags": {"type": "array", "items": {"type": "string"}}
                            }
                        }
                    },
                    "tags": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["cluster_name"]
            }
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
                "required": ["rank"]
            },
            "maxItems": 3
        }
    },
    "required": ["clusters", "priorities"]
}

REQUIRED_SCOPES = ["clarity.write"]

# ============================================================================
# Pydantic Models
# ============================================================================


class PriorityInput(BaseModel):
    """A single priority assignment.

    Targeting rules:
    - Cluster: { name: "Work", rank: "P1" }
    - Subcluster: { name: "Urgent Tasks", rank: "P2" }
    - Thought item: { item_index: 0, parent_name: "Work", rank: "P3" }
    """
    name: Optional[str] = None  # For cluster/subcluster targeting
    item_index: Optional[int] = None  # For thought item targeting
    parent_name: Optional[str] = None  # Required when targeting thought item
    rank: str
    reason: Optional[str] = None

    @field_validator("rank")
    @classmethod
    def validate_rank(cls, v: str) -> str:
        if v not in VALID_RANKS:
            raise ValueError(f"Invalid rank: {v}. Must be P1, P2, or P3.")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in {"blocker", "goal-aligned"}:
            raise ValueError(f"Invalid reason: {v}. Must be 'blocker' or 'goal-aligned'.")
        return v

    def is_item_target(self) -> bool:
        """Check if this priority targets a thought item."""
        return self.item_index is not None

    def is_container_target(self) -> bool:
        """Check if this priority targets a cluster or subcluster."""
        return self.name is not None and self.item_index is None


class SubclusterInput(BaseModel):
    """Subcluster structure."""
    subcluster_name: str
    thought_items: List[Union[str, dict]] = Field(default_factory=list)  # string or {text, priority?}
    tags: List[str] = Field(default_factory=list)
    priority: Optional[dict] = None  # Will be added by tool


class ClusterInput(BaseModel):
    """Cluster structure."""
    cluster_name: str
    thought_items: List[Union[str, dict]] = Field(default_factory=list)  # string or {text, priority?}
    subclusters: List[SubclusterInput] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    priority: Optional[dict] = None  # Will be added by tool


class PrioritizeClustersRequest(BaseModel):
    """Request structure."""
    clusters: List[ClusterInput]
    priorities: List[PriorityInput] = Field(default_factory=list)


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

            container, _container_type = _find_container_by_name(clusters_data, p.parent_name)
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


def _normalize_thought_item(item: Union[str, dict]) -> dict:
    """Convert string thought item to object format."""
    if isinstance(item, str):
        return {"text": item}
    return item


def _clear_all_thought_item_priorities(items: List[Union[str, dict]]) -> List[Union[str, dict]]:
    """Clear priorities from all thought items, preserving object structure."""
    result = []
    for item in items:
        if isinstance(item, dict):
            # Keep object format, clear priority
            result.append({"text": item.get("text", ""), "priority": None})
        else:
            # Keep as string (no priority to clear)
            result.append(item)
    return result


def _apply_priorities(clusters: List[dict], priorities: List[PriorityInput]) -> List[dict]:
    """
    Apply priority metadata to clusters, subclusters, and thought items.

    Returns deep copy of clusters with priority fields added.
    Converts string thought items to objects when prioritized.
    Clears priorities from entities not in the priorities list.
    """
    # Build lookups
    container_priority_map = {}  # name -> {rank, reason}
    item_priority_map = {}  # (parent_name, item_index) -> {rank, reason}

    for p in priorities:
        if p.is_item_target():
            item_priority_map[(p.parent_name, p.item_index)] = {"rank": p.rank, "reason": p.reason}
        elif p.is_container_target():
            container_priority_map[p.name] = {"rank": p.rank, "reason": p.reason}

    # Deep copy to avoid mutating input
    result = copy.deepcopy(clusters)

    for cluster in result:
        cluster_name = cluster.get("cluster_name", "")

        # Apply cluster priority
        if cluster_name in container_priority_map:
            cluster["priority"] = container_priority_map[cluster_name]
        else:
            cluster["priority"] = None

        # Process cluster's direct thought items
        items = cluster.get("thought_items", [])
        # First clear all existing priorities
        items = _clear_all_thought_item_priorities(items)
        # Then apply new priorities
        for idx in range(len(items)):
            key = (cluster_name, idx)
            if key in item_priority_map:
                # Convert to object and set priority
                items[idx] = _normalize_thought_item(items[idx])
                items[idx]["priority"] = item_priority_map[key]
        cluster["thought_items"] = items

        # Apply subcluster priorities
        for subcluster in cluster.get("subclusters", []):
            sub_name = subcluster.get("subcluster_name", "")
            if sub_name in container_priority_map:
                subcluster["priority"] = container_priority_map[sub_name]
            else:
                subcluster["priority"] = None

            # Process subcluster's thought items
            sub_items = subcluster.get("thought_items", [])
            # First clear all existing priorities
            sub_items = _clear_all_thought_item_priorities(sub_items)
            # Then apply new priorities
            for idx in range(len(sub_items)):
                key = (sub_name, idx)
                if key in item_priority_map:
                    # Convert to object and set priority
                    sub_items[idx] = _normalize_thought_item(sub_items[idx])
                    sub_items[idx]["priority"] = item_priority_map[key]
            subcluster["thought_items"] = sub_items

    return result


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
        arguments: { clusters: [...], priorities: [...] }

    Returns:
        CallToolResult with prioritized board and widget metadata
    """
    logger.debug("prioritize_clusters.handle.start",
                user_id=user_id,
                correlation_id=correlation_id)

    # Validate request structure
    try:
        request = PrioritizeClustersRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("prioritize_clusters.validation_failed",
                      user_id=user_id,
                      error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Invalid input format. Please provide clusters and priorities."
            )],
            isError=True,
        )

    # Check for empty board
    if not request.clusters:
        logger.info("prioritize_clusters.no_board", user_id=user_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=ERROR_NO_BOARD
            )],
            isError=True,
        )

    # Convert to dicts for processing
    clusters_data = [c.model_dump() for c in request.clusters]

    # Find all valid names
    cluster_names, subcluster_names, subcluster_to_parent = _find_all_names(clusters_data)

    # Validate priorities
    error = _validate_priorities(
        request.priorities,
        clusters_data,
        cluster_names,
        subcluster_names,
        subcluster_to_parent
    )
    if error:
        logger.info("prioritize_clusters.validation_error",
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
    prioritized_clusters = _apply_priorities(clusters_data, request.priorities)

    # Enrich with sum_thought_items for widget
    enriched_clusters = enrich_clusters(prioritized_clusters)

    # Build response
    priority_count = len(request.priorities)
    if priority_count == 0:
        message = "Priorities cleared from board."
    else:
        ranks = [p.rank for p in request.priorities]
        message = f"Applied {priority_count} priorit{'y' if priority_count == 1 else 'ies'} ({', '.join(sorted(ranks))}) to board."

    logger.info("prioritize_clusters.success",
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
        guidance = "No priorities set. Ask which clusters feel most important to them right now."

    elif priority_count == 1:
        guidance = """Nice — P1 is set. Acknowledge that they've named what matters most.

Then genuinely ask if there's a second priority pulling at them, or if one focus is enough right now. Let them decide — no pressure either way."""

    elif priority_count == 2:
        guidance = """Two priorities locked in. Reflect that back — they're creating real focus.

Check if there's a third, but make it clear that two is perfectly fine. "Is there a P3, or does this feel complete?" """

    else:  # 3
        guidance = """Three priorities — they've cut through the noise. Acknowledge that briefly.

Let them know their board is ready to save and come back to anytime. Then just be present — if they want to keep talking, talk. If they're done, that's fine too."""

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
))
