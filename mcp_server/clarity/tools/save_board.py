"""
Save Board Tool.

Saves the current board state to the database.
Self-registers at import time.

Callable by:
- LLM: When user asks to save their board
- Widget: When user clicks Save button
"""

import hashlib
import json
import unicodedata
from typing import List, Optional, Union

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, Field, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..persistence import persist_cluster

logger = structlog.get_logger(__name__)

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
# Tool Metadata
# ============================================================================

NAME = "save_board"

DESCRIPTION = """
Save the current Clarity board to the database.

WHEN TO CALL:
- ONLY WHEN User EXPLICITELY ASKS TO SAVE their board f.e. "Save my board"
- Or User clicked Widget Save button

WHEN NOT TO CALL:
- NEVER call this tool automatically when you are ASSUMING user implied "save" f.e. user asks "Add to my saved board" -> read saved board via read_saved_board THEN add the requested edit by merging it with saved board and calling organize_board to create a new updated version of the saved board.

Returns saved=true for widget to show temporary "Saved" confirmation (3 seconds).
Does NOT render a new widget. Widget shows transient feedback only.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "confirmed": {
            "type": "boolean",
            "description": "Must be true to save. Set to true ONLY after user explicitly confirms. Note: Users can only have ONE saved board - saving replaces any previously saved board."
        },
        "clusters": {
            "type": "array",
            "description": "The current board state to save.",
            "items": {
                "type": "object",
                "properties": {
                    "cluster_name": {
                        "type": "string",
                        "description": "Name of the cluster"
                    },
                    "thought_items": {
                        "type": "array",
                        "items": {
                            "oneOf": [
                                {"type": "string"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "text": {"type": "string"},
                                        "priority": {
                                            "type": ["object", "null"],
                                            "properties": {
                                                "rank": {"type": "string", "enum": ["P1", "P2", "P3"]},
                                                "reason": {"type": "string", "enum": ["blocker", "goal-aligned"]}
                                            }
                                        }
                                    }
                                }
                            ]
                        },
                        "description": "Direct thought items (string or object)"
                    },
                    "subclusters": {
                        "type": "array",
                        "description": "Nested groupings within cluster",
                        "items": {
                            "type": "object",
                            "properties": {
                                "subcluster_name": {
                                    "type": "string"
                                },
                                "thought_items": {
                                    "type": "array",
                                    "items": {
                                        "oneOf": [
                                            {"type": "string"},
                                            {
                                                "type": "object",
                                                "properties": {
                                                    "text": {"type": "string"},
                                                    "priority": {
                                                        "type": ["object", "null"],
                                                        "properties": {
                                                            "rank": {"type": "string", "enum": ["P1", "P2", "P3"]},
                                                            "reason": {"type": "string", "enum": ["blocker", "goal-aligned"]}
                                                        }
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                },
                                "tags": {
                                    "type": "array",
                                    "items": {"type": "string"}
                                },
                                "priority": {
                                    "type": ["object", "null"],
                                    "description": "Priority assignment on this subcluster",
                                    "properties": {
                                        "rank": {"type": "string", "enum": ["P1", "P2", "P3"]},
                                        "reason": {"type": "string", "enum": ["blocker", "goal-aligned"]}
                                    }
                                }
                            },
                            "required": ["subcluster_name", "thought_items"]
                        }
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional behavioral tags"
                    },
                    "priority": {
                        "type": ["object", "null"],
                        "description": "Priority assignment on this cluster",
                        "properties": {
                            "rank": {"type": "string", "enum": ["P1", "P2", "P3"]},
                            "reason": {"type": "string", "enum": ["blocker", "goal-aligned"]}
                        }
                    }
                },
                "required": ["cluster_name"]
            }
        }
    },
    "required": ["clusters"]
}

REQUIRED_SCOPES = ["clarity.write"]

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
    confirmed: bool = False  # Default to False - requires explicit confirmation
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


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Save the current board state to the database.

    Args:
        user_id: Authenticated user ID from JWT
        correlation_id: Request correlation ID for tracing
        arguments: Raw arguments from widget

    Returns:
        CallToolResult with save status and content_hash
    """
    logger.debug("save_board.handle.start",
                user_id=user_id,
                correlation_id=correlation_id)

    # ============================================================
    # VALIDATION
    # ============================================================
    try:
        validated_request = SaveBoardRequest.model_validate(arguments)
        logger.debug("save_board.validation_success",
                    cluster_count=len(validated_request.clusters))

    except ValidationError as e:
        logger.warning("save_board.validation_failed",
                      error=str(e.errors()))
        return _make_error_response(
            ERROR_SERVER_ERROR,
            "Failed to save board: Invalid input format."
        )

    # ============================================================
    # CONFIRMATION CHECK
    # ============================================================
    if not validated_request.confirmed:
        logger.info("save_board.awaiting_confirmation", user_id=user_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Save requires user confirmation. Note: You can only have ONE saved board - saving will replace any previously saved board."
            )],
            structuredContent={
                "saved": False,
                "status": "awaiting_confirmation",
                "assistant_guidance": "Ask user to confirm they want to save. IMPORTANT: Inform them that they can only have ONE saved board at a time - if they already have a saved board, this will REPLACE it with the current board. Once they confirm, call save_board again with confirmed=true.",
            },
            isError=False,
        )

    # ============================================================
    # BUSINESS RULE VALIDATIONS (from Increment 12 spec)
    # ============================================================

    # 1. Empty board check (must have at least 1 item)
    total_items = _count_total_items(validated_request.clusters)
    if total_items == 0:
        logger.info("save_board.rejected.empty_board", user_id=user_id)
        return _make_error_response(
            ERROR_EMPTY_BOARD,
            "Cannot save an empty board. Add some thoughts first."
        )

    # 2. Cluster count limit (max 20 top-level)
    cluster_count = len(validated_request.clusters)
    if cluster_count > MAX_CLUSTERS:
        logger.info("save_board.rejected.too_many_clusters",
                   user_id=user_id, cluster_count=cluster_count)
        return _make_error_response(
            ERROR_TOO_MANY_CLUSTERS,
            f"Board has too many clusters (max {MAX_CLUSTERS} top-level). Consolidate some clusters before saving."
        )

    # 3. Total item count limit (max 100)
    if total_items > MAX_TOTAL_ITEMS:
        logger.info("save_board.rejected.too_many_items",
                   user_id=user_id, total_items=total_items)
        return _make_error_response(
            ERROR_TOO_MANY_ITEMS,
            f"Board exceeds maximum size ({MAX_TOTAL_ITEMS} items). Remove some items before saving."
        )

    # 4. Item length limit (max 500 chars)
    long_item = _find_long_item(validated_request.clusters, MAX_ITEM_LENGTH)
    if long_item is not None:
        logger.info("save_board.rejected.item_too_long",
                   user_id=user_id, item_length=len(long_item))
        return _make_error_response(
            ERROR_ITEM_TOO_LONG,
            f"One or more items exceed {MAX_ITEM_LENGTH} characters. Shorten them before saving."
        )

    # ============================================================
    # COMPUTE CONTENT HASH
    # ============================================================
    clusters_for_storage = [c.model_dump() for c in validated_request.clusters]
    content_hash = compute_content_hash(clusters_for_storage)

    # ============================================================
    # PERSIST TO DATABASE
    # ============================================================
    cluster_data_to_store = {"clusters": clusters_for_storage}

    try:
        await persist_cluster(
            user_id=user_id,
            cluster_data=cluster_data_to_store,
            thoughts_exhausted=False,  # DEPRECATED: always False
            correctly_clustered=None,  # DEPRECATED: always None
            correlation_id=correlation_id,
            content_hash=content_hash,
        )
    except Exception as e:
        logger.error("save_board.persistence_error",
                    user_id=user_id,
                    error=str(e))
        return _make_error_response(
            ERROR_SERVER_ERROR,
            "Save failed. Please try again later."
        )

    # ============================================================
    # SUCCESS RESPONSE
    # ============================================================
    cluster_count = len(validated_request.clusters)
    logger.info("save_board.success",
               user_id=user_id,
               cluster_count=cluster_count,
               content_hash=content_hash[:8])  # Log first 8 chars of hash

    # Pure data operation - never renders widget
    # Widget shows temporary "Saved" indicator via saved=true check
    # Hash in _meta: widget can read it, LLM cannot see it
    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Board saved successfully ({cluster_count} cluster{'s' if cluster_count != 1 else ''})."
        )],
        structuredContent={
            "saved": True,
            "clusters": clusters_for_storage,
            "assistant_guidance": "Board saved successfully. Confirm briefly.",
        },
        _meta={
            "saved_board_hash": content_hash,
            "openai/toolInvocation/invoking": "Saving your board...",
            "openai/toolInvocation/invoked": "Board saved.",
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,  # Pure data operation - never renders widget
    handle=handle,
    widget_accessible=True,  # Widget can call this tool
    read_only_hint=False,  # Writes to database
    destructive_hint=True,  # Overwrites previous board
    open_world_hint=False,  # Own database, not external system
))
