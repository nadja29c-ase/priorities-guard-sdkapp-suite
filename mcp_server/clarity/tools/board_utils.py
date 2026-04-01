"""
Board Utilities - Shared logic for priority operations.

Used by:
- start_prioritization_flow: bulk priority assignment
- edit_board: single priority mutations
"""

from typing import List, Optional, Union
import copy
import hashlib
import json
import unicodedata

from pydantic import BaseModel, field_validator


# ============================================================================
# Constants
# ============================================================================

MAX_PRIORITIES = 3
VALID_RANKS = {"P1", "P2", "P3"}

# Behavioral tags - signal cluster requires different mental mode than execute-and-done
ALLOWED_TAGS = frozenset({
    "decide",    # contains choices/tradeoffs needing resolution
    "research",  # contains unknowns needing investigation
    "test",      # contains assumptions/hypotheses to test
    "delegate",  # contains work for others
    "automate",  # contains repetitive work to systematize
    "learn",     # contains skill gaps requiring knowledge acquisition
    "align",     # contains items needing discussion/agreement with others
})
MAX_TAGS_PER_CONTAINER = 3
MAX_ITEM_LENGTH = 500


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
    reason: str

    @field_validator("rank")
    @classmethod
    def validate_rank(cls, v: str) -> str:
        if v not in VALID_RANKS:
            raise ValueError(f"Invalid rank: {v}. Must be P1, P2, or P3.")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reason must be non-empty.")
        return v.strip()

    @field_validator("item_index", mode="before")
    @classmethod
    def coerce_float_to_int(cls, v):
        """Coerce whole floats to int - ChatGPT sends 0.0 instead of 0."""
        if isinstance(v, float) and v.is_integer():
            return int(v)
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


# ============================================================================
# Content Hash
# ============================================================================


def compute_content_hash(clusters: List[dict]) -> str:
    """
    Compute SHA256 hash of board content for saved state detection.

    CANONICAL HASH SPECIFICATION (must match widget exactly):
    - Explicit key order (NOT alphabetical): cluster_name, subclusters, tags, thought_items
    - NFC Unicode normalization
    - Clusters sorted alphabetically by cluster_name
    - Subclusters sorted alphabetically by subcluster_name
    - thought_items and tags sorted lexicographically
    - No whitespace in JSON

    Args:
        clusters: List of cluster dictionaries

    Returns:
        SHA256 hex digest (64 characters)
    """
    def normalize_string(s: str) -> str:
        """NFC normalize and trim whitespace."""
        return unicodedata.normalize("NFC", s.strip())

    def normalize_thought_item(item: Union[str, dict]) -> str:
        """Extract text from thought item (handles both string and object format)."""
        if isinstance(item, dict):
            return normalize_string(item.get("text", ""))
        return normalize_string(item)

    def normalize_subcluster(s: dict) -> dict:
        """Normalize subcluster with explicit key order."""
        # Key order: subcluster_name, tags, thought_items
        return {
            "subcluster_name": normalize_string(s.get("subcluster_name", "")),
            "tags": sorted([normalize_string(t) for t in s.get("tags", [])]),
            "thought_items": sorted([normalize_thought_item(i) for i in s.get("thought_items", [])]),
        }

    def normalize_cluster(c: dict) -> dict:
        """Normalize cluster with explicit key order."""
        # Key order: cluster_name, subclusters, tags, thought_items
        return {
            "cluster_name": normalize_string(c.get("cluster_name", "")),
            "subclusters": sorted(
                [normalize_subcluster(s) for s in c.get("subclusters", [])],
                key=lambda x: x["subcluster_name"]
            ),
            "tags": sorted([normalize_string(t) for t in c.get("tags", [])]),
            "thought_items": sorted([normalize_thought_item(i) for i in c.get("thought_items", [])]),
        }

    # Sort clusters by cluster_name, normalize all content
    normalized = sorted(
        [normalize_cluster(c) for c in clusters],
        key=lambda x: x["cluster_name"]
    )

    # NO sort_keys=True - key order is determined by dict construction above
    canonical = json.dumps({"clusters": normalized}, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
