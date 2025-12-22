"""
Edit Board Tool.

Single-operation mutations on an existing board.
Handles priorities, renames, and deletes.

Self-registers at import time.
"""

from typing import List, Optional, Union
import copy

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, Field, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..handlers.resources import WIDGET_URI
from ..tool_logic import enrich_clusters
from .board_utils import (
    VALID_RANKS,
    PriorityInput,
    apply_priorities,
    clear_all_priorities,
)

logger = structlog.get_logger(__name__)

# ============================================================================
# Constants
# ============================================================================

VALID_OPERATIONS = {
    "set_priority",
    "clear_priority",
    "rename_cluster",
    "rename_subcluster",
    "delete_cluster",
    "delete_subcluster",
    "delete_thought_item",
    "clear_all_priorities",
}

# ============================================================================
# Error Messages
# ============================================================================

ERROR_NO_BOARD = "No board provided. Pass the current board to edit."
ERROR_INVALID_OPERATION = "Invalid operation. Supported: set_priority, clear_priority, rename_cluster, rename_subcluster, delete_cluster, delete_subcluster, delete_thought_item, clear_all_priorities"
ERROR_MISSING_TARGET = "Target not specified. Provide target_name or item_index + parent_name."
ERROR_CLUSTER_NOT_FOUND = "Cluster '{name}' not found."
ERROR_SUBCLUSTER_NOT_FOUND = "Subcluster '{name}' not found in '{parent}'."
ERROR_ITEM_NOT_FOUND = "Item index {index} not found in '{parent}'."
ERROR_MISSING_NEW_NAME = "new_name required for rename operation."
ERROR_MISSING_RANK = "rank required for set_priority operation."
ERROR_PARENT_NOT_FOUND = "Parent '{parent}' not found."

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "edit_board"

DESCRIPTION = """
PURPOSE: Edit an existing board — change priorities, rename clusters, or delete items.
Use this when user wants to MODIFY their current board, not create a new one.

WHEN TO CALL:
- User says "make X my P2" or "change P1 to Y"
- User says "rename X to Y"
- User says "delete X" or "remove X"
- User says "clear my priorities"

CRITICAL INPUT REQUIREMENT:
You MUST pass the EXACT board JSON from the previous tool output.
- Copy the complete clusters array including ALL priority fields
- Do NOT reconstruct the board from memory
- Do NOT summarize or simplify the structure

DOES NOT AUTO-SAVE: Changes are applied to working board only. User must call save_board to persist.

AFTER TOOL RETURNS: Confirm the change was made. If user wants to save, remind them to ask.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "board": {
            "type": "array",
            "description": "CRITICAL: Pass the EXACT clusters JSON from the previous tool output. Do NOT reconstruct from memory.",
            "items": {
                "type": "object",
                "properties": {
                    "cluster_name": {"type": "string"},
                    "priority": {
                        "type": ["object", "null"],
                        "description": "Existing priority (MUST pass through from previous output)",
                        "properties": {"rank": {"type": "string"}, "reason": {"type": "string"}}
                    },
                    "thought_items": {
                        "type": "array",
                        "items": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "object", "properties": {"text": {"type": "string"}, "priority": {"type": "object"}}}
                            ]
                        }
                    },
                    "subclusters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "subcluster_name": {"type": "string"},
                                "priority": {
                                    "type": ["object", "null"],
                                    "description": "Existing priority (MUST pass through from previous output)",
                                    "properties": {"rank": {"type": "string"}, "reason": {"type": "string"}}
                                },
                                "thought_items": {
                                    "type": "array",
                                    "items": {
                                        "oneOf": [
                                            {"type": "string"},
                                            {"type": "object", "properties": {"text": {"type": "string"}, "priority": {"type": "object"}}}
                                        ]
                                    }
                                },
                                "tags": {"type": "array", "items": {"type": "string"}}
                            }
                        }
                    },
                    "tags": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["cluster_name"]
            }
        },
        "operation": {
            "type": "string",
            "enum": ["set_priority", "clear_priority", "rename_cluster", "rename_subcluster", "delete_cluster", "delete_subcluster", "delete_thought_item", "clear_all_priorities"],
            "description": "The edit operation to perform"
        },
        "target_name": {
            "type": "string",
            "description": "Cluster or subcluster name to target"
        },
        "parent_name": {
            "type": "string",
            "description": "Parent container name (for subclusters and thought items)"
        },
        "item_index": {
            "type": "integer",
            "description": "0-based index for thought item targeting"
        },
        "rank": {
            "type": "string",
            "enum": ["P1", "P2", "P3"],
            "description": "For set_priority operation"
        },
        "new_name": {
            "type": "string",
            "description": "For rename operations"
        }
    },
    "required": ["board", "operation"]
}

REQUIRED_SCOPES = ["clarity.write"]

# ============================================================================
# Pydantic Models
# ============================================================================


class SubclusterInput(BaseModel):
    """Subcluster structure."""
    subcluster_name: str
    thought_items: List[Union[str, dict]] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    priority: Optional[dict] = None


class ClusterInput(BaseModel):
    """Cluster structure."""
    cluster_name: str
    thought_items: List[Union[str, dict]] = Field(default_factory=list)
    subclusters: List[SubclusterInput] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    priority: Optional[dict] = None


class EditBoardRequest(BaseModel):
    """Request structure for edit_board tool."""
    board: List[ClusterInput]
    operation: str
    target_name: Optional[str] = None
    parent_name: Optional[str] = None
    item_index: Optional[int] = None
    rank: Optional[str] = None
    new_name: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================


def _find_cluster(clusters: List[dict], name: str) -> Optional[dict]:
    """Find a cluster by name."""
    for c in clusters:
        if c.get("cluster_name") == name:
            return c
    return None


def _find_subcluster(clusters: List[dict], name: str, parent_name: Optional[str] = None) -> tuple:
    """
    Find a subcluster by name.

    Returns: (subcluster, parent_cluster) or (None, None) if not found.
    """
    for cluster in clusters:
        if parent_name and cluster.get("cluster_name") != parent_name:
            continue
        for sc in cluster.get("subclusters", []):
            if sc.get("subcluster_name") == name:
                return sc, cluster
    return None, None


def _find_container(clusters: List[dict], name: str) -> tuple:
    """
    Find a container (cluster or subcluster) by name.

    Returns: (container, container_type, parent_cluster)
             container_type is "cluster" or "subcluster"
    """
    # Check clusters first
    cluster = _find_cluster(clusters, name)
    if cluster:
        return cluster, "cluster", None

    # Check subclusters
    subcluster, parent = _find_subcluster(clusters, name)
    if subcluster:
        return subcluster, "subcluster", parent

    return None, None, None


# ============================================================================
# Operation Handlers
# ============================================================================


def _op_set_priority(clusters: List[dict], target_name: Optional[str],
                     parent_name: Optional[str], item_index: Optional[int],
                     rank: Optional[str]) -> tuple:
    """
    Set priority on target. Returns (updated_clusters, error_message).
    Error is None on success.
    """
    if not rank:
        return None, ERROR_MISSING_RANK
    if rank not in VALID_RANKS:
        return None, f"Invalid rank: {rank}. Must be P1, P2, or P3."

    # Build a PriorityInput for the target
    if item_index is not None:
        # Targeting a thought item
        if not parent_name:
            return None, ERROR_MISSING_TARGET

        # Verify parent exists
        container, _, _ = _find_container(clusters, parent_name)
        if not container:
            return None, ERROR_PARENT_NOT_FOUND.format(parent=parent_name)

        # Verify item_index is valid
        items = container.get("thought_items", [])
        if item_index < 0 or item_index >= len(items):
            return None, ERROR_ITEM_NOT_FOUND.format(index=item_index, parent=parent_name)

        priority = PriorityInput(item_index=item_index, parent_name=parent_name, rank=rank)
    elif target_name:
        # Targeting a cluster or subcluster
        container, _, _ = _find_container(clusters, target_name)
        if not container:
            return None, ERROR_CLUSTER_NOT_FOUND.format(name=target_name)

        priority = PriorityInput(name=target_name, rank=rank)
    else:
        return None, ERROR_MISSING_TARGET

    # Use apply_priorities to handle global uniqueness
    updated = apply_priorities(clusters, [priority])
    return updated, None


def _op_clear_priority(clusters: List[dict], target_name: Optional[str],
                       parent_name: Optional[str], item_index: Optional[int]) -> tuple:
    """
    Clear priority from target. Returns (updated_clusters, error_message).
    """
    result = copy.deepcopy(clusters)

    if item_index is not None:
        # Targeting a thought item
        if not parent_name:
            return None, ERROR_MISSING_TARGET

        container, container_type, parent_cluster = _find_container(result, parent_name)
        if not container:
            return None, ERROR_PARENT_NOT_FOUND.format(parent=parent_name)

        items = container.get("thought_items", [])
        if item_index < 0 or item_index >= len(items):
            return None, ERROR_ITEM_NOT_FOUND.format(index=item_index, parent=parent_name)

        # Clear priority on the item
        item = items[item_index]
        if isinstance(item, dict):
            item["priority"] = None
        # String items don't have priority, nothing to clear

    elif target_name:
        # Targeting a cluster or subcluster
        container, container_type, _ = _find_container(result, target_name)
        if not container:
            return None, ERROR_CLUSTER_NOT_FOUND.format(name=target_name)

        container["priority"] = None
    else:
        return None, ERROR_MISSING_TARGET

    return result, None


def _op_rename_cluster(clusters: List[dict], target_name: Optional[str],
                       new_name: Optional[str]) -> tuple:
    """Rename a cluster."""
    if not target_name:
        return None, ERROR_MISSING_TARGET
    if not new_name:
        return None, ERROR_MISSING_NEW_NAME

    result = copy.deepcopy(clusters)
    cluster = _find_cluster(result, target_name)
    if not cluster:
        return None, ERROR_CLUSTER_NOT_FOUND.format(name=target_name)

    cluster["cluster_name"] = new_name
    return result, None


def _op_rename_subcluster(clusters: List[dict], target_name: Optional[str],
                          parent_name: Optional[str], new_name: Optional[str]) -> tuple:
    """Rename a subcluster."""
    if not target_name:
        return None, ERROR_MISSING_TARGET
    if not new_name:
        return None, ERROR_MISSING_NEW_NAME

    result = copy.deepcopy(clusters)
    subcluster, parent = _find_subcluster(result, target_name, parent_name)

    if not subcluster:
        if parent_name:
            return None, ERROR_SUBCLUSTER_NOT_FOUND.format(name=target_name, parent=parent_name)
        return None, ERROR_CLUSTER_NOT_FOUND.format(name=target_name)

    subcluster["subcluster_name"] = new_name
    return result, None


def _op_delete_cluster(clusters: List[dict], target_name: Optional[str]) -> tuple:
    """Delete a cluster and all its contents."""
    if not target_name:
        return None, ERROR_MISSING_TARGET

    result = copy.deepcopy(clusters)

    # Find and remove the cluster
    for i, c in enumerate(result):
        if c.get("cluster_name") == target_name:
            result.pop(i)
            return result, None

    return None, ERROR_CLUSTER_NOT_FOUND.format(name=target_name)


def _op_delete_subcluster(clusters: List[dict], target_name: Optional[str],
                          parent_name: Optional[str]) -> tuple:
    """Delete a subcluster and its contents."""
    if not target_name:
        return None, ERROR_MISSING_TARGET

    result = copy.deepcopy(clusters)

    for cluster in result:
        if parent_name and cluster.get("cluster_name") != parent_name:
            continue

        subclusters = cluster.get("subclusters", [])
        for i, sc in enumerate(subclusters):
            if sc.get("subcluster_name") == target_name:
                subclusters.pop(i)
                return result, None

    if parent_name:
        return None, ERROR_SUBCLUSTER_NOT_FOUND.format(name=target_name, parent=parent_name)
    return None, ERROR_CLUSTER_NOT_FOUND.format(name=target_name)


def _op_delete_thought_item(clusters: List[dict], parent_name: Optional[str],
                            item_index: Optional[int]) -> tuple:
    """Delete a single thought item."""
    if item_index is None:
        return None, ERROR_MISSING_TARGET
    if not parent_name:
        return None, ERROR_MISSING_TARGET

    result = copy.deepcopy(clusters)
    container, _, _ = _find_container(result, parent_name)

    if not container:
        return None, ERROR_PARENT_NOT_FOUND.format(parent=parent_name)

    items = container.get("thought_items", [])
    if item_index < 0 or item_index >= len(items):
        return None, ERROR_ITEM_NOT_FOUND.format(index=item_index, parent=parent_name)

    items.pop(item_index)
    return result, None


def _op_clear_all_priorities(clusters: List[dict]) -> tuple:
    """Clear all priorities from the board."""
    result = clear_all_priorities(clusters)
    return result, None


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Edit an existing board with a single operation.

    Args:
        user_id: Authenticated user ID from JWT
        correlation_id: Request correlation ID for tracing
        arguments: { board: [...], operation: "...", ... }

    Returns:
        CallToolResult with edited board and widget metadata
    """
    logger.debug("edit_board.handle.start",
                user_id=user_id,
                correlation_id=correlation_id)

    # Validate request structure
    try:
        request = EditBoardRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("edit_board.validation_failed",
                      user_id=user_id,
                      error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Invalid input format. Please provide board and operation."
            )],
            isError=True,
        )

    # Check board is provided
    if not request.board:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=ERROR_NO_BOARD)],
            isError=True,
        )

    # Validate operation
    if request.operation not in VALID_OPERATIONS:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=ERROR_INVALID_OPERATION)],
            isError=True,
        )

    # Convert to dicts for processing
    clusters_data = [c.model_dump() for c in request.board]

    # Route to operation handler
    if request.operation == "set_priority":
        result, error = _op_set_priority(
            clusters_data, request.target_name, request.parent_name,
            request.item_index, request.rank
        )
    elif request.operation == "clear_priority":
        result, error = _op_clear_priority(
            clusters_data, request.target_name, request.parent_name, request.item_index
        )
    elif request.operation == "rename_cluster":
        result, error = _op_rename_cluster(clusters_data, request.target_name, request.new_name)
    elif request.operation == "rename_subcluster":
        result, error = _op_rename_subcluster(
            clusters_data, request.target_name, request.parent_name, request.new_name
        )
    elif request.operation == "delete_cluster":
        result, error = _op_delete_cluster(clusters_data, request.target_name)
    elif request.operation == "delete_subcluster":
        result, error = _op_delete_subcluster(
            clusters_data, request.target_name, request.parent_name
        )
    elif request.operation == "delete_thought_item":
        result, error = _op_delete_thought_item(
            clusters_data, request.parent_name, request.item_index
        )
    elif request.operation == "clear_all_priorities":
        result, error = _op_clear_all_priorities(clusters_data)
    else:
        result, error = None, ERROR_INVALID_OPERATION

    # Handle operation error
    if error:
        logger.warning("edit_board.operation_failed",
                      user_id=user_id,
                      operation=request.operation,
                      error=error)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=error)],
            isError=True,
        )

    # Enrich for widget display
    enriched = enrich_clusters(result)

    # Build success message
    operation_messages = {
        "set_priority": f"Set {request.rank} on target.",
        "clear_priority": "Priority cleared.",
        "rename_cluster": f"Renamed cluster to '{request.new_name}'.",
        "rename_subcluster": f"Renamed subcluster to '{request.new_name}'.",
        "delete_cluster": f"Deleted cluster '{request.target_name}'.",
        "delete_subcluster": f"Deleted subcluster '{request.target_name}'.",
        "delete_thought_item": "Deleted thought item.",
        "clear_all_priorities": "All priorities cleared.",
    }
    message = operation_messages.get(request.operation, "Edit complete.")

    logger.info("edit_board.success",
               user_id=user_id,
               operation=request.operation)

    # Widget metadata
    meta = {
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Editing board...",
        "openai/toolInvocation/invoked": "Board updated.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=message)],
        structuredContent={
            "clusters": enriched,
            "assistant_guidance": "Confirm the change was made. Changes are not saved yet — if user wants to keep them, remind them to save."
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
