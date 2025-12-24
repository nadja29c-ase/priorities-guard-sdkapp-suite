"""
Organize Thoughts Tool.

Organizes user's thoughts, ideas, tasks into visual clusters for cognitive ease.
Self-registers at import time.

NOTE: As of Increment 12, this tool is PURE (no DB persistence).
      Use save_board to explicitly save the board.
"""

import re
import json
from typing import List

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, Field, ValidationError, model_validator

from .base import ToolDefinition
from . import register_tool
from .board_utils import ALLOWED_TAGS
from ..tool_logic import organize_thoughts as format_clusters  # Renamed from cluster_raw_thoughts
from ..handlers.resources import WIDGET_URI
from ..mcp_auth import build_invalid_params_error

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

DESCRIPTION = """
YOUR ROLE: EMPATHIC FACILITATOR. YOU BACKTRACK THE USER AND ASK QUESTIONS AND HELP USERS THINK - THIS UNLOCKS CLARITY. 

TOOL PURPOSE: Organize user's thoughts into visual clusters to reduce cognitive load - getting the full picture is absolutely necessary before prioritizing it also create mental space and emotional relief. This tool renders a board widget.
CRITICAL: STOP! YOU NEVER EVER TELL THE USER WHAT TO DO, PRIORITIZE OR PLAN when using this tool! If the user asks something that would normally trigger advice, you must STOP and say "My role is to facilitate YOUR thinking. Let's focus on organizing your thoughts first. Once we have a clear picture, we can explore next steps together."

WHEN TO CALL:
- Call after user expresses 5+ thought items RELATED TO PRODUCTIVITY (tasks, chores, thoughts, ideas). Include ALL thoughts — never filter.
- Until user says "That's all. Nothing else on my mind"
- When user wants to merge boards, combine and recluster thought items into one board.
- When user asks you "help me organize my thoughts", "help me sort my tasks", "help me find focus", "help me declutter my mind", "help me understand what to focus on" or similar.

WHEN NOT TO CALL:
- when user wants to sort through emotional and personal dilemmas, or relationship problems.

AFTER TOOL RETURNS: Follow the assistant_guidance in structuredContent for what to say.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "thoughts_exhausted": {
            "type": "boolean",
            "description": "Default false. Set true only when user has no more thought items."
        },
        "clusters": {
            "type": "array",
            "description": "List of clusters. Each cluster can use thought_items (flat), subclusters (nested), or both (mixed).",
            "items": {
                "type": "object",
                "properties": {
                    "cluster_name": {
                        "type": "string",
                        "description": "Cluster titel describing the common theme of its thought items, ideally as an intention or outcome."
                    },
                    "thought_items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Direct thought items (use for flat clusters without subclusters)"
                    },
                    "subclusters": {
                        "type": "array",
                        "description": "Nested groupings within cluster (use for complex clusters instead of thought_items)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "subcluster_name": {
                                    "type": "string",
                                    "description": "Name of the subcluster"
                                },
                                "thought_items": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Thought items in this subcluster"
                                },
                                "tags": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": sorted(ALLOWED_TAGS),
                                        "description": "decide=choices needing resolution, research=unknowns to investigate, test=assumptions to validate, delegate=work for others, automate=repetitive work, learn=skill gaps, align=needs discussion with others"
                                    },
                                    "maxItems": 3,
                                    "description": "Optional. Only tag when user intent is clear and dominant."
                                }
                            },
                            "required": ["subcluster_name", "thought_items"]
                        }
                    },
                    "tags": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": sorted(ALLOWED_TAGS),
                            "description": "decide=choices needing resolution, research=unknowns to investigate, test=assumptions to validate, delegate=work for others, automate=repetitive work, learn=skill gaps, align=needs discussion with others"
                        },
                        "maxItems": 3,
                        "description": "Optional. Only tag when user intent is clear and dominant."
                    }
                },
                "required": ["cluster_name"]
            }
        }
    },
    "required": ["clusters"]  # thoughts_exhausted defaults to false if missing
}

REQUIRED_SCOPES = ["clarity.write"]

# ALLOWED_TAGS imported from board_utils.py (single source of truth)

# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class SubclusterInput(BaseModel):
    """Expected structure for each subcluster within a cluster."""
    subcluster_name: str
    thought_items: List[str]
    tags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_subcluster(self) -> "SubclusterInput":
        """Validate subcluster has items and valid tags."""
        if len(self.thought_items) == 0:
            raise ValueError(
                f"Subcluster '{self.subcluster_name}' has no thought_items. "
                "Subclusters must contain at least one thought item."
            )
        if len(self.tags) > 3:
            raise ValueError(
                f"Subcluster '{self.subcluster_name}' has {len(self.tags)} tags. Maximum is 3."
            )
        for tag in self.tags:
            if tag not in ALLOWED_TAGS:
                raise ValueError(
                    f"Invalid tag '{tag}'. Allowed: {', '.join(ALLOWED_TAGS)}"
                )
        return self


class ClusterInput(BaseModel):
    """Expected structure for each cluster from ChatGPT."""
    cluster_name: str
    thought_items: List[str] = Field(default_factory=list)
    subclusters: List[SubclusterInput] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_cluster(self) -> "ClusterInput":
        """Validate cluster has content and valid tags."""
        has_items = len(self.thought_items) > 0
        has_subclusters = len(self.subclusters) > 0

        if not has_items and not has_subclusters:
            raise ValueError(
                f"Cluster '{self.cluster_name}' is empty. Must have thought_items or subclusters."
            )
        if len(self.tags) > 3:
            raise ValueError(
                f"Cluster '{self.cluster_name}' has {len(self.tags)} tags. Maximum is 3."
            )
        for tag in self.tags:
            if tag not in ALLOWED_TAGS:
                raise ValueError(
                    f"Invalid tag '{tag}'. Allowed: {', '.join(ALLOWED_TAGS)}"
                )
        return self


class ClusterRequest(BaseModel):
    """Expected top-level structure from ChatGPT."""
    thoughts_exhausted: bool = False  # Default: user may have more thoughts
    clusters: List[ClusterInput]


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Handle organize_thoughts tool call.

    Args:
        user_id: Authenticated user ID from JWT
        correlation_id: Request correlation ID for tracing
        arguments: Raw arguments from ChatGPT

    Returns:
        CallToolResult with clustered data and widget metadata
    """
    logger.debug("organize_thoughts.handle.start",
                user_id=user_id,
                correlation_id=correlation_id,
                argument_keys=list(arguments.keys()))

    validated_request = None

    # ============================================================
    # VALIDATION
    # ============================================================
    try:
        validated_request = ClusterRequest.model_validate(arguments)

        subcluster_count = sum(len(c.subclusters) for c in validated_request.clusters)
        tag_count = sum(len(c.tags) for c in validated_request.clusters) + sum(
            len(sc.tags) for c in validated_request.clusters for sc in c.subclusters
        )

        logger.debug("organize_thoughts.validation_success",
                    cluster_count=len(validated_request.clusters),
                    subcluster_count=subcluster_count,
                    tag_count=tag_count,
                    thoughts_exhausted=validated_request.thoughts_exhausted)

    except ValidationError as e:
        # ---------------------------------------------------------------
        # LLM Error Compensation - repair common malformed inputs
        # ---------------------------------------------------------------
        logger.warning("organize_thoughts.validation_failed_attempt_repair",
                      error=str(type(e).__name__),
                      details=str(e.errors()))

        clusters_data = None
        thoughts_exhausted = arguments.get("thoughts_exhausted", False)  # Default: user may have more
        raw_clusters = arguments.get("clusters", [])

        # Repair: invalid tags -> strip tags not in ALLOWED_TAGS
        # This handles ChatGPT using cached schemas with removed tags
        if raw_clusters and isinstance(raw_clusters, list) and isinstance(raw_clusters[0], dict):
            repaired_clusters = []
            tags_stripped = False
            for cluster in raw_clusters:
                if not isinstance(cluster, dict):
                    continue
                repaired = dict(cluster)
                # Strip invalid tags from cluster
                if "tags" in repaired and isinstance(repaired["tags"], list):
                    valid_tags = [t for t in repaired["tags"] if t in ALLOWED_TAGS]
                    if len(valid_tags) != len(repaired["tags"]):
                        tags_stripped = True
                    repaired["tags"] = valid_tags
                # Strip invalid tags from subclusters
                if "subclusters" in repaired and isinstance(repaired["subclusters"], list):
                    for subcluster in repaired["subclusters"]:
                        if isinstance(subcluster, dict) and "tags" in subcluster:
                            if isinstance(subcluster["tags"], list):
                                valid_sub_tags = [t for t in subcluster["tags"] if t in ALLOWED_TAGS]
                                if len(valid_sub_tags) != len(subcluster["tags"]):
                                    tags_stripped = True
                                subcluster["tags"] = valid_sub_tags
                repaired_clusters.append(repaired)
            if tags_stripped and repaired_clusters:
                logger.info("organize_thoughts.repair_stripped_invalid_tags")
                clusters_data = repaired_clusters

        # Repair: raw strings list -> wrap into single flat cluster
        if raw_clusters and isinstance(raw_clusters[0], str):
            clusters_data = [{
                "cluster_name": "Tasks",
                "thought_items": raw_clusters,
                "subclusters": []
            }]

        # Repair: content field -> extract items into single flat cluster
        elif isinstance(arguments.get("content"), str):
            items = re.split(r'[\n•\-\*]|(?:\d+\.)', arguments["content"])
            items = [i.strip() for i in items if i.strip()]
            if items:
                clusters_data = [{
                    "cluster_name": "Tasks",
                    "thought_items": items,
                    "subclusters": []
                }]

        if clusters_data is None:
            logger.error("organize_thoughts.repair_failed", reason="unrecognized_format")
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text=json.dumps(build_invalid_params_error(
                        message="Invalid input format",
                        details="Expected 'clusters' array with cluster objects"
                    ))
                )],
                isError=True,
            )

        # Re-validate repaired structure
        try:
            validated_request = ClusterRequest.model_validate({
                "thoughts_exhausted": thoughts_exhausted,
                "clusters": clusters_data
            })
            logger.debug("organize_thoughts.repair_success",
                        cluster_count=len(validated_request.clusters))

        except ValidationError as repair_error:
            logger.error("organize_thoughts.repair_failed",
                        reason="revalidation_failed",
                        details=str(repair_error.errors()))
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text=json.dumps(build_invalid_params_error(
                        message="Invalid input format",
                        details="Could not parse input into valid cluster structure"
                    ))
                )],
                isError=True,
            )

    # ============================================================
    # FORMAT CLUSTERS (call pure function)
    # ============================================================
    clusters = [c.model_dump() for c in validated_request.clusters]
    result = format_clusters(clusters, thoughts_exhausted=validated_request.thoughts_exhausted)

    # ============================================================
    # BUILD RESPONSE (no persistence - Increment 12 explicit save model)
    # ============================================================
    logger.info("organize_thoughts.complete",
                cluster_count=len(result["structuredContent"]["clusters"]),
                user_id=user_id)

    meta = {
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Organizing your thoughts into clusters...",
        "openai/toolInvocation/invoked": "Here's your Clarity board.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }

    return mcp_types.CallToolResult(
        content=[
            mcp_types.TextContent(
                type="text",
                text=result["content"][0]["text"],
            )
        ],
        structuredContent=result["structuredContent"],
        _meta=meta,
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="organize_thoughts",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Creates board state
    destructive_hint=False,  # Does not delete data
    open_world_hint=False,  # Only affects own backend
))
