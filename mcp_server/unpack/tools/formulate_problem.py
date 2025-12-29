"""
Formulate Problem Tool.

Transforms LLM-extracted problem components into a structured problem statement.
Self-registers at import time.

Pattern: LLM extracts components from raw user input, tool validates and formats.
"""

from typing import List

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, Field, ValidationError

from .base import ToolDefinition, ToolUsageError
from . import register_tool
from ..tool_logic import formulate_problem as format_problem

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "formulate_problem"

DESCRIPTION = """
Transforms a vague problem description into a specific problem statement.

WHEN TO CALL:
- User describes a problem, challenge, or stuck situation and needs help clarifying it
- User says they need help thinking through something
- User mentions feeling overwhelmed or unclear and needs help thinking it through

CRITICAL: If a component is not clearly stated by the user, pass an empty string — NEVER INFER OR INVENT - ask clarifying questions.

OUTPUT FORMAT: "[Actor] is trying to [goal], but [obstacle] keeps happening, which costs [cost]."
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "actor": {
            "type": "string",
            "description": "Who is experiencing the problem (e.g., 'I', 'my team', 'our company')"
        },
        "goal": {
            "type": "string",
            "description": "What they're trying to achieve"
        },
        "obstacle": {
            "type": "string",
            "description": "What keeps blocking progress"
        },
        "cost": {
            "type": "string",
            "description": "Impact in terms of time, money, energy, or clarity"
        }
    },
    # NO "required" - all fields optional at schema level
    # Allows ChatGPT to call tool with partial extraction → low confidence → clarify flow
    "additionalProperties": False
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class FormulateInput(BaseModel):
    """
    Expected structure from ChatGPT.

    All fields optional - allows partial extraction → low confidence → clarify flow.
    """
    actor: str = Field(default="", description="Who is experiencing the problem")
    goal: str = Field(default="", description="What they're trying to achieve")
    obstacle: str = Field(default="", description="What keeps blocking progress")
    cost: str = Field(default="", description="Impact in terms of time, money, energy, or clarity")


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Handle formulate_problem tool call.

    Args:
        user_id: Empty string (Unpack uses noauth)
        correlation_id: Request correlation ID for tracing
        arguments: LLM-extracted problem components {actor, goal, obstacle, cost}

    Returns:
        CallToolResult with structured problem statement
    """
    logger.debug("formulate_problem.handle.start",
                correlation_id=correlation_id,
                argument_keys=list(arguments.keys()))

    # ============================================================
    # VALIDATION
    # ============================================================
    try:
        validated = FormulateInput.model_validate(arguments)
        logger.debug("formulate_problem.validation_success",
                    correlation_id=correlation_id)

    except ValidationError as e:
        logger.warning("formulate_problem.validation_failed",
                      correlation_id=correlation_id,
                      error=str(e.errors()))
        # Raise ToolUsageError - dispatcher will surface message cleanly
        raise ToolUsageError(
            "I need a bit more to work with. What challenge or situation "
            "are you trying to think through?"
        )

    # ============================================================
    # FORMAT PROBLEM (call pure function)
    # ============================================================
    result = format_problem(
        actor=validated.actor,
        goal=validated.goal,
        obstacle=validated.obstacle,
        cost=validated.cost,
    )

    # ============================================================
    # BUILD RESPONSE
    # ============================================================
    confidence = result["confidence"]
    full_statement = result["formulated_problem"]["full_statement"]
    needs_clarification = result.get("needs_clarification", False)

    # Build assistant guidance as intent codes (not prose)
    # Tool decides WHAT, assistant decides HOW to phrase it
    if not needs_clarification:
        guidance = {
            "action": "CONFIRM_PROBLEM",
            "problem_statement": full_statement,
        }
    else:
        clarify_type = result.get("clarify", {}).get("type", "GENERAL")
        guidance = {
            "action": "ASK_CLARIFYING",
            "problem_statement": full_statement,
            "clarify_type": clarify_type,
        }

    logger.info("formulate_problem.complete",
                correlation_id=correlation_id,
                confidence=confidence)

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Formulated problem: {full_statement}"
        )],
        structuredContent={
            **result,
            "assistant_guidance": guidance,
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    widget_uri=None,  # No widget for this tool
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=True,  # Transforms input, no side effects
    destructive_hint=False,
    open_world_hint=False,
))
