# (duplicate) — exists because shared list_tools() embeds ChatGPT-specific _meta.#
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

# Claude-specific destructiveHint overrides.
# create_priority has destructive_hint=False in shared ToolDefinition to preserve
# ChatGPT UX — ChatGPT shows confirmation UI for destructiveHint=True on public tools.
# Anthropic policy §5E requires True for any tool that writes data.
# All other write tools are visibility="private" so ChatGPT never sees their annotations.
_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES: dict[str, bool] = {
    "create_priority": True,
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

        # Set annotations with hints from ToolDefinition
        tool.annotations = mcp_types.ToolAnnotations(
            title=tool_def.title,
            readOnlyHint=tool_def.read_only_hint,
            destructiveHint=_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES.get(
                tool_def.name, tool_def.destructive_hint
            ),
            openWorldHint=tool_def.open_world_hint,
        )

        tools.append(tool)

    return tools
