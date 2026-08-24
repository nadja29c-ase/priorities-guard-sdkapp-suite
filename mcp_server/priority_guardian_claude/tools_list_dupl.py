# (duplicate) — exists because shared list_tools() embeds ChatGPT-specific _meta.
#
# !! NOT COMPARED. This file names no single source file, so the 2026-08-09
# divergence sweep could not compare it. Unswept is not the same as clean.
# See doc/DUPL_DIVERGENCE_SWEEP_2026-08-09.md.
# Reads from mcp_server/priority_guardian/tools/ (source of truth — never modified here).
# Post-OpenAI-approval refactor: move to mcp_server/shared/ and delete this file.

from copy import deepcopy
from mcp import types as mcp_types

from mcp_server.priority_guardian.tools import TOOL_REGISTRY
from mcp_server.priority_guardian_claude.response_adapter_dupl import WIDGET_URI, WIDGET_APP_DOMAIN

# Tools that render the widget (need _meta.ui.resourceUri in tool definition)
_WIDGET_TOOL_NAMES = {"get_priorities", "render_weekly_report", "create_priority"}

# Claude-specific readOnlyHint overrides.
#
# get_priorities is declared read_only_hint=True in the shared ToolDefinition and stays
# that way for ChatGPT (that app is published; this is not the moment to change its
# descriptor). On the Claude surface it is False, because the tool DOES modify persistent
# state on essentially every call:
#
#   1. ALWAYS (connected happy path): GET /calendar/time-allocation sets
#      connection.last_used_at (calendar_service.py:460, :498). calendar_service issues no
#      commit of its own — get_db() commits at successful request teardown
#      (backend/core/database.py:50), so the UPDATE lands on every call.
#   2. CONDITIONALLY: POST /snapshots/ensure inserts pg_weekly_snapshots rows and updates
#      aggregates (snapshot_service.py:393). This leg CAN no-op — it returns at
#      snapshot_service.py:151-158 when no weeks are missing — so it is the weaker half of
#      the case, not the load-bearing one.
#   3. CONDITIONALLY: expired-token refresh rewrites the connection's encrypted token and
#      commits (google_token_management.py:200-204). Shared with the other Google-reading
#      tools and left alone — session maintenance is defensible as read-only.
#
# MCP schema defines readOnlyHint as "the tool does not modify its environment". (1) makes
# that false unconditionally. Superseded rationale, kept here so it is not re-derived: the
# shared definition's comment argued the snapshot write was "invisible bookkeeping" — that
# reasoning addressed (2) only and never accounted for (1).
_CLAUDE_READ_ONLY_HINT_OVERRIDES: dict[str, bool] = {
    "get_priorities": False,
}

# Claude-specific destructiveHint overrides.
# create_priority has destructive_hint=False in shared ToolDefinition to preserve
# ChatGPT UX — ChatGPT shows confirmation UI for destructiveHint=True on public tools.
# Anthropic policy §5E requires True for any tool that writes data.
# All other write tools are visibility="private" so ChatGPT never sees their annotations.
#
# get_priorities follows create_priority's precedent: it writes, so the Claude surface
# declares it destructive while ChatGPT keeps the non-confirming descriptor. Note this
# tool is the widget's primary data load — the override is what keeps that confirmation
# prompt off the ChatGPT dashboard path.
_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES: dict[str, bool] = {
    "create_priority": True,
    "get_priorities": True,
}

# ============================================================================
# Claude-only description/schema overrides (compliance surface split)
# ============================================================================
#
# mcp_server/priority_guardian/tools/*.py is shared with the published ChatGPT
# app (mcp_server/priority_guardian/handlers/tools.py reads the same
# TOOL_REGISTRY). Some of those descriptions carry conversational-coaching
# content — tone direction, scripted example dialogue, a facilitation
# methodology — that is appropriate for the existing, already-shipped ChatGPT
# product but is not reproduced here for Claude. This section replaces only
# `description` text (top-level and schema-property) for Claude; it never
# touches the shared files, so ChatGPT's behavior is unaffected.
#
# See doc/Claude_Compliance/audit results/PG_CLAUDE_MCP_TOOL_AUDIT_2026-08-24.md.
#
# get_priority_events/render_weekly_report are overridden here only to drop
# "IMMEDIATELY call"/imperative cross-tool phrasing for experimental cleanliness —
# the audit rated their shared descriptions FUNCTIONAL CONTRACT / PASS. Tools not
# listed here (get_priorities, get_patterns, delete_my_priority_guardian_data) had
# no issue in their top-level description at all — Claude uses the shared text
# unchanged.
_CLAUDE_DESCRIPTION_OVERRIDES: dict[str, str] = {
    "create_priority": """Creates ONE priority AT A TIME for guarding and progress tracking against calendar time while onboarding the user, up to 3 priorities total. Call ONCE per priority — the user sets up priorities iteratively.

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

Required inputs: priority name, priority type (deadline vs flexible, the user's choice), and the type-specific fields for that type.""",

    "onboarding_calendar_setup": """Returns phase-specific educational content and user-specific Google Calendar data describing how Priority Guardian tracks time. When calendar access is permitted, responses may include the user's priorities, keywords, calendar data, and next-phase information.

Preconditions: priorities have been created and Google Calendar is connected through the dashboard. This tool does not establish the connection and is intended only for users who have not completed onboarding.

Supported phases are keyword_education, first_weekly_report, and reflection_setup. The server validates the requested phase but does not store or enforce phase progression.""",

    "inspect_adapt": """Validates a completed inspect-and-adapt reflection payload and returns the validated reflection items, linked action steps, and completion status. It does not conduct the reflection or persist the data.

CALL PRECONDITIONS — DO NOT CALL unless ALL are true:
- user_reflection_verbatim: non-empty, user's exact words for each reflection item
- user_action_verbatim: non-empty, final wording confirmed by the user for each action step
- derived_from_id: each action step links to a reflection item

Applicable after a weekly-reflection flow has produced all required reflection items and confirmed action steps. User intent to begin a reflection is not sufficient for invocation; the completed payload is required.""",

    "get_priority_events": """Fetch calendar events for a specific priority to enable a breakdown chart.

Call this tool ONLY when the user asks to break down or analyse their time within a single priority (e.g. "break down my P1 time", "what's in my P2 this week?").

Returns priorityEvents, from which semantic_groupings are derived and passed to render_weekly_report along with semantic_target to render the chart. Do NOT call this tool for the initial weekly report — use render_weekly_report directly.
Do NOT call this tool for past weeks (no event data available).""",

    "render_weekly_report": """Get your weekly report showing time invested in each priority, rendered as a pie chart.

Call this tool:
- When the user asks about their week, progress, or hours
- When the user says "how did I do?", "show my report", "weekly summary"
- At the start of a reflection or check-in conversation
- For a P1/P2/P3 breakdown, following a get_priority_events call, with semantic_groupings and semantic_target set

Do NOT call this tool:
- During onboarding or priority setup
- When the user is asking about patterns or trends over time (use get_patterns instead)
- To fetch events for a breakdown — use get_priority_events first, then call this tool""",
}

# Claude-only schema *property description* patches, applied after deepcopy() of the shared
# input_schema. Each path is walked from the schema root; only the "description" string at
# that path is replaced. type/enum/required/pattern/additionalProperties/minLength/maxLength
# are never touched here — they stay sourced from the shared registry, so there is nothing
# to drift out of sync with its validation rules. See test_schema_patches_preserve_validation
# in tests/unit/mcp_pg_claude/ for the check that only descriptions differ.
_CLAUDE_SCHEMA_DESCRIPTION_PATCHES: dict[str, dict[tuple, str]] = {
    "create_priority": {
        ("properties", "user_priority_type_verbatim"): (
            "Copy of the user's own words describing their priority type, in their natural "
            "language (not required to be the literal words 'deadline' or 'flexible'). "
            "deadline priorities have a non-negotiable external end date and concrete "
            "deliverables; Priority Guardian tracks what gets delivered by when. "
            "flexible priorities are ongoing commitments tracked via a weekly hour target "
            "and a one-month goal. A date mentioned by the user does not by itself indicate "
            "the deadline type — it may also describe a flexible priority's target date."
        ),
        ("properties", "type"): (
            "Priority type derived from the user's verbatim choice, mapped to one of the enum values."
        ),
        ("properties", "weekly_hour_target"): (
            "Number of hours per week the user intends to protect for this priority. "
            "Used for calendar-time tracking and progress comparison. Required when type=flexible."
        ),
        ("properties", "user_goal_verbatim"): (
            "The user's own description of the concrete outcome that would constitute "
            "success within approximately one month. Preserve the user's wording. "
            "Must be non-empty. Required when type=flexible."
        ),
        ("properties", "checkpoint_date"): (
            "ISO date (YYYY-MM-DD) when the user will evaluate progress against "
            "user_goal_verbatim. Accepts conversion from natural-language dates "
            "(e.g., 'mid-March', 'in 4 weeks'). Typically about one month out. "
            "Required when type=flexible."
        ),
        ("properties", "deadline"): (
            "ISO date (YYYY-MM-DD): the hard due date for this priority. "
            "Accepts conversion from natural-language dates (e.g., 'end of March', 'March 15th'). "
            "Required when type=deadline."
        ),
    },
    "onboarding_calendar_setup": {
        ("properties", "phase"): (
            "Which phase of onboarding step 2 to execute — keyword_education, "
            "first_weekly_report, or reflection_setup. Intended to be called in that order "
            "(each phase builds on data typically gathered in the previous one), but the "
            "server does not enforce or store phase progression."
        ),
    },
    "inspect_adapt": {
        ("properties", "reflection_items", "items", "properties", "user_reflection_verbatim"): (
            "The user's own account of what supported or obstructed progress toward a "
            "priority this period. Preserve the user's wording. Must be non-empty."
        ),
        # user_action_verbatim is not patched here — the shared-registry fix already
        # resolves the verbatim/rephrasing contradiction identically for both platforms.
    },
    "get_priority_events": {
        ("properties", "semantic_target"): (
            "Priority keyword identifying which priority's calendar events to fetch. "
            "Returns priorityEvents from which semantic_groupings are derived. "
            "render_weekly_report accepts those derived groupings together with semantic_target."
        ),
    },
    "render_weekly_report": {
        ("properties", "semantic_groupings"): (
            "Semantic categories for the target slice. "
            "When provided together with semantic_target, replaces that category's slice "
            "in the pie chart with these subcategory slices. "
            "For an 'other' breakdown, these are the groupings confirmed by the user. "
            "For a priority breakdown (P1/P2/P3), these are the groupings derived from "
            "get_priority_events's returned events."
        ),
        ("properties", "semantic_target"): (
            "With semantic_groupings: replaces that category's slice in the chart with "
            "subcategory slices. For 'other', this follows user-confirmed groupings. "
            "For P1/P2/P3, this follows a get_priority_events call for the same priority."
        ),
    },
}


def _patch_schema_descriptions(schema: dict, patches: dict[tuple, str]) -> dict:
    """
    Apply description-only patches to a deep-copied input_schema, by path.

    Only the "description" string at each path is replaced. Every other schema
    keyword at that path — type, enum, required, pattern, additionalProperties,
    minLength, maxLength, items — is left exactly as the shared registry defined
    it, so there is nothing here to drift out of sync with its validation rules.
    """
    for path, new_description in patches.items():
        node = schema
        for key in path:
            node = node[key]
        node["description"] = new_description
    return schema


async def list_tools_for_claude() -> list[mcp_types.Tool]:
    """
    Build MCP Tool list for Claude.

    Filters to public tools only. Sets _meta=None (no OpenAI Apps SDK fields).
    Uses ToolAnnotations with hints from ToolDefinition.
    Sorted by name for deterministic output.
    """
    tools = []

    # Sort by name for deterministic output
    for tool_def in sorted(TOOL_REGISTRY.values(), key=lambda t: t.name):
        # Filter: only public tools
        if tool_def.visibility != "public":
            continue

        # Widget tools have _meta for host-side prefetch (MCP Apps spec)
        if tool_def.name in _WIDGET_TOOL_NAMES:
            tool_meta = {"ui": {"resourceUri": WIDGET_URI, "domain": WIDGET_APP_DOMAIN}}
        else:
            tool_meta = None

        # Claude-only description/schema overrides — see block above. Falls through to the
        # shared registry's text for any tool/field with no override entry.
        description = _CLAUDE_DESCRIPTION_OVERRIDES.get(tool_def.name, tool_def.description)
        input_schema = deepcopy(tool_def.input_schema)
        if tool_def.name in _CLAUDE_SCHEMA_DESCRIPTION_PATCHES:
            input_schema = _patch_schema_descriptions(
                input_schema, _CLAUDE_SCHEMA_DESCRIPTION_PATCHES[tool_def.name]
            )

        tool = mcp_types.Tool(
            name=tool_def.name,
            description=description,
            inputSchema=input_schema,
            _meta=tool_meta,
        )

        # Set annotations with hints from ToolDefinition, applying Claude-side overrides
        tool.annotations = mcp_types.ToolAnnotations(
            title=tool_def.title,
            readOnlyHint=_CLAUDE_READ_ONLY_HINT_OVERRIDES.get(
                tool_def.name, tool_def.read_only_hint
            ),
            destructiveHint=_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES.get(
                tool_def.name, tool_def.destructive_hint
            ),
            openWorldHint=tool_def.open_world_hint,
        )

        tools.append(tool)

    return tools
