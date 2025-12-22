"""
Board Utilities - Shared logic for priority operations.

Used by:
- prioritize_clusters: bulk priority assignment
- edit_board: single priority mutations
"""

from typing import List, Optional, Union
import copy

from pydantic import BaseModel, field_validator


# ============================================================================
# Constants
# ============================================================================

MAX_PRIORITIES = 3
VALID_RANKS = {"P1", "P2", "P3"}


# ============================================================================
# Priority Input Model
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


# ============================================================================
# Thought Item Helpers
# ============================================================================


def normalize_thought_item(item: Union[str, dict]) -> dict:
    """Convert string thought item to object format."""
    if isinstance(item, str):
        return {"text": item}
    return item


def clear_all_thought_item_priorities(items: List[Union[str, dict]]) -> List[Union[str, dict]]:
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


# ============================================================================
# Board-Level Priority Operations
# ============================================================================


def clear_all_priorities(clusters: List[dict]) -> List[dict]:
    """
    Recursively clear priority on all clusters, subclusters, and thought items.

    Used when priorities array is empty (explicit clear all).
    """
    result = copy.deepcopy(clusters)
    for cluster in result:
        cluster["priority"] = None
        # Clear thought item priorities
        cluster["thought_items"] = clear_all_thought_item_priorities(
            cluster.get("thought_items", [])
        )
        # Clear subcluster priorities
        for subcluster in cluster.get("subclusters", []):
            subcluster["priority"] = None
            subcluster["thought_items"] = clear_all_thought_item_priorities(
                subcluster.get("thought_items", [])
            )
    return result


def apply_priorities(clusters: List[dict], priorities: List[PriorityInput]) -> List[dict]:
    """
    Apply priority metadata to clusters, subclusters, and thought items.

    Returns deep copy of clusters with priority fields added.
    Converts string thought items to objects when prioritized.

    Priority preservation rules:
    - Empty priorities array = clear ALL priorities (explicit early return)
    - Entities explicitly in request = always get new priority (request wins)
    - Entities NOT in request = preserve UNLESS their rank is being reassigned elsewhere
    """
    # EXPLICIT EARLY RETURN: empty priorities = clear all
    if not priorities:
        return clear_all_priorities(clusters)

    # Build lookups
    container_priority_map = {}  # name -> {rank, reason}
    item_priority_map = {}  # (parent_name, item_index) -> {rank, reason}

    for p in priorities:
        if p.is_item_target():
            item_priority_map[(p.parent_name, p.item_index)] = {"rank": p.rank, "reason": p.reason}
        elif p.is_container_target():
            container_priority_map[p.name] = {"rank": p.rank, "reason": p.reason}

    # Ranks being assigned in this call (for conflict detection)
    assigned_ranks = {p.rank for p in priorities}

    # Deep copy to avoid mutating input
    result = copy.deepcopy(clusters)

    for cluster in result:
        cluster_name = cluster.get("cluster_name", "")

        # Apply cluster priority
        if cluster_name in container_priority_map:
            # Explicitly in request → always set (request wins)
            cluster["priority"] = container_priority_map[cluster_name]
        else:
            # Not in request → preserve UNLESS rank is being reassigned elsewhere
            existing_priority = cluster.get("priority")
            existing_rank = existing_priority.get("rank") if existing_priority else None
            if existing_rank and existing_rank in assigned_ranks:
                cluster["priority"] = None  # Rank taken by someone else
            elif existing_priority is None and "priority" not in cluster:
                # Ensure priority key exists for consistent output structure
                cluster["priority"] = None
            # else: keep existing priority (do nothing)

        # Process cluster's direct thought items
        items = cluster.get("thought_items", [])
        new_items = []
        for idx, item in enumerate(items):
            key = (cluster_name, idx)
            if key in item_priority_map:
                # Explicitly in request → set new priority
                normalized = normalize_thought_item(item)
                normalized["priority"] = item_priority_map[key]
                new_items.append(normalized)
            elif isinstance(item, dict) and item.get("priority"):
                # Not in request but has existing priority → check for rank conflict
                existing_rank = item["priority"].get("rank")
                if existing_rank and existing_rank in assigned_ranks:
                    # Rank taken by someone else → clear
                    new_items.append({"text": item.get("text", ""), "priority": None})
                else:
                    # Preserve existing priority
                    new_items.append(item)
            else:
                # No existing priority and not in request → keep as-is
                new_items.append(item)
        cluster["thought_items"] = new_items

        # Apply subcluster priorities
        for subcluster in cluster.get("subclusters", []):
            sub_name = subcluster.get("subcluster_name", "")

            if sub_name in container_priority_map:
                # Explicitly in request → always set (request wins)
                subcluster["priority"] = container_priority_map[sub_name]
            else:
                # Not in request → preserve UNLESS rank is being reassigned elsewhere
                existing_priority = subcluster.get("priority")
                existing_rank = existing_priority.get("rank") if existing_priority else None
                if existing_rank and existing_rank in assigned_ranks:
                    subcluster["priority"] = None  # Rank taken by someone else
                elif existing_priority is None and "priority" not in subcluster:
                    # Ensure priority key exists for consistent output structure
                    subcluster["priority"] = None
                # else: keep existing priority (do nothing)

            # Process subcluster's thought items
            sub_items = subcluster.get("thought_items", [])
            new_sub_items = []
            for idx, item in enumerate(sub_items):
                key = (sub_name, idx)
                if key in item_priority_map:
                    # Explicitly in request → set new priority
                    normalized = normalize_thought_item(item)
                    normalized["priority"] = item_priority_map[key]
                    new_sub_items.append(normalized)
                elif isinstance(item, dict) and item.get("priority"):
                    # Not in request but has existing priority → check for rank conflict
                    existing_rank = item["priority"].get("rank")
                    if existing_rank and existing_rank in assigned_ranks:
                        # Rank taken by someone else → clear
                        new_sub_items.append({"text": item.get("text", ""), "priority": None})
                    else:
                        # Preserve existing priority
                        new_sub_items.append(item)
                else:
                    # No existing priority and not in request → keep as-is
                    new_sub_items.append(item)
            subcluster["thought_items"] = new_sub_items

    return result
