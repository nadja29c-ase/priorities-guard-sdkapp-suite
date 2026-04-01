"""
Edit Board Tool.

Single-operation mutations on an existing board.
Handles priorities, renames, and deletes.

Self-registers at import time.
"""

from typing import List, Optional
import copy

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError, field_validator

from .base import ToolDefinition
from . import register_tool
from ..handlers.resources import WIDGET_URI
from ..tool_logic import enrich_clusters
from .board_utils import (
    VALID_RANKS,
    ALLOWED_TAGS,
    MAX_TAGS_PER_CONTAINER,
    MAX_ITEM_LENGTH,
    PriorityInput,
    apply_priorities,
    clear_all_priorities,
    compute_content_hash,
)
from ..persistence import get_cluster, persist_cluster

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
    "add_thought_item",
    "add_tag",
    "remove_tag",
}

# ============================================================================
# Error Messages
# ============================================================================

ERROR_NO_BOARD = "No board found. Create one with organize_thoughts first."
ERROR_INVALID_OPERATION = "Invalid operation. Supported: set_priority, clear_priority, rename_cluster, rename_subcluster, delete_cluster, delete_subcluster, delete_thought_item, clear_all_priorities, add_thought_item, add_tag, remove_tag"
ERROR_MISSING_TARGET = "Target not specified. Provide target_name or item_index + parent_name."
ERROR_CLUSTER_NOT_FOUND = "Cluster '{name}' not found."
ERROR_SUBCLUSTER_NOT_FOUND = "Subcluster '{name}' not found in '{parent}'."
ERROR_ITEM_NOT_FOUND = "Item index {index} not found in '{parent}'."
ERROR_MISSING_NEW_NAME = "new_name required for rename operation."
ERROR_MISSING_RANK = "rank required for set_priority operation."
ERROR_PARENT_NOT_FOUND = "Parent '{parent}' not found."
ERROR_MISSING_TEXT = "text required for add_thought_item operation."
ERROR_MISSING_TAG = "tag required for add_tag/remove_tag operation."
ERROR_INVALID_TAG = f"Invalid tag. Must be one of: {', '.join(sorted(ALLOWED_TAGS))}"
ERROR_TAG_LIMIT = "'{name}' already has 3 tags (maximum). Remove a tag first."
ERROR_TAG_NOT_FOUND = "Tag '{tag}' not found on '{name}'."
ERROR_AMBIGUOUS_NAME = "'{name}' exists as both a cluster and subcluster. Please rename one to make it unique."
ERROR_NAME_COLLISION = "A cluster named '{name}' already exists. Choose a different name."
ERROR_SUBCLUSTER_NAME_COLLISION = "A subcluster named '{name}' already exists in '{parent}'. Choose a different name."
ERROR_TEXT_TOO_LONG = f"Text exceeds maximum length of {MAX_ITEM_LENGTH} characters."
ERROR_MIXED_MODE = "Use 'operation' (single) OR 'operations' (batch), not both."
ERROR_NO_OPERATION = "Provide 'operation' (single) or 'operations' (batch)."
ERROR_EMPTY_BATCH = "Batch operations list cannot be empty."

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "edit_board"

DESCRIPTION = """
Requires a board to exist in DB. Use organize_thoughts to create one. load_saved_board only displays the board — it does not create DB state.
The board is fetched automatically — do NOT pass a board field. Only pass operation(s) and targeting fields.

PURPOSE: Targeted, surgical edits to an existing board — one item at a time. Use for specific changes: add one item, rename one cluster, delete one item, set a priority. This is also the correct tool when the user provides a list of specific items to add to an existing cluster — do not use read_saved_board → organize_thoughts for this case.
Do NOT use this when the user wants to add many new thoughts or recluster the board. For that, use read_saved_board → merge thoughts → organize_thoughts.
Use this when user wants to MODIFY their current board, NOT CREATE A NEW ONE.

WHEN TO CALL:
- User says "add X to Y" (use add_thought_item)
- User says "add these items to my board" or "add these items to [cluster]" with a specific list → use add_thought_item in batch mode via operations array
- Use this for any targeted edits, even when multiple specific edits are requested at once
- User says "tag X as research" (use add_tag)
- User says "remove the research tag from X" (use remove_tag)
- User wants to REASSIGN OR SWAP an existing priority that is already set on the board (use set_priority). Example: "change my P2 to something else", "move P1 to the other cluster".
NEVER use set_priority if you are currently in a prioritization conversation — meaning the user just answered the criterion question or is still naming their priorities for the first time. In that case, always use start_prioritization_flow, even if the user's wording sounds like a direct board edit (e.g. "p2: Follow up on payments"). The prioritization conversation takes precedence over any general board-edit rule.
- User says "rename X to Y" (use rename_cluster/rename_subcluster)
- User says "delete X" or "remove X" (use delete_cluster/delete_subcluster/delete_thought_item)
- User says "clear my priorities" (use clear_all_priorities)
- User requests multiple changes at once (use operations array)
  Example: "Rename X to Y and make it P1" → batch with rename_cluster + set_priority

AFTER TOOL RETURNS: Confirm the change was made. Your board has been updated.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {
            "type": "string",
            "enum": ["set_priority", "clear_priority", "rename_cluster", "rename_subcluster", "delete_cluster", "delete_subcluster", "delete_thought_item", "clear_all_priorities", "add_thought_item", "add_tag", "remove_tag"],
            "description": "The edit operation to perform"
        },
        "target_name": {
            "type": "string",
            "description": "Cluster or subcluster name to target"
        },
        "parent_name": {
            "type": "string",
            "description": "Parent container name (for subclusters, thought items, and add_thought_item)"
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
        },
        "text": {
            "type": "string",
            "description": "For add_thought_item: the thought item text to add",
            "maxLength": MAX_ITEM_LENGTH
        },
        "tag": {
            "type": "string",
            "description": "For add_tag/remove_tag operations. Valid values: align, automate, decide, delegate, learn, research, test. Invalid values will be rejected with a clear error message."
        },
        "operations": {
            "type": "array",
            "description": "Batch mode: multiple operations applied in order. Use EITHER 'operation' (single) OR 'operations' (batch), not both.",
            "items": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": list(VALID_OPERATIONS)
                    },
                    "target_name": {"type": "string"},
                    "parent_name": {"type": "string"},
                    "item_index": {"type": "integer"},
                    "rank": {"type": "string", "enum": ["P1", "P2", "P3"]},
                    "new_name": {"type": "string"},
                    "text": {"type": "string"},
                    "tag": {"type": "string", "description": "For add_tag/remove_tag. Valid values: align, automate, decide, delegate, learn, research, test."}
                },
                "required": ["operation"],
                "additionalProperties": False,
            }
        }
    },
    "required": [],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["clarity.write"]

# ============================================================================
# Pydantic Models
# ============================================================================


class SingleOperation(BaseModel):
    """One edit operation (for batch mode)."""
    operation: str
    target_name: Optional[str] = None
    parent_name: Optional[str] = None
    item_index: Optional[int] = None
    rank: Optional[str] = None
    new_name: Optional[str] = None
    text: Optional[str] = None
    tag: Optional[str] = None

    @field_validator("item_index", mode="before")
    @classmethod
    def coerce_item_index(cls, v):
        """Coerce float to int (LLM sometimes sends 0.0 instead of 0)."""
        if v is None:
            return None
        if isinstance(v, float):
            return int(v)
        return v


class EditBoardRequest(BaseModel):
    """Request structure — single or batch mode (board fetched from DB)."""
    # Single mode
    operation: Optional[str] = None
    target_name: Optional[str] = None
    parent_name: Optional[str] = None
    item_index: Optional[int] = None
    rank: Optional[str] = None
    new_name: Optional[str] = None
    text: Optional[str] = None
    tag: Optional[str] = None
    # Batch mode
    operations: Optional[List[SingleOperation]] = None

    @field_validator("item_index", mode="before")
    @classmethod
    def coerce_item_index(cls, v):
        """Coerce float to int (LLM sometimes sends 0.0 instead of 0)."""
        if v is None:
            return None
        if isinstance(v, float):
            return int(v)
        return v


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


def _check_ambiguous_name(clusters: List[dict], name: str) -> Optional[str]:
    """
    Check if name exists as both a cluster and subcluster.

    Returns error message if ambiguous, None if OK.
    """
    cluster_names = {c.get("cluster_name") for c in clusters}
    subcluster_names = set()
    for c in clusters:
        for s in c.get("subclusters", []):
            subcluster_names.add(s.get("subcluster_name"))

    if name in cluster_names and name in subcluster_names:
        return ERROR_AMBIGUOUS_NAME.format(name=name)
    return None


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

    # Check for name collision (another cluster with the new name)
    existing = _find_cluster(result, new_name)
    if existing and existing is not cluster:
        return None, ERROR_NAME_COLLISION.format(name=new_name)

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

    # Check for name collision within same parent's subclusters
    parent_cluster_name = parent.get("cluster_name", "unknown")
    for sc in parent.get("subclusters", []):
        if sc.get("subcluster_name") == new_name and sc is not subcluster:
            return None, ERROR_SUBCLUSTER_NAME_COLLISION.format(name=new_name, parent=parent_cluster_name)

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


def _op_add_thought_item(clusters: List[dict], parent_name: Optional[str],
                         text: Optional[str], target_name: Optional[str] = None) -> tuple:
    """Add a thought item to a container."""
    # Fallback: LLM sometimes passes target_name instead of parent_name for add_thought_item
    if not parent_name and target_name:
        parent_name = target_name
    if not parent_name:
        return None, ERROR_PARENT_NOT_FOUND.format(parent="(empty)")
    if not text:
        return None, ERROR_MISSING_TEXT
    if len(text) > MAX_ITEM_LENGTH:
        return None, ERROR_TEXT_TOO_LONG

    # Check for ambiguous name
    error = _check_ambiguous_name(clusters, parent_name)
    if error:
        return None, error

    result = copy.deepcopy(clusters)
    container, _, _ = _find_container(result, parent_name)

    if not container:
        return None, ERROR_PARENT_NOT_FOUND.format(parent=parent_name)

    # Append as string (not object) per spec
    container.setdefault("thought_items", []).append(text)
    return result, None


def _op_add_tag(clusters: List[dict], target_name: Optional[str],
                tag: Optional[str]) -> tuple:
    """Add a tag to a container."""
    if not target_name:
        return None, ERROR_MISSING_TARGET
    if not tag:
        return None, ERROR_MISSING_TAG
    if tag not in ALLOWED_TAGS:
        return None, ERROR_INVALID_TAG

    # Check for ambiguous name
    error = _check_ambiguous_name(clusters, target_name)
    if error:
        return None, error

    result = copy.deepcopy(clusters)
    container, _, _ = _find_container(result, target_name)

    if not container:
        return None, ERROR_CLUSTER_NOT_FOUND.format(name=target_name)

    tags = container.get("tags", [])

    # Silently skip if tag already present (no duplicate)
    if tag in tags:
        return result, None

    # Check tag limit
    if len(tags) >= MAX_TAGS_PER_CONTAINER:
        return None, ERROR_TAG_LIMIT.format(name=target_name)

    tags.append(tag)
    container["tags"] = tags
    return result, None


def _op_remove_tag(clusters: List[dict], target_name: Optional[str],
                   tag: Optional[str]) -> tuple:
    """Remove a tag from a container."""
    if not target_name:
        return None, ERROR_MISSING_TARGET
    if not tag:
        return None, ERROR_MISSING_TAG

    # Check for ambiguous name
    error = _check_ambiguous_name(clusters, target_name)
    if error:
        return None, error

    result = copy.deepcopy(clusters)
    container, _, _ = _find_container(result, target_name)

    if not container:
        return None, ERROR_CLUSTER_NOT_FOUND.format(name=target_name)

    tags = container.get("tags", [])

    if tag not in tags:
        return None, ERROR_TAG_NOT_FOUND.format(tag=tag, name=target_name)

    tags.remove(tag)
    container["tags"] = tags
    return result, None


def _dispatch_operation(clusters: List[dict], op: SingleOperation) -> tuple:
    """Route operation to handler. Returns (updated_clusters, error)."""
    if op.operation == "set_priority":
        return _op_set_priority(clusters, op.target_name, op.parent_name, op.item_index, op.rank)
    elif op.operation == "clear_priority":
        return _op_clear_priority(clusters, op.target_name, op.parent_name, op.item_index)
    elif op.operation == "add_thought_item":
        return _op_add_thought_item(clusters, op.parent_name, op.text, op.target_name)
    elif op.operation == "add_tag":
        return _op_add_tag(clusters, op.target_name, op.tag)
    elif op.operation == "remove_tag":
        return _op_remove_tag(clusters, op.target_name, op.tag)
    elif op.operation == "rename_cluster":
        return _op_rename_cluster(clusters, op.target_name, op.new_name)
    elif op.operation == "rename_subcluster":
        return _op_rename_subcluster(clusters, op.target_name, op.parent_name, op.new_name)
    elif op.operation == "delete_cluster":
        return _op_delete_cluster(clusters, op.target_name)
    elif op.operation == "delete_subcluster":
        return _op_delete_subcluster(clusters, op.target_name, op.parent_name)
    elif op.operation == "delete_thought_item":
        return _op_delete_thought_item(clusters, op.parent_name, op.item_index)
    elif op.operation == "clear_all_priorities":
        return _op_clear_all_priorities(clusters)
    else:
        return None, ERROR_INVALID_OPERATION


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Edit an existing board with single or batch operations.

    Args:
        user_id: Authenticated user ID from JWT
        correlation_id: Request correlation ID for tracing
        arguments: { operation: "..." } for single mode
                   { operations: [...] } for batch mode

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
                text="Invalid input format. Please provide operation."
            )],
            isError=True,
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

    # CRITICAL: Check empty batch FIRST (before mode detection)
    if request.operations is not None and len(request.operations) == 0:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=ERROR_EMPTY_BATCH)],
            isError=True,
        )

    # Determine mode
    if request.operations and request.operation:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=ERROR_MIXED_MODE)],
            isError=True,
        )

    if not request.operations and not request.operation:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=ERROR_NO_OPERATION)],
            isError=True,
        )

    # Build ops list
    if request.operations:
        ops = request.operations
    else:
        # Wrap single op
        ops = [SingleOperation(
            operation=request.operation,
            target_name=request.target_name,
            parent_name=request.parent_name,
            item_index=request.item_index,
            rank=request.rank,
            new_name=request.new_name,
            text=request.text,
            tag=request.tag,
        )]

    # Validate all operations
    for op in ops:
        if op.operation not in VALID_OPERATIONS:
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(type="text", text=ERROR_INVALID_OPERATION)],
                isError=True,
            )

    # Execute in order — fail fast
    completed = []

    for i, op in enumerate(ops):
        result, error = _dispatch_operation(clusters_data, op)
        if error:
            # Report which operation failed (1-indexed for user clarity)
            logger.warning("edit_board.operation_failed",
                          user_id=user_id,
                          operation=op.operation,
                          index=i + 1,
                          error=error)
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text=f"Operation {i + 1} ({op.operation}) failed: {error}"
                )],
                isError=True,
            )
        clusters_data = result
        completed.append(op.operation)

    # ============================================================
    # AUTO-PERSIST UPDATED BOARD TO DB (fatal on failure)
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
        logger.info("edit_board.auto_persisted", user_id=user_id)
    except Exception as e:
        logger.error("edit_board.persist_failed", user_id=user_id, error=str(e))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Your edits could not be saved."
            )],
            structuredContent={
                "success": False,
                "error": "persist_failed",
                "assistant_guidance": {
                    "action": "RETRY",
                    "instruction": (
                        "Edit operations succeeded but could not be saved to the database. "
                        "Tell the user their edits were not saved and ask them to try again. "
                        "Do NOT imply the board was updated."
                    ),
                },
            },
            isError=True,
        )

    # Enrich for widget display
    enriched = enrich_clusters(clusters_data)

    # Build success message
    if len(completed) == 1:
        # Single operation — use detailed message
        operation_messages = {
            "set_priority": f"Set {request.rank} on target.",
            "clear_priority": "Priority cleared.",
            "rename_cluster": f"Renamed cluster to '{request.new_name}'.",
            "rename_subcluster": f"Renamed subcluster to '{request.new_name}'.",
            "delete_cluster": f"Deleted cluster '{request.target_name}'.",
            "delete_subcluster": f"Deleted subcluster '{request.target_name}'.",
            "delete_thought_item": "Deleted thought item.",
            "clear_all_priorities": "All priorities cleared.",
            "add_thought_item": f"Added '{request.text}' to '{request.parent_name or request.target_name}'.",
            "add_tag": f"Added tag '{request.tag}' to '{request.target_name}'.",
            "remove_tag": f"Removed tag '{request.tag}' from '{request.target_name}'.",
        }
        message = operation_messages.get(completed[0], "Edit complete.")
    else:
        # Batch mode — summary message
        message = f"Completed {len(completed)} edits: {', '.join(completed)}."

    logger.info("edit_board.success",
               user_id=user_id,
               operations=completed)

    # Widget metadata
    meta = {
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Editing board...",
        "openai/toolInvocation/invoked": "Board updated.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }

    # Guidance for all operations
    guidance = (
        f"Say one short sentence acknowledging what you found and what changed — "
        f"example: 'Found your board with {len(clusters_data)} clusters. Done, [edit description].' "
        "Then confirm the edit briefly and continue with whatever you were doing with the user."
    )

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=message)],
        structuredContent={
            "clusters": enriched,
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
    destructive_hint=True,  # Overwrites saved board state in DB
    open_world_hint=False,  # Only affects internal backend
))
