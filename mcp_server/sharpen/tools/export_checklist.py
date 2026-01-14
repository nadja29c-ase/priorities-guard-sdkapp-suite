"""
Export Checklist Tool.

Generates a markdown checklist grouped by deliverable from work items.
Self-registers at import time.
"""

from typing import List

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, Field, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import export_checklist as do_export_checklist

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

DESCRIPTION = """Generate a markdown checklist grouped by deliverable from a list of work items."""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {
            "type": "string",
            "description": "Name of the project",
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "Name of the work item",
                    },
                    "deliverable": {
                        "type": "string",
                        "description": "Parent deliverable this task belongs to",
                    },
                    "estimate_hours": {
                        "type": "number",
                        "description": "Estimated hours (optional)",
                    },
                },
                "required": ["task_name", "deliverable"],
            },
            "minItems": 1,
        },
    },
    "required": ["project_name", "items"],
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class WorkItemInput(BaseModel):
    """Expected structure for each work item."""
    task_name: str
    deliverable: str
    estimate_hours: float | None = None


class ExportChecklistRequest(BaseModel):
    """Expected top-level structure from ChatGPT."""
    project_name: str
    items: List[WorkItemInput] = Field(..., min_length=1)


# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """
    Handle export_checklist tool call.

    Args:
        arguments: Raw arguments from ChatGPT

    Returns:
        CallToolResult with markdown checklist
    """
    logger.debug("export_checklist.handle.start",
                argument_keys=list(arguments.keys()))

    # ============================================================
    # VALIDATION
    # ============================================================
    try:
        validated_request = ExportChecklistRequest.model_validate(arguments)
        logger.debug("export_checklist.validation_success",
                    project_name=validated_request.project_name,
                    item_count=len(validated_request.items))

    except ValidationError as e:
        logger.warning("export_checklist.validation_failed",
                      error=str(type(e).__name__),
                      details=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text="Invalid input. Expected 'project_name' and at least one item with 'task_name' and 'deliverable'.",
            )],
            structuredContent={
                "error": "validation_error",
                "details": e.errors(),
            },
            isError=True,
        )

    # ============================================================
    # GENERATE CHECKLIST (call pure function)
    # ============================================================
    items = [item.model_dump() for item in validated_request.items]
    result = do_export_checklist(validated_request.project_name, items)

    # ============================================================
    # BUILD RESPONSE (handler shapes MCP transport layer)
    # ============================================================
    logger.info("export_checklist.complete",
                project_name=validated_request.project_name,
                item_count=len(items))

    # Extract markdown from pure logic result
    markdown = result["checklist_markdown"]

    # Shape into MCP structuredContent (transport layer concern)
    structured_content = {
        "status": "exported",
        "format": "markdown",
        "project_name": result["project_name"],
        "item_count": result["item_count"],
        "checklist_markdown": markdown,
        "assistant_guidance": {
            "action": "CONFIRM_EXPORT",
            "instruction": "Present the checklist to the user. They can copy it directly.",
        },
    }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=markdown)],
        structuredContent=structured_content,
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="export_checklist",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Produces artifact for user (not read-only)
    destructive_hint=False,  # Doesn't modify/delete existing data
    open_world_hint=False,  # No external API calls
))
