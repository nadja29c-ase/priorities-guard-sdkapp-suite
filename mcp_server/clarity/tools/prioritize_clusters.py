"""
Prioritize Clusters Tool.

Allows user to mark MAX 3 clusters or subclusters as P1/P2/P3.
Updates widget to visually highlight priorities and reorder display.

Self-registers at import time.

Role boundaries:
- LLM: Facilitates goal elicitation, prompts user to identify priorities
- User: Decides WHAT is prioritized
- Tool: Receives final decisions, updates widget (execution only)
"""

from typing import List, Optional
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

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "prioritize_clusters"

DESCRIPTION = """
Marks up to 3 clusters or subclusters as P1/P2/P3 priorities.
This tool applies priorities to the board provided in the input, so that the user can identify what to focus on and derive specific action steps FROM there.

WHEN TO CALL:
- After user exhausted ALL thoughts AND ALL thoughts have been organized into a board
- After USER explicitly names clusters/subclusters and confirms ranking
- USER says "Priority 1 is X, Priority 2 is Y" or similar explicit prioritization
- When the user asks "what now" or "I have too much to do and I am still overwhelmed" or "I still don't know what to do next"

DO NOT CALL:
- NEVER infer or guess priorities or provide priorities on behalf of the user
- Only call after the user explicitly names priorities in form of clusters/subclusters and confirms ranking

FACILITATION SEQUENCE:
1. Ask about goals: "What are you trying to achieve RIGHT NOW?"
2. If user has no explicit goals: Ask about BLOCKERS: "What's stuck? What would unblock the most?"
3. Prompt identification: "Based on what you've shared, which clusters feel most important? Pick up to 3."
4. Prompt ranking: "Of those, which is #1?"
5. ONLY call this tool after EXPLICIT user decisions

INPUT:
- clusters: The current board that is subject of the conversation (from organize_thoughts or load_saved_board)
- priorities: Array of { cluster_name OR subcluster_name, rank (P1/P2/P3), reason (optional) }

OUTPUT:
- Board with priority metadata embedded in cluster/subcluster objects
- Widget renders with green highlights and rank badges
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
            "description": "Priority assignments (max 3). Use cluster_name for clusters, subcluster_name for subclusters.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The cluster_name or subcluster_name to prioritize"
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
                "required": ["name", "rank"]
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
    """A single priority assignment."""
    name: str
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


class SubclusterInput(BaseModel):
    """Subcluster structure."""
    subcluster_name: str
    thought_items: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    priority: Optional[dict] = None  # Will be added by tool


class ClusterInput(BaseModel):
    """Cluster structure."""
    cluster_name: str
    thought_items: List[str] = Field(default_factory=list)
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


def _validate_priorities(
    priorities: List[PriorityInput],
    cluster_names: set,
    subcluster_names: set,
    subcluster_to_parent: dict
) -> Optional[str]:
    """
    Validate priority assignments.

    Returns error message if invalid, None if valid.
    """
    # Check max priorities
    if len(priorities) > MAX_PRIORITIES:
        return ERROR_TOO_MANY_PRIORITIES

    # Check for duplicate ranks
    ranks_used = set()
    for p in priorities:
        if p.rank in ranks_used:
            return ERROR_DUPLICATE_RANK
        ranks_used.add(p.rank)

    # Check all names are valid and track what's prioritized
    prioritized_clusters = set()
    prioritized_subclusters = set()

    for p in priorities:
        if p.name in cluster_names:
            prioritized_clusters.add(p.name)
        elif p.name in subcluster_names:
            prioritized_subclusters.add(p.name)
        else:
            return ERROR_INVALID_CLUSTER

    # Check for parent + child conflict
    for sub_name in prioritized_subclusters:
        parent_name = subcluster_to_parent.get(sub_name)
        if parent_name and parent_name in prioritized_clusters:
            return ERROR_PARENT_AND_CHILD

    return None


def _apply_priorities(clusters: List[dict], priorities: List[PriorityInput]) -> List[dict]:
    """
    Apply priority metadata to clusters and subclusters.

    Returns deep copy of clusters with priority fields added.
    """
    # Build lookup: name -> priority
    priority_map = {p.name: {"rank": p.rank, "reason": p.reason} for p in priorities}

    # Deep copy to avoid mutating input
    result = copy.deepcopy(clusters)

    for cluster in result:
        cluster_name = cluster.get("cluster_name", "")

        # Apply cluster priority
        if cluster_name in priority_map:
            cluster["priority"] = priority_map[cluster_name]
        else:
            cluster["priority"] = None

        # Apply subcluster priorities
        for subcluster in cluster.get("subclusters", []):
            sub_name = subcluster.get("subcluster_name", "")
            if sub_name in priority_map:
                subcluster["priority"] = priority_map[sub_name]
            else:
                subcluster["priority"] = None

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

    guidance = (
        "Mirror back briefly: what clusters emerged, what was/seemed important to the user. "
        "Then say: 'That's your Clarity board — ready to be saved and revisited. "
        "You can come back to your board anytime by asking to load it. "
        "From here we're just chatting — ask me anything or close when you're done.' "
        "Then answer naturally."
    )

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
