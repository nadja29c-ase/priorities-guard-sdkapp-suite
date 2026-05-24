"""
create_priority tool for Priority Guardian MCP.

Records a user's declared priority for time tracking with verbatim provenance
fields to enforce conversational onboarding flow.

Three-layer validation model:
1. JSON Schema: Structural gate (required fields present)
2. MCP handler (provenance): Behavioral gate (verbatim fields non-empty)
3. Backend (domain): Business rules (conditional fields, future dates, max 3)
"""

import asyncio

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_post, backend_get
from .base import ToolDefinition, ToolUsageError
from .normalize import _normalize_priority
from .widget_tools.constants import WIDGET_URI

logger = structlog.get_logger(__name__)

# Timeout for backend calls (seconds) — must be under ChatGPT's ~10s window
TIMEOUT_S = 8.0


async def _call_with_timeout(coro, op_name: str, correlation_id: str):
    """Wrap a coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning(
            "tool.create_priority.timeout",
            correlation_id=correlation_id,
            op_name=op_name,
            timeout=TIMEOUT_S,
        )
        raise ToolUsageError(f"{op_name} timed out. Please try again.")

# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "create_priority"

DESCRIPTION = """Creates ONE priority AT A TIME for guarding and progress tracking while onboarding the user. Call ONCE per priority — user sets up 1–3 priorities iteratively.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- user_priority_name_verbatim: non-empty, user's exact words
- name: derived from verbatim, normalized for clarity
- user_priority_type_verbatim: non-empty, user's exact words choosing deadline or flexible priority type.
- type: derived from user's choice
- For deadline: deadline date gathered from user
- For flexible: weekly_hour_target, checkpoint_date, user_goal_verbatim, AND initial_goal_text all gathered from user

DO NOT CALL this tool:
- When the user is asking for advice on how to prioritize or manage tasks
- When the user wants to plan, break down, or organize a project into tasks
- When the user is asking a general productivity question

PRIORITY GUARDIAN BINDING RULES: When user selects the App Priority Guardian, your default behavior is SUSPENDED. Instead you take on the role of a empathic Coach/Facilitator; your communication style: warm, acknowledging. Flow: Gather ONE field at a time → wait for user's response before asking the next question. NEVER ask for multiple fields in one message. NEVER call this tool until ALL required fields for one Priority are gathered and stored as verbatim.

FIRST-TIME CONTEXT: If user has no existing priorities, open with something like this example (adapt naturally, do not copy verbatim):

'Happy to help you set that up. We'll lock in your first priority together, and I'll walk you through how Priority Guardian works as we go.

Quick overview: PG lets you anchor up to 3 priorities you want to protect time for. You stay flexible in how you plan your week — PG just tracks whether your calendar actually reflects what you said matters most.

Let's start — what's the first priority you want to lock in?'

Then begin the sequence.

Sequence: PRIORITY NAME → PRIORITY TYPE (explain deadline vs flexible, user chooses) → TYPE-SPECIFIC FIELDS → call tool with ALL data.
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "user_priority_name_verbatim": {
            "type": "string",
            "description": "Copy-paste user's exact words for their priority. Must be non-empty.",
            "minLength": 1,
        },
        "name": {
            "type": "string",
            "description": "Priority name derived from verbatim — normalized for clarity (max 100 chars). Do not invent specificity the user did not state.",
            "maxLength": 100,
        },
        "user_priority_type_verbatim": {
            "type": "string",
            "description": (
                "Copy-paste user's words that reveal their priority type. "
                "NEVER ask user to say 'deadline' or 'flexible' literally — ask in natural terms "
                "and capture their natural language response. "
                "Explain the difference before asking:\n"
                "- Deadline = non-negotiable external end date + concrete deliverables to ship. "
                "PG tracks what gets delivered by when.\n"
                "- Flexible = ongoing commitment where consistent time investment matters. "
                "PG tracks weekly hours + a 1-month goal.\n"
                "A date alone does NOT mean deadline — probe whether it's a hard external constraint "
                "or an aspirational target. If unsure, suggest flexible: it gives weekly structure "
                "and monthly checkpoints without artificial pressure."
            ),
            "minLength": 1,
        },
        "type": {
            "type": "string",
            "enum": ["deadline", "flexible"],
            "description": "Priority type derived from user's verbatim choice. Map user's natural language to one of the enum values. Never ask the user to say 'deadline' or 'flexible' literally.",
        },
        "calendar_keyword": {
            "type": "string",
            "enum": ["P1", "P2", "P3"],
            "description": "Preferred keyword (optional). Omit to auto-assign next available.",
        },
        "deadline": {
            "type": "string",
            "description": (
                "ISO date (YYYY-MM-DD). The hard due date for this priority. "
                "User can say a natural date like 'end of March' or 'March 15th' — convert to ISO format. "
                "Do NOT ask user for YYYY-MM-DD format. Required when type=deadline."
            ),
        },
        "weekly_hour_target": {
            "type": "number",
            "description": "Hours per week commitment. Required when type=flexible. Explain why this is necessary and how it will be used for progress tracking.",
            "exclusiveMinimum": 0,
        },
        "user_goal_verbatim": {
            "type": "string",
            "description": (
                "Copy-paste user's exact words for their 1-month goal. "
                "Ask BEFORE checkpoint_date. Explain why: hours alone don't tell you if you're making progress. "
                "A concrete goal turns time investment into something measurable. "
                "Ask: 'What would success look like in about a month? One sentence — specific enough that you'll know whether it happened.' "
                "Must be non-empty. Required when type=flexible."
            ),
            "minLength": 1,
        },
        "checkpoint_date": {
            "type": "string",
            "description": (
                "ISO date (YYYY-MM-DD). Ask AFTER user_goal_verbatim. "
                "The date when user will evaluate whether their time investment is producing results against their goal. "
                "User can say a natural date like 'mid-March' or 'in 4 weeks' — convert to ISO format. "
                "Do NOT ask user for YYYY-MM-DD format. Typically ~1 month from now. Required when type=flexible."
            ),
        },
        "initial_goal_text": {
            "type": "string",
            "description": (
                "The concrete outcome user expects, derived from user_goal_verbatim. "
                "Normalized for clarity (max 200 chars). Required when type=flexible."
            ),
            "maxLength": 200,
        },
    },
    "required": [
        "user_priority_name_verbatim",
        "name",
        "user_priority_type_verbatim",
        "type",
    ],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]


# ============================================================================
# Action Constants (for assistant_guidance)
# ============================================================================

ACTION_PRIORITY_CREATED = "PRIORITY_CREATED"
ACTION_ASK_CLARIFYING = "ASK_CLARIFYING"
ACTION_RETRY = "RETRY"
ACTION_MAX_REACHED = "MAX_REACHED"
ACTION_ERROR = "ERROR"

# Shared onboarding completion guidance (used in multiple branches)
ONBOARDING_COMPLETION_GUIDANCE = (
    "Acknowledge their setup is complete (even if fewer than 3 — that's fine, they can add more anytime). "
    "Briefly introduce the dashboard: their home base — a quick way to check "
    "how their week is going, stay flexible, and stay on track with what matters most. "
    "Two views — inline summary in chat, and full dashboard (button at the bottom) "
    "for detailed progress and editing. "
    "Guide user to connect Google Calendar next — open the full dashboard to set that up. "
    "Keywords and progress tracking will be explained after calendar is connected."
)


# ============================================================================
# Provenance Guidance Messages
# ============================================================================

GUIDANCE_EMPTY_NAME_VERBATIM = (
    "user_priority_name_verbatim is empty. Do not call this tool until user has stated a priority. "
    "Ask: 'What is the priority you want to lock in and track your time against?' "
    "Then store their exact answer in user_priority_name_verbatim."
)

GUIDANCE_EMPTY_NAME = (
    "name is empty. Derive from user_priority_name_verbatim — "
    "normalize for clarity but do not invent specificity."
)

GUIDANCE_EMPTY_TYPE_VERBATIM = (
    "user_priority_type_verbatim is empty. Do not call this tool until user has chosen deadline or flexible. "
    "Explain: Deadline priorities have a hard end date. Flexible priorities are ongoing commitments with a weekly hour target. "
    "Ask: 'Does this priority have a hard deadline, or is it more of an ongoing commitment?' "
    "Then store their exact answer in user_priority_type_verbatim."
)

GUIDANCE_EMPTY_GOAL_VERBATIM = (
    "user_goal_verbatim is empty. Do not call this tool until user has stated a 1-month goal. "
    "Explain: The 1-month goal anchors your time investment to a concrete outcome. "
    "Ask: 'What would success look like in one month? One sentence — specific enough "
    "that you will know whether it happened.' "
    "Then store their exact answer in user_goal_verbatim."
)

GUIDANCE_EMPTY_GOAL_TEXT = (
    "initial_goal_text is empty. Derive from user_goal_verbatim — "
    "normalize for clarity but do not invent specificity."
)

GUIDANCE_MISSING_TYPE = (
    "type is missing or invalid. Derive from user_priority_type_verbatim — "
    "must be 'deadline' or 'flexible' based on user's stated preference."
)

GUIDANCE_MISSING_DEADLINE = (
    "deadline is required for deadline-type priorities. "
    "Ask: 'What is the due date for this priority?' "
    "Then store the ISO date (YYYY-MM-DD) in the deadline field."
)

GUIDANCE_MISSING_WEEKLY_HOURS = (
    "weekly_hour_target is required for flexible-type priorities. "
    "Ask: 'How many hours per week do you want to commit to this priority?' "
    "Then store the number in weekly_hour_target."
)

GUIDANCE_MISSING_CHECKPOINT = (
    "checkpoint_date is required for flexible-type priorities. "
    "Ask: 'When should we check in on your progress — about a month from now?' "
    "Then store the ISO date (YYYY-MM-DD) in checkpoint_date."
)


# ============================================================================
# Helper Functions
# ============================================================================

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
                "action": ACTION_ASK_CLARIFYING,
                "instruction": instruction,
            },
        },
        isError=True,
    )


def _build_success_guidance(
    keyword: str,
    priority_name: str,
    available_keywords: list[str] | None,
    correlation_id: str,
) -> dict:
    """Build structured guidance after successful priority creation.

    Uses available_keywords from backend to determine remaining slots.
    Defensive fallback if available_keywords is missing/invalid.
    """
    if available_keywords is None or not isinstance(available_keywords, list):
        # Defensive: backend response shape may have changed
        logger.error(
            "tool.create_priority.missing_available_keywords",
            correlation_id=correlation_id,
        )
        return {
            "action": ACTION_PRIORITY_CREATED,
            "instruction": (
                f"Priority created: {priority_name} is now tracked as {keyword}. "
                "The dashboard now shows the user's priorities. "
                "Do NOT repeat priority details — the widget displays them.\n\n"
                f"Remind user: add {keyword} to calendar event titles to track time "
                f"(e.g., '{keyword}: Meeting name')."
            ),
        }

    remaining = len(available_keywords)

    if remaining > 0:
        next_slot = available_keywords[0] if available_keywords else None
        guidance = {
            "action": ACTION_PRIORITY_CREATED,
            "remaining_slots": remaining,
        }
        if next_slot:
            guidance["next_available_keyword"] = next_slot
        guidance["instruction"] = (
            f"Priority created: {priority_name} is now tracked as {keyword}. "
            "The dashboard now shows the user's priorities. "
            "Do NOT repeat priority details — the widget displays them."
        )
        guidance["next_steps"] = {
            "path_a": {
                "label": "conversational",
                "instruction": (
                    "Present both options to the user: "
                    "'What is your next priority?' — and also mention: "
                    "'Or you can add priorities directly in the dashboard above. "
                    "Just let me know when you are done.' "
                    "If user continues conversationally, gather ONE question at a time following the binding rules. "
                    "If user says 'done' or signals completion, "
                    + ONBOARDING_COMPLETION_GUIDANCE
                ),
            },
            "path_b": {
                "label": "widget",
                "instruction": (
                    "User chose to add via dashboard or said 'done'. "
                    + ONBOARDING_COMPLETION_GUIDANCE
                ),
            },
            "present_both": True,
        }
        return guidance
    else:
        return {
            "action": ACTION_PRIORITY_CREATED,
            "remaining_slots": 0,
            "instruction": (
                f"Priority created: {priority_name} is now tracked as {keyword}. "
                "All 3 priority slots are filled. "
                + ONBOARDING_COMPLETION_GUIDANCE
            ),
        }


# ============================================================================
# Handler
# ============================================================================

async def handle(user_id: str, correlation_id: str, arguments: dict) -> mcp_types.CallToolResult:
    """
    Create a priority for time tracking with provenance validation.

    Flow:
    1. Extract arguments
    2. Validate provenance fields (verbatim non-empty)
    3. Build backend payload (exclude verbatim fields)
    4. Call backend POST /api/priority-guardian/priorities
    5. On success: fetch fresh priorities, build widget response
    6. On error: return structured error with guidance

    Args:
        user_id: Validated user ID from JWT token
        correlation_id: Request correlation ID
        arguments: Tool arguments

    Returns:
        CallToolResult with widget data and assistant_guidance
    """
    # -------------------------------------------------------------------------
    # Step 1: Extract arguments
    # -------------------------------------------------------------------------
    user_priority_name_verbatim = arguments.get("user_priority_name_verbatim", "")
    name = arguments.get("name", "")
    user_priority_type_verbatim = arguments.get("user_priority_type_verbatim", "")
    priority_type = arguments.get("type")
    calendar_keyword = arguments.get("calendar_keyword")
    deadline = arguments.get("deadline")
    weekly_hour_target = arguments.get("weekly_hour_target")
    checkpoint_date = arguments.get("checkpoint_date")
    user_goal_verbatim = arguments.get("user_goal_verbatim", "")
    initial_goal_text = arguments.get("initial_goal_text", "")

    logger.info(
        "tool.create_priority.start",
        correlation_id=correlation_id,
        user_id=user_id,
        priority_name=name,
        priority_type=priority_type,
        calendar_keyword=calendar_keyword,
    )

    # -------------------------------------------------------------------------
    # Step 2: Provenance validation (behavioral gate)
    # -------------------------------------------------------------------------

    # Check user_priority_name_verbatim non-empty
    if not user_priority_name_verbatim or not user_priority_name_verbatim.strip():
        logger.warning(
            "tool.create_priority.provenance_failed",
            correlation_id=correlation_id,
            field="user_priority_name_verbatim",
        )
        return _build_provenance_error("empty_name_verbatim", GUIDANCE_EMPTY_NAME_VERBATIM)

    # Check name non-empty
    if not name or not name.strip():
        logger.warning(
            "tool.create_priority.provenance_failed",
            correlation_id=correlation_id,
            field="name",
        )
        return _build_provenance_error("empty_name", GUIDANCE_EMPTY_NAME)

    # Check user_priority_type_verbatim non-empty
    if not user_priority_type_verbatim or not user_priority_type_verbatim.strip():
        logger.warning(
            "tool.create_priority.provenance_failed",
            correlation_id=correlation_id,
            field="user_priority_type_verbatim",
        )
        return _build_provenance_error("empty_type_verbatim", GUIDANCE_EMPTY_TYPE_VERBATIM)

    # Defensive guard: type must be valid (schema should prevent, but costs one line)
    if priority_type not in ("deadline", "flexible"):
        logger.warning(
            "tool.create_priority.provenance_failed",
            correlation_id=correlation_id,
            field="type",
            value=priority_type,
        )
        return _build_provenance_error("missing_type", GUIDANCE_MISSING_TYPE)

    # For deadline type: check deadline field is present
    if priority_type == "deadline":
        if not deadline or not deadline.strip():
            logger.warning(
                "tool.create_priority.provenance_failed",
                correlation_id=correlation_id,
                field="deadline",
            )
            return _build_provenance_error("missing_deadline", GUIDANCE_MISSING_DEADLINE)

    # For flexible type: check structural and goal fields
    if priority_type == "flexible":
        if weekly_hour_target is None or weekly_hour_target <= 0:
            logger.warning(
                "tool.create_priority.provenance_failed",
                correlation_id=correlation_id,
                field="weekly_hour_target",
            )
            return _build_provenance_error("missing_weekly_hours", GUIDANCE_MISSING_WEEKLY_HOURS)

        if not checkpoint_date or not checkpoint_date.strip():
            logger.warning(
                "tool.create_priority.provenance_failed",
                correlation_id=correlation_id,
                field="checkpoint_date",
            )
            return _build_provenance_error("missing_checkpoint", GUIDANCE_MISSING_CHECKPOINT)

        if not user_goal_verbatim or not user_goal_verbatim.strip():
            logger.warning(
                "tool.create_priority.provenance_failed",
                correlation_id=correlation_id,
                field="user_goal_verbatim",
            )
            return _build_provenance_error("empty_goal_verbatim", GUIDANCE_EMPTY_GOAL_VERBATIM)

        if not initial_goal_text or not initial_goal_text.strip():
            logger.warning(
                "tool.create_priority.provenance_failed",
                correlation_id=correlation_id,
                field="initial_goal_text",
            )
            return _build_provenance_error("empty_goal_text", GUIDANCE_EMPTY_GOAL_TEXT)

    # -------------------------------------------------------------------------
    # Step 3: Build backend payload (verbatim fields NOT sent)
    # -------------------------------------------------------------------------
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
    if initial_goal_text and initial_goal_text.strip():
        payload["initial_goal_text"] = initial_goal_text

    # -------------------------------------------------------------------------
    # Step 4: Call backend to create priority (with timeout)
    # -------------------------------------------------------------------------
    try:
        response = await _call_with_timeout(
            backend_post(
                "/api/priority-guardian/priorities",
                payload,
                user_id,
                correlation_id
            ),
            "Create priority",
            correlation_id,
        )

        # Check if backend returned an error (4xx returns JSON, not exception)
        if not response.get("success", True):
            error_data = response.get("error", {})
            error_code = error_data.get("code", "UNKNOWN")
            error_message = error_data.get("message", "Unknown error")

            logger.warning(
                "tool.create_priority.backend_error",
                correlation_id=correlation_id,
                user_id=user_id,
                error_code=error_code,
            )

            return _build_backend_error_response(error_code, error_message)

        # -------------------------------------------------------------------------
        # Step 5: Extract success data
        # -------------------------------------------------------------------------
        priority = response["data"]["priority"]
        keyword = priority["calendar_keyword"]
        priority_name = priority["name"]

        logger.info(
            "tool.create_priority.success",
            correlation_id=correlation_id,
            user_id=user_id,
            priority_id=priority["id"],
            keyword=keyword,
        )

        # -------------------------------------------------------------------------
        # Step 6: Fetch fresh priorities for widget rendering (with timeout)
        # -------------------------------------------------------------------------
        try:
            fresh_response = await _call_with_timeout(
                backend_get(
                    "/api/priority-guardian/priorities",
                    user_id,
                    correlation_id
                ),
                "Fetch priorities",
                correlation_id,
            )

            data = fresh_response.get("data", {})
            raw_priorities = data.get("priorities", [])
            google_connection = data.get("google_connection", {"connected": False})
            # Don't default to [] - preserve None for defensive check in _build_success_guidance
            fresh_available_keywords = data.get("available_keywords")

            priorities = [_normalize_priority(p) for p in raw_priorities]

        except (ToolUsageError, Exception) as get_error:
            # GET failed after POST succeeded - use POST response data as fallback
            logger.warning(
                "tool.create_priority.get_after_post_failed",
                correlation_id=correlation_id,
                user_id=user_id,
                error=str(get_error),
                error_type=type(get_error).__name__,
            )
            # Build minimal widget data from the just-created priority
            priorities = [_normalize_priority(priority)]
            google_connection = {"connected": False}  # Safe default
            fresh_available_keywords = None  # Will trigger defensive fallback in guidance

        # -------------------------------------------------------------------------
        # Step 7: Build structured response with widget
        # -------------------------------------------------------------------------
        guidance = _build_success_guidance(
            keyword=keyword,
            priority_name=priority_name,
            available_keywords=fresh_available_keywords,
            correlation_id=correlation_id,
        )

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Created priority: {priority_name} (assigned {keyword})"
            )],
            structuredContent={
                "success": True,
                "data": {
                    "priorities": priorities,
                    "google_connected": google_connection.get("connected", False),
                    # Default to [] for widget, but _build_success_guidance handles None defensively
                    "available_keywords": fresh_available_keywords if fresh_available_keywords is not None else [],
                },
                "_meta": {
                    "openai/outputTemplate": WIDGET_URI,
                },
                "assistant_guidance": guidance,
            },
        )

    except Exception as e:
        # Unexpected error - let dispatcher handle
        logger.error(
            "tool.create_priority.unexpected_error",
            correlation_id=correlation_id,
            user_id=user_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        raise


def _build_backend_error_response(error_code: str, error_message: str) -> mcp_types.CallToolResult:
    """Build error response for backend validation errors."""
    if error_code == "MAX_PRIORITIES_REACHED":
        guidance = {
            "action": ACTION_MAX_REACHED,
            "instruction": (
                "User already has 3 active priorities. Tell the user they've reached the maximum. "
                "If they want to add a new one, they'll need to retire or delete an existing priority first "
                "(available in their dashboard)."
            ),
        }
    elif error_code == "KEYWORD_CONFLICT":
        guidance = {
            "action": ACTION_RETRY,
            "instruction": (
                "A race condition occurred assigning the keyword. Retry the request without "
                "specifying a keyword (omit calendar_keyword) — the backend will auto-assign "
                "the next available one."
            ),
        }
    elif error_code == "VALIDATION_ERROR":
        guidance = {
            "action": ACTION_ASK_CLARIFYING,
            "instruction": (
                "Some required fields are missing or invalid. Ask the user to re-confirm "
                "the details for this priority type. Do not guess or fill in defaults."
            ),
        }
    else:
        guidance = {
            "action": ACTION_ERROR,
            "instruction": "An error occurred creating the priority. Please try again.",
        }

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text="Unable to create priority. Please try again.",  # Static; raw backend message stays in structuredContent only
        )],
        structuredContent={
            "success": False,
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
    title="Create Priority",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,
    handle=handle,
    read_only_hint=False,   # Creates data in database
    destructive_hint=False,  # Reverted: ChatGPT acts on destructiveHint for public tools — keep False for published app. Claude override handled in tools_list_dupl.py.
    open_world_hint=False,  # No external system interaction
    # widget_accessible intentionally NOT set (defaults False):
    # This tool requires verbatim provenance fields that widgets cannot provide.
    # Post-onboarding widget creation uses add_priority (private) which has no provenance gates.
)
