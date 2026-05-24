"""
Priority Guardian MCP Tool Registry.

Explicit registry pattern - no import side effects, no register_tool() calls.
The registry is a single inspectable, testable data structure.
"""

from copy import deepcopy
from typing import List

import structlog
from mcp import types as mcp_types

from .base import ToolDefinition
# Public tools (LLM can see and call)
from .create_priority import CREATE_PRIORITY
from .get_priorities import GET_PRIORITIES
from .get_priority_events import GET_PRIORITY_EVENTS
from .render_weekly_report import RENDER_WEEKLY_REPORT
from .get_patterns import GET_PATTERNS
from .onboarding_calendar_setup import ONBOARDING_CALENDAR_SETUP
from .inspect_adapt import INSPECT_ADAPT
# Private widget-only tools (widget can call, LLM cannot see)
from .widget_tools import (
    ADD_PRIORITY,
    UPDATE_PRIORITY,
    DELETE_PRIORITY,
    ADD_DELIVERABLE,
    UPDATE_DELIVERABLE,
    DELETE_DELIVERABLE,
    ADD_GOAL,
    UPDATE_GOAL,
    DELETE_GOAL,
    CONNECT_GOOGLE_CALENDAR,
    DISCONNECT_GOOGLE_CALENDAR,
    RECORD_WIDGET_DIAGNOSTIC,
)

logger = structlog.get_logger(__name__)

# Tool-specific invocation messages for better UX
# Only needed for public tools (LLM-callable) - private tools don't show messages
TOOL_INVOCATION_MESSAGES: dict[str, tuple[str, str]] = {
    "get_priorities": (
        "Loading your priorities...",
        "Here's your Priority Guardian dashboard.",
    ),
    "create_priority": (
        "Setting up your priority...",
        "Here's your Priority Guardian dashboard.",
    ),
    "get_priority_events": (
        "Fetching priority events...",
        "Events retrieved.",
    ),
    "render_weekly_report": (
        "Generating your weekly report...",
        "Here's your weekly time allocation.",
    ),
    "onboarding_calendar_setup": (
        "Walking you through tracking setup...",
        "Here's your tracking guide.",
    ),
    "get_patterns": (
        "Analyzing your tracking patterns...",
        "Here's what I found in your history.",
    ),
    "inspect_adapt": (
        "Recording your action steps...",
        "Action steps confirmed.",
    ),
}

# Explicit tool registry
TOOL_REGISTRY: dict[str, ToolDefinition] = {
    # Public tools (LLM can see and call)
    CREATE_PRIORITY.name: CREATE_PRIORITY,
    GET_PRIORITIES.name: GET_PRIORITIES,
    GET_PRIORITY_EVENTS.name: GET_PRIORITY_EVENTS,
    RENDER_WEEKLY_REPORT.name: RENDER_WEEKLY_REPORT,
    GET_PATTERNS.name: GET_PATTERNS,
    ONBOARDING_CALENDAR_SETUP.name: ONBOARDING_CALENDAR_SETUP,
    INSPECT_ADAPT.name: INSPECT_ADAPT,
    # Private widget-only tools (widget can call, LLM cannot see)
    CONNECT_GOOGLE_CALENDAR.name: CONNECT_GOOGLE_CALENDAR,
    DISCONNECT_GOOGLE_CALENDAR.name: DISCONNECT_GOOGLE_CALENDAR,
    ADD_PRIORITY.name: ADD_PRIORITY,
    UPDATE_PRIORITY.name: UPDATE_PRIORITY,
    DELETE_PRIORITY.name: DELETE_PRIORITY,
    ADD_DELIVERABLE.name: ADD_DELIVERABLE,
    UPDATE_DELIVERABLE.name: UPDATE_DELIVERABLE,
    DELETE_DELIVERABLE.name: DELETE_DELIVERABLE,
    ADD_GOAL.name: ADD_GOAL,
    UPDATE_GOAL.name: UPDATE_GOAL,
    DELETE_GOAL.name: DELETE_GOAL,
    RECORD_WIDGET_DIAGNOSTIC.name: RECORD_WIDGET_DIAGNOSTIC,
}


def get_tool(name: str) -> ToolDefinition | None:
    """Get a tool by name, or None if not found."""
    return TOOL_REGISTRY.get(name)


async def list_tools() -> List[mcp_types.Tool]:
    """
    Build MCP Tool list from registry.

    Each tool gets:
    - annotations (ToolAnnotations with readOnlyHint, destructiveHint, openWorldHint)
    - _meta with securitySchemes, ui visibility, openai/outputTemplate if widget_uri is set

    Sorted by name for deterministic output.
    """
    tools = []

    # Sort by name for deterministic output
    for tool_def in sorted(TOOL_REGISTRY.values(), key=lambda t: t.name):
        # Build securitySchemes based on required_scopes
        if tool_def.required_scopes:
            security_schemes = [{"type": "oauth2", "scopes": tool_def.required_scopes}]
        else:
            security_schemes = [{"type": "noauth"}]

        # Get tool-specific invocation messages (fallback to generic)
        invoking_msg, invoked_msg = TOOL_INVOCATION_MESSAGES.get(
            tool_def.name, ("Processing...", "Done.")
        )

        # Build _meta based on tool capabilities
        # Use new ui.* keys per OpenAI Apps SDK (March 2026)
        if tool_def.visibility == "private":
            # Private tools: widget-only, LLM cannot see or call them
            meta = {
                "ui": {
                    "visibility": ["app"],
                },
                "securitySchemes": security_schemes,
            }
        elif tool_def.widget_uri and tool_def.widget_accessible:
            # Widget-producing AND widget-callable public tools
            # visibility: ["model", "app"] - both model and widget can call
            meta = {
                "ui": {
                    "resourceUri": tool_def.widget_uri,
                    "visibility": ["model", "app"],
                },
                "openai/outputTemplate": tool_def.widget_uri,  # compat alias
                "openai/toolInvocation/invoking": invoking_msg,
                "openai/toolInvocation/invoked": invoked_msg,
                "securitySchemes": security_schemes,
            }
        elif tool_def.widget_uri:
            # Widget-producing but NOT widget-callable (e.g., create_priority)
            # visibility: ["model"] - only model can call, widget cannot
            meta = {
                "ui": {
                    "resourceUri": tool_def.widget_uri,
                    "visibility": ["model"],
                },
                "openai/outputTemplate": tool_def.widget_uri,  # compat alias
                "openai/toolInvocation/invoking": invoking_msg,
                "openai/toolInvocation/invoked": invoked_msg,
                "securitySchemes": security_schemes,
            }
        elif tool_def.widget_accessible:
            # Widget-callable public tools without widget output
            # visibility: ["model", "app"]
            meta = {
                "ui": {
                    "visibility": ["model", "app"],
                },
                "openai/toolInvocation/invoking": invoking_msg,
                "openai/toolInvocation/invoked": invoked_msg,
                "securitySchemes": security_schemes,
            }
        else:
            # Public model-only tools without widget
            # visibility: ["model"]
            meta = {
                "ui": {
                    "visibility": ["model"],
                },
                "openai/toolInvocation/invoking": invoking_msg,
                "openai/toolInvocation/invoked": invoked_msg,
                "securitySchemes": security_schemes,
            }

        tool = mcp_types.Tool(
            name=tool_def.name,
            description=tool_def.description,
            inputSchema=deepcopy(tool_def.input_schema),
            _meta=meta,
        )

        # Set annotations at Tool level (proper ToolAnnotations object, not dict)
        tool.annotations = mcp_types.ToolAnnotations(
            title=tool_def.title,
            readOnlyHint=tool_def.read_only_hint,
            destructiveHint=tool_def.destructive_hint,
            openWorldHint=tool_def.open_world_hint,
        )

        tools.append(tool)

    logger.debug("tools.list.returning", tool_count=len(tools))
    return tools
