"""
create_priority tool for Priority Guardian MCP.

Records a user's declared priority for time tracking.
"""

import httpx
import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_post
from .base import ToolDefinition

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "create_priority"

DESCRIPTION = """Records a user's declared priority so Priority Guardian can track their time investment against it. A calendar keyword (P1, P2, or P3) is assigned — the user tags their Google Calendar events with this keyword so PG knows which hours count toward which priority.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- User has clearly stated a priority name (their exact words — NEVER rephrase or embellish)
- You have confirmed the type (deadline or flexible) based on user's description
- You have gathered ALL required fields for that type (see schema)
- User has confirmed the details are correct

If ANY required field is missing or vague → ask the user. NEVER invent defaults.

ONBOARDING CONTEXT: User is setting up 1–3 priorities. Call this tool once per priority after gathering all fields. After the tool returns, tell the user their assigned calendar keyword and remind them to tag calendar events with it (e.g., "Tag your calendar events with P1 to track time — like 'P1: Design review'").

KEYWORD ASSIGNMENT: If the user expresses a preference for which keyword (P1, P2, P3) to assign, include it. Otherwise omit and the backend assigns the next available."""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Priority name exactly as stated by user (max 100 chars)",
            "maxLength": 100,
        },
        "calendar_keyword": {
            "type": "string",
            "enum": ["P1", "P2", "P3"],
            "description": "Preferred keyword (optional). If not provided, next available is auto-assigned.",
        },
        "type": {
            "type": "string",
            "enum": ["deadline", "flexible"],
            "description": "Priority type: 'deadline' for hard deadlines, 'flexible' for ongoing commitments",
        },
        "deadline": {
            "type": "string",
            "description": "ISO date (YYYY-MM-DD) - required when type=deadline",
        },
        "weekly_hour_target": {
            "type": "number",
            "description": "Hours per week - required when type=flexible",
        },
        "checkpoint_date": {
            "type": "string",
            "description": "ISO date (YYYY-MM-DD) - required when type=flexible",
        },
        "initial_goal_text": {
            "type": "string",
            "description": "Initial goal text (max 200 chars) - required when type=flexible",
            "maxLength": 200,
        },
    },
    "required": ["name", "type"],
}

REQUIRED_SCOPES = ["pg.access"]


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Create a priority for time tracking.

    Extracts arguments, calls backend, and returns CallToolResult with
    assistant_guidance based on active_priority_count.

    For known backend errors (MAX_PRIORITIES_REACHED, KEYWORD_CONFLICT, VALIDATION_ERROR),
    returns CallToolResult directly with full structuredContent to preserve behavioral invariance.

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments

    Returns:
        CallToolResult with priority data and assistant_guidance
    """
    # Extract arguments
    name = arguments.get("name")
    calendar_keyword = arguments.get("calendar_keyword")
    priority_type = arguments.get("type")
    deadline = arguments.get("deadline")
    weekly_hour_target = arguments.get("weekly_hour_target")
    checkpoint_date = arguments.get("checkpoint_date")
    initial_goal_text = arguments.get("initial_goal_text")

    logger.info(
        "tool.create_priority.start",
        correlation_id=correlation_id,
        user_id=user_id,
        priority_name=name,
        priority_type=priority_type,
        calendar_keyword=calendar_keyword,
    )

    # Build request payload (forward as-is, backend validates)
    payload = {
        "name": name,
        "type": priority_type,
    }

    # Add optional fields only if provided
    if calendar_keyword is not None:
        payload["calendar_keyword"] = calendar_keyword
    if deadline is not None:
        payload["deadline"] = deadline
    if weekly_hour_target is not None:
        payload["weekly_hour_target"] = weekly_hour_target
    if checkpoint_date is not None:
        payload["checkpoint_date"] = checkpoint_date
    if initial_goal_text is not None:
        payload["initial_goal_text"] = initial_goal_text

    # Call backend to create priority
    # NOTE: Inner try/except for HTTPStatusError builds tool-specific assistant_guidance.
    # Known backend errors return CallToolResult directly to preserve response structure.
    # Unexpected errors propagate to dispatcher's generic catch.
    try:
        response = await backend_post(
            "/api/priority-guardian/priorities",
            payload,
            user_id,
            correlation_id
        )

        # Backend returns success response
        priority = response["data"]["priority"]
        active_count = response["data"]["active_priority_count"]
        available_keywords = response["data"]["available_keywords"]

        logger.info(
            "tool.create_priority.success",
            correlation_id=correlation_id,
            user_id=user_id,
            priority_id=priority["id"],
            keyword=priority["calendar_keyword"],
        )

        # Build assistant_guidance based on active_priority_count
        keyword = priority["calendar_keyword"]
        priority_name = priority["name"]

        if active_count < 3:
            remaining = 3 - active_count
            guidance = (
                f'Priority created. Tell the user: "{priority_name} is now tracked as {keyword}."\n'
                f'Remind them: "Tag your calendar events with {keyword} to track time — '
                f"for example, '{keyword}: Meeting name'.\"\n\n"
                f'Ask: "Do you have another priority you\'d like to track? '
                f'You can have up to {remaining} more."'
            )
        else:
            guidance = (
                f'Priority created. Tell the user: "{priority_name} is now tracked as {keyword}."\n'
                f'Remind them: "Tag your calendar events with {keyword} to track time — '
                f"for example, '{keyword}: Meeting name'.\"\n\n"
                'Say: "You\'ve set up all 3 priorities. Let me show you your dashboard." '
                'Then call get_priorities to render the widget.'
            )

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Created priority: {priority_name} (assigned {keyword})"
            )],
            structuredContent={
                "priority": priority,
                "active_priority_count": active_count,
                "available_keywords": available_keywords,
                "assistant_guidance": guidance,
            },
        )

    except httpx.HTTPStatusError as e:
        # Handle specific backend error responses
        # Return CallToolResult directly for known errors to preserve behavioral invariance
        status_code = e.response.status_code

        try:
            error_data = e.response.json()
            error_code = error_data.get("error", {}).get("code", "UNKNOWN")
            error_message = error_data.get("error", {}).get("message", "Unknown error")
        except Exception:
            error_code = "BACKEND_ERROR"
            error_message = f"Backend returned {status_code}"

        logger.warning(
            "tool.create_priority.backend_error",
            correlation_id=correlation_id,
            user_id=user_id,
            status_code=status_code,
            error_code=error_code,
        )

        # Build error-specific assistant_guidance
        if error_code == "MAX_PRIORITIES_REACHED":
            guidance = (
                "User already has 3 active priorities. Tell the user they've reached the maximum. "
                "If they want to add a new one, they'll need to retire or delete an existing priority first "
                "(available in their dashboard)."
            )
        elif error_code == "KEYWORD_CONFLICT":
            guidance = (
                "A race condition occurred assigning the keyword. Retry the request — "
                "the backend will assign the next available keyword."
            )
        elif error_code == "VALIDATION_ERROR":
            guidance = (
                f"Tell the user what's missing or invalid based on this error: {error_message}. "
                "Ask them to provide the correct information. Do not guess or fill in defaults."
            )
        else:
            guidance = f"An error occurred: {error_message}. Please try again."

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Error: {error_message}"
            )],
            structuredContent={
                "error": {
                    "code": error_code,
                    "message": error_message,
                },
                "assistant_guidance": guidance,
            },
            isError=True,
        )


# ============================================================================
# Tool Definition
# ============================================================================

CREATE_PRIORITY = ToolDefinition(
    name=NAME,
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=None,
    handle=handle,
    read_only_hint=False,   # Creates data in database
    destructive_hint=False,
    open_world_hint=False,  # No external system interaction
)
