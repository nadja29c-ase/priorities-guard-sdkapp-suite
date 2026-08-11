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

        tool = mcp_types.Tool(
            name=tool_def.name,
            description=tool_def.description,
            inputSchema=deepcopy(tool_def.input_schema),
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
