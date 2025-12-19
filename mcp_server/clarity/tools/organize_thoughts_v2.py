"""
Organize Thoughts V2 - Simplified test version.

Tests if tool description alone guides LLM behavior without assistant_guidance.
Self-registers at import time.
"""

from typing import List

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, Field, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..handlers.resources import WIDGET_URI

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "organize_thoughts_v2"

DESCRIPTION = """
Organize user's thoughts into visual clusters. Renders a board widget.

FACILITATOR ROLE: Questions unlock clarity. Advice blocks it.

Example:
❌ "Your order should be: 1. Proposal 2. Emails"
✅ "What else is on your mind?"
✅ "Which of these feels most urgent?"

Include ALL thoughts. After rendering, ask what else is on their mind.
When done, ask if they want to prioritize.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cluster_name": {"type": "string"},
                    "thought_items": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["cluster_name", "thought_items"]
            }
        },
        "thoughts_exhausted": {
            "type": "boolean",
            "description": "Set true only when user confirms 'that's all'."
        }
    },
    "required": ["clusters"]
}

REQUIRED_SCOPES = ["clarity.write"]

# ============================================================================
# Pydantic Models (Simplified)
# ============================================================================


class ClusterInput(BaseModel):
    """Simple cluster structure."""
    cluster_name: str
    thought_items: List[str] = Field(default_factory=list)


class ClusterRequest(BaseModel):
    """Request structure."""
    clusters: List[ClusterInput]
    thoughts_exhausted: bool = False


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(
    user_id: str,
    correlation_id: str,
    arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Handle organize_thoughts_v2 tool call.
    Simplified version - no subclusters, tags, or assistant_guidance.
    """
    logger.debug("organize_thoughts_v2.handle.start",
                user_id=user_id,
                correlation_id=correlation_id)

    # Validate
    try:
        request = ClusterRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("organize_thoughts_v2.validation_failed", error=str(e))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Invalid input format."
            )],
            isError=True,
        )

    # Build simple cluster output
    clusters = [
        {
            "cluster_name": c.cluster_name,
            "thought_items": c.thought_items,
            "sum_thought_items": len(c.thought_items),
        }
        for c in request.clusters
    ]

    # Conditional message - no assistant_guidance
    if request.thoughts_exhausted:
        message = "Here's your board. Want to prioritize? Tell me which clusters matter most."
    else:
        message = "What else is on your mind?"

    logger.info("organize_thoughts_v2.complete",
                cluster_count=len(clusters),
                user_id=user_id)

    meta = {
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Organizing your thoughts...",
        "openai/toolInvocation/invoked": "Here's your Clarity board.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=message)],
        structuredContent={
            "clusters": clusters,
            "thoughts_exhausted": request.thoughts_exhausted
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
