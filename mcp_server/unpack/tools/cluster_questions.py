"""
Cluster Questions Tool.

Validates ChatGPT-clustered questions and generates summary for export.
Self-registers at import time.

Pattern: ChatGPT clusters → Tool validates and generates markdown summary.
"""

from typing import List

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, Field, ValidationError

from .base import ToolDefinition, ToolUsageError
from . import register_tool
from ..tool_logic import (
    cluster_questions as process_clusters,
    MissingProblemStatementError,
    InsufficientQuestionsError,
    InvalidClustersError,
)

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

from ..handlers.resources import WIDGET_URI

NAME = "cluster_questions"

DESCRIPTION = """
Presents the user the results of their questions brainstorming, clustered by theme.

WHEN TO CALL:
- AFTER User has confirmed their problem statement
- AFTER User has explicitly communicated that the user is done with the brainstorming

BEFORE CALLING:
1. Group questions by semantic similarity — what do they have in common?
2. Name each cluster with a short THEME that captures the shared meaning
3. Questions that don't fit any group go in "unclustered"

RULES:
- Themes should be descriptive, not generic ("Understanding the behavior" not "Questions")
- A cluster needs at least 2 questions (single questions go to unclustered)

AFTER WIDGET RENDERS:
- Give a brief observation about what you notice in the clusters
- Ask: 'Which area would you like to explore further?'
- Do NOT offer advice or solutions
- Wait for user to select a cluster
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "problem_statement": {
            "type": "string",
            "description": "The confirmed problem statement from formulate_problem"
        },
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "theme": {
                        "type": "string",
                        "description": "Theme capturing what these questions have in common"
                    },
                    "questions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "Questions belonging to this cluster"
                    }
                },
                "required": ["theme", "questions"]
            },
            "description": "Questions grouped by semantic similarity"
        },
        "unclustered": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Questions that don't fit any cluster",
            "default": []
        }
    },
    "required": ["problem_statement", "clusters"],
    "additionalProperties": False
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class ClusterInput(BaseModel):
    """A single cluster of semantically similar questions."""
    theme: str = Field(description="Theme capturing what these questions have in common")
    questions: List[str] = Field(min_length=1, description="Questions in this cluster")


class ClusterQuestionsInput(BaseModel):
    """Expected structure from ChatGPT."""
    problem_statement: str = Field(description="Confirmed problem statement")
    clusters: List[ClusterInput] = Field(description="Questions grouped by semantic similarity")
    unclustered: List[str] = Field(default=[], description="Questions that don't fit any cluster")


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Handle cluster_questions tool call.

    Args:
        user_id: Empty string (Unpack uses noauth)
        correlation_id: Request correlation ID for tracing
        arguments: ChatGPT-clustered questions

    Returns:
        CallToolResult with validated clusters and summary markdown
    """
    logger.debug("cluster_questions.handle.start",
                correlation_id=correlation_id,
                argument_keys=list(arguments.keys()))

    # ============================================================
    # VALIDATION
    # ============================================================
    try:
        validated = ClusterQuestionsInput.model_validate(arguments)
        logger.debug("cluster_questions.validation_success",
                    correlation_id=correlation_id,
                    cluster_count=len(validated.clusters))

    except ValidationError as e:
        logger.warning("cluster_questions.validation_failed",
                      correlation_id=correlation_id,
                      error=str(e.errors()))
        raise ToolUsageError(
            "I couldn't process the clusters. Make sure you have at least 5 questions "
            "and each cluster has a theme and questions."
        )

    # ============================================================
    # PROCESS CLUSTERS (call pure function)
    # ============================================================
    try:
        result = process_clusters(
            problem_statement=validated.problem_statement,
            clusters=[c.model_dump() for c in validated.clusters],
            unclustered=validated.unclustered,
        )

    except MissingProblemStatementError:
        logger.warning("cluster_questions.missing_problem_statement",
                      correlation_id=correlation_id)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Missing problem statement."
            )],
            structuredContent={
                "error_type": "missing_problem_statement",
                "assistant_guidance": {
                    "action": "RESTART_FLOW",
                    "instruction": "The problem statement is missing. Ask the user to describe their problem first."
                }
            },
            isError=True,
        )

    except InsufficientQuestionsError as e:
        logger.warning("cluster_questions.insufficient_questions",
                      correlation_id=correlation_id,
                      count=e.extra.get("count", 0))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Insufficient questions for clustering."
            )],
            structuredContent={
                "error_type": "insufficient_questions",
                "count": e.extra.get("count", 0),
                "required_minimum": 5,
                "assistant_guidance": {
                    "action": "REQUEST_MORE_QUESTIONS",
                    "instruction": "Tell the user you need at least 5 questions to find patterns. Ask what other questions come to mind."
                }
            },
            isError=True,
        )

    except InvalidClustersError as e:
        logger.warning("cluster_questions.invalid_clusters",
                      correlation_id=correlation_id,
                      detail=e.detail)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Invalid cluster structure."
            )],
            structuredContent={
                "error_type": "invalid_clusters",
                "detail": e.detail or "Unknown issue",
                "assistant_guidance": {
                    "action": "RETRY_CLUSTERING",
                    "instruction": "Re-cluster the questions ensuring each cluster has a theme and at least one question."
                }
            },
            isError=True,
        )

    # ============================================================
    # BUILD SUCCESS RESPONSE
    # ============================================================
    clusters = result["clusters"]
    unclustered = result["unclustered"]
    summary_markdown = result["summary_markdown"]
    total_questions = result["total_questions"]

    logger.info("cluster_questions.complete",
                correlation_id=correlation_id,
                cluster_count=len(clusters),
                unclustered_count=len(unclustered),
                total_questions=total_questions)

    # Widget metadata for OpenAI rendering (matches Clarity pattern)
    meta = {
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Clustering your questions...",
        "openai/toolInvocation/invoked": "Here's your Unpack summary.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Clustered {total_questions} questions into {len(clusters)} groups."
        )],
        structuredContent={
            "problem_statement": validated.problem_statement,
            "clusters": clusters,
            "unclustered": unclustered,
            "summary_markdown": summary_markdown,
            "assistant_guidance": {
                "action": "WIDGET_RENDERED",
                "next_step": "SELECT_CLUSTER",
            },
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
    widget_uri=WIDGET_URI,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=True,  # Transforms input, no side effects
    destructive_hint=False,
    open_world_hint=False,
))
