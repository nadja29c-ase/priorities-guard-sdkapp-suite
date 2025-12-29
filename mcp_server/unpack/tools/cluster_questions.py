"""
Cluster Questions Tool.

Validates ChatGPT-clustered questions and generates summary for export.
Self-registers at import time.

Pattern: ChatGPT clusters → Tool validates and enriches with insights + markdown.
"""

from typing import List

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, Field, ValidationError

from .base import ToolDefinition, ToolUsageError
from . import register_tool
from ..tool_logic import cluster_questions as process_clusters

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "cluster_questions"

DESCRIPTION = """
Validates clustered questions and generates summary for export.

WHEN TO CALL:
- User has confirmed their problem statement
- User has generated at least 3 questions
- User has signaled they are done brainstorming
- You have clustered the questions by uncertainty type

BEFORE CALLING:
1. Collect all questions from the brainstorming session
2. Group questions semantically into clusters by uncertainty type
3. Assign each cluster:
   - label: A short name describing what these questions are about
   - uncertainty_type: One of [causes, constraints, unknowns, dependencies, risks, options]
   - questions: The questions belonging to this cluster
4. Put questions that don't fit cleanly into "unclustered"

UNCERTAINTY TYPES:
- causes: Questions about WHY something happens
- constraints: Questions about what LIMITS options
- unknowns: Questions about MISSING INFORMATION
- dependencies: Questions about OTHER PEOPLE or factors
- risks: Questions about what could GO WRONG
- options: Questions about POSSIBLE PATHS forward

RULES:
- Minimum 3 questions total required
- Questions may remain unclustered if they don't fit any type
- Do NOT force questions into ill-fitting clusters
- Do NOT call if fewer than 3 questions collected
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "problem_statement": {
            "type": "string",
            "description": "The confirmed problem statement from formulate_problem"
        },
        "questions": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "description": "All questions collected during brainstorming"
        },
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {
                        "type": "string",
                        "description": "Short name describing what these questions are about"
                    },
                    "uncertainty_type": {
                        "type": "string",
                        "enum": ["causes", "constraints", "unknowns", "dependencies", "risks", "options"],
                        "description": "Type of uncertainty these questions represent"
                    },
                    "questions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "description": "Questions belonging to this cluster"
                    }
                },
                "required": ["label", "uncertainty_type", "questions"]
            },
            "description": "Questions grouped by uncertainty type (clustered by ChatGPT)"
        },
        "unclustered": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Questions that don't fit any uncertainty type cleanly",
            "default": []
        }
    },
    "required": ["problem_statement", "questions", "clusters"],
    "additionalProperties": False
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class ClusterInput(BaseModel):
    """A single cluster from ChatGPT."""
    label: str = Field(description="Short name for the cluster")
    uncertainty_type: str = Field(description="Type of uncertainty")
    questions: List[str] = Field(min_length=1, description="Questions in this cluster")


class ClusterQuestionsInput(BaseModel):
    """Expected structure from ChatGPT."""
    problem_statement: str = Field(description="Confirmed problem statement")
    questions: List[str] = Field(description="All questions collected")  # min 3 validated in logic
    clusters: List[ClusterInput] = Field(description="ChatGPT-clustered questions")
    unclustered: List[str] = Field(default=[], description="Questions that don't fit")


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
        CallToolResult with validated clusters, insights, and summary markdown
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
                    question_count=len(validated.questions),
                    cluster_count=len(validated.clusters))

    except ValidationError as e:
        logger.warning("cluster_questions.validation_failed",
                      correlation_id=correlation_id,
                      error=str(e.errors()))
        raise ToolUsageError(
            "I couldn't process the clusters. Make sure you have at least 3 questions "
            "and each cluster has a label, uncertainty type, and questions."
        )

    # ============================================================
    # PROCESS CLUSTERS (call pure function)
    # ============================================================
    result = process_clusters(
        problem_statement=validated.problem_statement,
        questions=validated.questions,
        clusters=[c.model_dump() for c in validated.clusters],
        unclustered=validated.unclustered,
    )

    # ============================================================
    # HANDLE ERRORS FROM LOGIC
    # ============================================================
    if result.get("error"):
        error_type = result.get("error_type", "unknown")

        if error_type == "missing_problem_statement":
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

        elif error_type == "insufficient_questions":
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text="Insufficient questions for clustering."
                )],
                structuredContent={
                    "error_type": "insufficient_questions",
                    "count": result.get("count", 0),
                    "required_minimum": 3,
                    "assistant_guidance": {
                        "action": "REQUEST_MORE_QUESTIONS",
                        "instruction": "Tell the user you need at least 3 questions to find patterns. Ask what other questions come to mind."
                    }
                },
                isError=True,
            )

        elif error_type == "invalid_clusters":
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text="Invalid cluster structure."
                )],
                structuredContent={
                    "error_type": "invalid_clusters",
                    "detail": result.get("detail", "Unknown issue"),
                    "assistant_guidance": {
                        "action": "RETRY_CLUSTERING",
                        "instruction": "Re-cluster the questions ensuring each cluster has a label, uncertainty_type, and at least one question."
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

    logger.info("cluster_questions.complete",
                correlation_id=correlation_id,
                cluster_count=len(clusters),
                unclustered_count=len(unclustered))

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Clustered {len(validated.questions)} questions into {len(clusters)} groups."
        )],
        structuredContent={
            "clusters": clusters,
            "unclustered": unclustered,
            "summary_markdown": summary_markdown,
            "assistant_guidance": {
                "action": "PRESENT_CLUSTERS",
                "instruction": (
                    "Present the clusters to the user. For each cluster, show:\n"
                    "- The cluster name\n"
                    "- The uncertainty type\n"
                    "- The questions in that cluster\n"
                    "- The insight\n\n"
                    "If there are unclustered questions, show them separately.\n\n"
                    "Then ask: 'Which area would you like to explore further?'\n\n"
                    "Do NOT offer advice or solutions. Do NOT answer any questions.\n"
                    "Wait for the user to select a cluster."
                ),
            },
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    widget_uri=None,  # Widget comes in Increment 3
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=True,  # Transforms input, no side effects
    destructive_hint=False,
    open_world_hint=False,
))
