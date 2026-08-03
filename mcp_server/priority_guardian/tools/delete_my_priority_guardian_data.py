"""
delete_my_priority_guardian_data tool for Priority Guardian MCP.

Operation A from doc/ADR_008_data_ownership_and_deletion_model.md: delete the user's
Priority Guardian data, leaving every other Priority Guard Suite app untouched.

NAMING IS LOAD-BEARING (ADR_008 §4). This tool is "delete my Priority Guardian data",
never "delete my account". A user who typed "delete my account" and later found their
MindSort board gone would be right to object. The name, the title and the description all
say Priority Guardian, and the description states explicitly that other apps are unaffected.

CONFIRMATION IS THE HOST'S JOB. destructive_hint=True is what makes ChatGPT and Claude
surface their native confirmation before the call executes. No custom widget confirmation is
built here — §5 requires the platform's own, and a second bespoke confirmation would train
users to click through both.

ANNOTATIONS ARE SET IN THE SHARED ToolDefinition, NOT OVERRIDDEN PER PLATFORM.
mcp_server/priority_guardian_claude/tools_list_dupl.py carries
_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES, which exists because create_priority is deliberately
destructive_hint=False in the shared definition (to avoid ChatGPT's confirmation UI on a
creation tool) and needs raising to True on Claude. A deletion tool wants that confirmation
on BOTH platforms, so destructive_hint=True is set here and no override entry is added —
omitting a tool from that dict falls through to the shared value.

THE USER-FACING TEXT DESCRIBES CATEGORIES, NEVER SCHEMA (§5). No table names, no audit-log
id, no raw row counts reach the user. Those live in structuredContent for the widget and
tests, and in the backend's audit entry.
"""

import asyncio

import structlog
from mcp import types as mcp_types

from mcp_server.priority_guardian.http_client import backend_post
from .base import ToolDefinition, ToolUsageError

logger = structlog.get_logger(__name__)

# Timeout for backend calls (seconds) — must be under ChatGPT's ~10s window.
# Deletion touches several tables in one transaction; see the Part C report for the
# measurement at realistic maximum volume.
TIMEOUT_S = 8.0


async def _call_with_timeout(coro, op_name: str, correlation_id: str):
    """Wrap a coroutine with timeout."""
    try:
        return await asyncio.wait_for(coro, timeout=TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.warning(
            "tool.delete_my_priority_guardian_data.timeout",
            correlation_id=correlation_id,
            op_name=op_name,
            timeout=TIMEOUT_S,
        )
        raise ToolUsageError(
            f"{op_name} timed out. Your data has NOT been deleted. Please try again."
        )


# ============================================================================
# Tool Metadata
# ============================================================================

NAME = "delete_my_priority_guardian_data"

DESCRIPTION = (
    "Permanently deletes the user's Priority Guardian data. This cannot be undone.\n\n"
    "WHAT IT DELETES:\n"
    "- Priorities, their goals and deliverables\n"
    "- Weekly progress snapshots and tracking history\n"
    "- The Google Calendar connection (access is revoked at Google)\n"
    "- Priority Guardian authorization data\n\n"
    "WHAT IT DOES NOT DELETE:\n"
    "- Data belonging to other Priority Guard apps. MindSort AI boards are NOT affected.\n"
    "- A limited security audit record, retained up to 90 days\n"
    "- The shared sign-in identity other Priority Guard apps need\n\n"
    "BEFORE CALLING: Confirm with the user what will be deleted, in the terms above. Only "
    "call after they confirm. The user will also see the platform's own confirmation prompt.\n\n"
    "Call this tool:\n"
    "- When the user explicitly asks to delete their Priority Guardian data, priorities, or "
    "tracking history\n\n"
    "Do NOT call this tool:\n"
    "- To delete a single priority — that is a different operation\n"
    "- When the user wants to disconnect Google Calendar but keep their priorities\n"
    "- When the user asks to delete their whole account across all Priority Guard apps. This "
    "tool only removes Priority Guardian data; direct them to support for anything wider.\n"
    "- To 'reset' or 'start over' without the user understanding the data is gone permanently"
)

INPUT_SCHEMA = {
    "type": "object",
    "properties": {},
    "required": [],
    "additionalProperties": False,
}

REQUIRED_SCOPES = ["pg.access"]

# No widget. Deletion produces a plain confirmation the assistant narrates; rendering a
# dashboard of just-deleted data would be incoherent.
WIDGET_URI = None


ASSISTANT_GUIDANCE = (
    "Confirm plainly that the deletion is done. One or two sentences, warm and factual. "
    "Name the categories that were removed — priorities and their goals and deliverables, "
    "weekly progress history, the Google Calendar connection, and Priority Guardian "
    "authorization. "
    "State that other Priority Guard apps were not affected, and that MindSort AI boards are "
    "untouched. "
    "If asked what remains: a limited security audit record for up to 90 days, and the shared "
    "sign-in identity the other apps need. "
    "Do NOT list table names, row counts, or any internal identifier — describe categories "
    "only. "
    "Do not offer to undo it; it cannot be undone. Do not suggest recreating their priorities "
    "unless the user asks."
)

ASSISTANT_GUIDANCE_RETRYABLE = (
    "The deletion did NOT complete and nothing was removed. Tell the user plainly that their "
    "data is still there and the operation can be retried. "
    "If calendar_access_revoked is true, also tell them their Google Calendar connection was "
    "already disconnected as part of the attempt, so Priority Guardian has stopped reading "
    "their calendar even though the data remains. Do not describe this as 'nothing happened'. "
    "Do not speculate about the cause."
)


# ============================================================================
# Handler
# ============================================================================

async def handle(
    user_id: str,
    correlation_id: str,
    _arguments: dict,
) -> mcp_types.CallToolResult:
    """
    Delete the user's Priority Guardian data.

    Args:
        user_id: Validated user ID from JWT token. On ChatGPT this is already the reconciled
            canonical id — mcp_auth reconciles before handlers run (ADR_007 §3).
        correlation_id: Request correlation ID
        _arguments: none

    Returns:
        CallToolResult. The text the user reads describes categories only; per-table counts
        stay in structuredContent.
    """
    logger.info(
        "tool.delete_my_priority_guardian_data.start",
        correlation_id=correlation_id,
        user_id=user_id,
    )

    result = await _call_with_timeout(
        backend_post(
            "/api/priority-guardian/delete-data",
            {},
            user_id,
            correlation_id,
        ),
        "Deletion",
        correlation_id,
    )

    # The backend returns 503 with retryable=true when local deletion failed and was rolled
    # back. That is NOT "nothing changed" — Google access may already be gone.
    if not result.get("success"):
        detail = result.get("detail") or {}
        retryable = bool(detail.get("retryable")) if isinstance(detail, dict) else False
        google_revoked = (
            bool(detail.get("google_revocation_confirmed")) if isinstance(detail, dict) else False
        )

        logger.warning(
            "tool.delete_my_priority_guardian_data.failed",
            correlation_id=correlation_id,
            user_id=user_id,
            retryable=retryable,
            google_revocation_confirmed=google_revoked,
        )

        text = (
            "Your Priority Guardian data was not deleted and nothing was removed. "
            "You can try again."
        )
        if google_revoked:
            text += (
                " Your Google Calendar connection was disconnected during the attempt, so "
                "Priority Guardian is no longer reading your calendar."
            )

        return mcp_types.CallToolResult(
            isError=True,
            content=[mcp_types.TextContent(type="text", text=text)],
            structuredContent={
                "success": False,
                "retryable": retryable,
                "calendar_access_revoked": google_revoked,
                "assistant_guidance": ASSISTANT_GUIDANCE_RETRYABLE,
            },
        )

    data = result.get("data", result)
    google_confirmed = bool(data.get("google_revocation_confirmed"))

    logger.info(
        "tool.delete_my_priority_guardian_data.success",
        correlation_id=correlation_id,
        user_id=user_id,
        tables_affected=data.get("tables_affected"),
        google_revocation_confirmed=google_confirmed,
    )

    # Categories, never schema. The row counts and audit id stay in structuredContent.
    text = (
        "Your Priority Guardian data has been deleted: priorities, goals and deliverables; "
        "weekly progress history; the Google Calendar connection; and Priority Guardian "
        "authorization data. "
        "Your other Priority Guard apps are unaffected — MindSort AI boards were not touched. "
        "Retained: a limited security audit record for up to 90 days, and the shared sign-in "
        "identity the other apps need."
    )

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text=text)],
        structuredContent={
            "success": True,
            "calendar_access_revoked": google_confirmed,
            "deleted_categories": [
                "priorities, goals and deliverables",
                "weekly progress snapshots",
                "Google Calendar connection",
                "Priority Guardian authorization data",
            ],
            "retained_categories": [
                "security audit record (up to 90 days)",
                "shared Priority Guard sign-in identity",
            ],
            "assistant_guidance": ASSISTANT_GUIDANCE,
        },
    )


# ============================================================================
# Tool Definition
# ============================================================================

DELETE_MY_PRIORITY_GUARDIAN_DATA = ToolDefinition(
    name=NAME,
    title="Delete My Priority Guardian Data",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    required_scopes=REQUIRED_SCOPES,
    widget_uri=WIDGET_URI,
    handle=handle,
    read_only_hint=False,     # Permanently deletes data
    destructive_hint=True,    # §5: mandatory on BOTH platforms; no Claude override entry
    # True: the backend revokes the user's token at Google as step 1, which is an external,
    # open-system interaction. Matches this registry's own convention for the same behaviour —
    # get_priorities.py:332, get_priority_events and render_weekly_report all set True with
    # the comment "Calls Google Calendar API via backend".
    #
    # CORRECTION, 2026-08-03. The increment briefing §5 originally mandated
    # openWorldHint=False. Implemented as False first (briefing constraints are binding —
    # RULE 0a), flagged, and corrected by Nadja: the False was reasoning about confirmation
    # gating, which destructiveHint handles alone. openWorldHint was never doing that work,
    # and False would have misdescribed the tool — Anthropic policy §2.B requires
    # descriptions to precisely match actual functionality, and annotations are part of that.
    # Briefing §5 updated to match, so the spec and the code agree.
    open_world_hint=True,
    widget_accessible=False,  # Never callable from a widget — host confirmation is required
)
