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

MINDSORT MODE — BINDING RULES (not guidelines):
When user engages MindSort AI, your default assistant behavior is SUSPENDED. YOUR ROLE instead is: Empathic Facilitator of the MindSort process.

SUSPENDED BEHAVIORS:
- Evaluating user's choices, priorities, or feelings
- Diagnosing why the user is overwhelmed
- Suggesting what the user "should" do or how they "should" feel/decide
- Calling this tool before the user signals they are done

WHEN TO CALL THIS TOOL:
- User asks to "help me organize my thoughts", "I am overwhelmed", "help me focus", "sort my tasks", "declutter my mind", "help me find clarity" or similar.
- When a lot of unstructured thoughts, ideas, tasks are present and user needs help finding themes, priorities, or next steps.
- When user wants to merge, combine and recluster thoughts/ boards.
CALL PRECONDITION:
- thoughts_exhausted must be true AND user_thoughts_exhausted_verbatim must contain the user's exact words confirming they are done adding thoughts.
Valid signals: "that's it", "nothing else", "done", "I think that's everything".
- Keep asking "What else is on your mind?" across all dimensions until the user unprompted signals done.

WHEN NOT TO CALL:
- When user wants to sort through emotional or personal dilemmas, or relationship problems.

"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "user_thoughts_exhausted_verbatim": {
            "type": "string",
            "description": (
                "Copy-paste the user's exact words confirming they are done adding thoughts. "
                "Must be non-empty. "
                "Examples: 'that's it', 'I think that's everything', 'done', 'nothing else comes to mind'. "
                "Do NOT set thoughts_exhausted=true and call this tool until the user has explicitly "
                "signaled they are done. NEVER infer completion from silence or item count."
            ),
            "minLength": 1,
        },
        "thoughts_exhausted": {
            "type": "boolean",
            "description": "Default false. Set true only when user has no more thought items to organize."
        },
        "clusters": {
            "type": "array",
            "description": "List of clusters. Each cluster can use thought_items (flat), subclusters (nested), or both (mixed).",
            "items": {
                "type": "object",
                "properties": {
                    "cluster_name": {
                        "type": "string",
                        "description": (
                            "Cluster name describing the common theme of its thought items. "
                            "Use descriptive, specific names — not generic categories. "
                            "BAD: 'Marketing & PR', 'Work', 'Personal', 'Health'. "
                            "GOOD: 'Launch Q2 campaign', 'Finish client deliverables', 'Plan birthday weekend'. "
                            "When unsure, use the user's exact phrasing."
                        ),
                    },
                    "thought_items": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "description": "Direct thought items. Minimum 2 — a single item is not a cluster. If only 1 item exists, merge it into another cluster."
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
                                    "minItems": 2,
                                    "description": "Thought items in this subcluster. Minimum 2 — a single item is not a cluster."
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
                            "required": ["subcluster_name", "thought_items"],
                            "additionalProperties": False,
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
                "required": ["cluster_name"],
                "additionalProperties": False,
            }
        }
    },
    "required": ["user_thoughts_exhausted_verbatim", "clusters"],
    "additionalProperties": False,
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
        if len(self.thought_items) < 2:
            raise ValueError(
                f"Subcluster '{self.subcluster_name}' has only {len(self.thought_items)} item. "
                "Minimum 2 required — merge into another cluster."
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
        if has_items and len(self.thought_items) < 2:
            raise ValueError(
                f"Cluster '{self.cluster_name}' has only {len(self.thought_items)} item. "
                "Minimum 2 required — merge into another cluster."
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
# Provenance Guidance
# ============================================================================

GUIDANCE_EMPTY_THOUGHTS_EXHAUSTED_VERBATIM = (
    "user_thoughts_exhausted_verbatim is empty. Do NOT call this tool yet. "
    "Return to the conversation and continue eliciting thoughts from the user."
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

    # ============================================================
    # PROVENANCE CHECK (behavioral gate)
    # ============================================================
    user_thoughts_exhausted_verbatim = arguments.get("user_thoughts_exhausted_verbatim", "")
    if not user_thoughts_exhausted_verbatim or not user_thoughts_exhausted_verbatim.strip():
        logger.info("organize_thoughts.provenance_failed",
                    user_id=user_id,
                    field="user_thoughts_exhausted_verbatim")
        return _build_provenance_error(
            "empty_thoughts_exhausted_verbatim",
            GUIDANCE_EMPTY_THOUGHTS_EXHAUSTED_VERBATIM,
        )

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
    read_only_hint=True,  # Transforms input into clusters, no DB write
    destructive_hint=False,  # N/A when read_only=True
    open_world_hint=False,  # Only affects internal backend
))
