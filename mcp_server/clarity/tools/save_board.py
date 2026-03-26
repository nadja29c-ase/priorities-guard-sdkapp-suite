"""
save_board.py — Deprecated as of Increment 15 (DB-only model).

Tool registration removed. Helper functions retained pending verification
of external callers. compute_content_hash is now canonical in board_utils.py.
"""

import hashlib
import json
import unicodedata
from typing import List, Optional, Union

from mcp import types as mcp_types
from pydantic import BaseModel, Field

# ============================================================================
# Validation Limits (from Increment 12 spec)
# ============================================================================

MAX_CLUSTERS = 20  # Top-level clusters only (subclusters don't count)
MAX_TOTAL_ITEMS = 100  # Sum of all thought_items across clusters + subclusters
MAX_ITEM_LENGTH = 500  # Characters per thought item

# ============================================================================
# Error Codes (standardized, match widget expectations)
# ============================================================================

ERROR_TOO_MANY_CLUSTERS = "TOO_MANY_CLUSTERS"
ERROR_TOO_MANY_ITEMS = "TOO_MANY_ITEMS"
ERROR_ITEM_TOO_LONG = "ITEM_TOO_LONG"
ERROR_EMPTY_BOARD = "EMPTY_BOARD"
ERROR_SERVER_ERROR = "SERVER_ERROR"

# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class SubclusterInput(BaseModel):
    """Expected structure for each subcluster."""
    subcluster_name: str
    thought_items: List[Union[str, dict]] = Field(default_factory=list)  # string or {text, priority?}
    tags: List[str] = Field(default_factory=list)
    priority: Optional[dict] = None  # Added in increment 13


class ClusterInput(BaseModel):
    """Expected structure for each cluster."""
    cluster_name: str
    thought_items: List[Union[str, dict]] = Field(default_factory=list)  # string or {text, priority?}
    subclusters: List[SubclusterInput] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    priority: Optional[dict] = None  # Added in increment 13


class SaveBoardRequest(BaseModel):
    """Expected top-level structure for save request."""
    clusters: List[ClusterInput]


# ============================================================================
# Helper Functions
# ============================================================================


def _make_error_response(error_code: str, message: str) -> mcp_types.CallToolResult:
    """Create a standardized error response."""
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=message)],
        structuredContent={
            "saved": False,
            "error_code": error_code,
            "error": message,
            "saved_board_hash": None,
        },
        isError=True,
    )


def _count_total_items(clusters: List["ClusterInput"]) -> int:
    """Count total thought items across all clusters and subclusters."""
    total = 0
    for cluster in clusters:
        total += len(cluster.thought_items)
        for subcluster in cluster.subclusters:
            total += len(subcluster.thought_items)
    return total


def _get_item_text(item: Union[str, dict]) -> str:
    """Extract text from thought item (handles both string and object format)."""
    if isinstance(item, dict):
        return item.get("text", "")
    return item


def _find_long_item(clusters: List["ClusterInput"], max_length: int) -> Optional[str]:
    """Find first item exceeding max_length, or None if all valid."""
    for cluster in clusters:
        for item in cluster.thought_items:
            text = _get_item_text(item)
            if len(text) > max_length:
                return text
        for subcluster in cluster.subclusters:
            for item in subcluster.thought_items:
                text = _get_item_text(item)
                if len(text) > max_length:
                    return text
    return None


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
