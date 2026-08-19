# (duplicate) — exists because shared list_tools() embeds ChatGPT-specific _meta.
#
# !! NOT COMPARED. This file names no single source file, so the 2026-08-09
# divergence sweep could not compare it. Unswept is not the same as clean.
# See doc/DUPL_DIVERGENCE_SWEEP_2026-08-09.md.
# Reads from mcp_server/clarity/tools/ (source of truth — never modified here).
# Consolidate into shared/ ONLY if this file proves to churn — not preemptively.

from copy import deepcopy

from mcp import types as mcp_types

from mcp_server.clarity.tools import TOOL_REGISTRY
# Import WIDGET_URI from the single production definition (Widget-0 requirement)
from mcp_server.mindsort_claude.handlers.resources_dupl import WIDGET_URI


# Title overrides for tools that don't title-case cleanly (§8.1(a))
_TITLE_OVERRIDES = {
    "start_prioritization_flow": "Set Priorities",
    "read_board_before_editing": "Read Board",
    "delete_my_data": "Delete My Data",
}


def _derive_title(tool_name: str) -> str:
    """Derive title from tool name. Use override if available, else title-case split."""
    if tool_name in _TITLE_OVERRIDES:
        return _TITLE_OVERRIDES[tool_name]
    return " ".join(word.capitalize() for word in tool_name.split("_"))


# destructiveHint overrides for Claude (§8.2)
# start_prioritization_flow writes/overwrites DB priorities; "reversible" is irrelevant to destructiveHint
_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES = {
    "start_prioritization_flow": True,
}


# ============================================================================
# Widget-producing tools (Widget-0)
# ============================================================================
# These tools get _meta.ui.resourceUri pointing to the Claude widget.
# Verified from clarity/tools/ register_tool() blocks — do not guess.
# See inc_03_widget0.md "Widget-producing tools" section.
#
# Tools that produce widget output:
#   - organize_thoughts: WIDGET_URI
#   - load_saved_board: WIDGET_URI
#   - start_prioritization_flow: WIDGET_URI
#   - edit_board: WIDGET_URI
#
# Tools that do NOT produce widget output (keep _meta=None):
#   - read_board_before_editing: explicitly "Never produces widget"
#   - delete_my_data: no widget output
_WIDGET_PRODUCING_TOOLS = {
    "organize_thoughts",
    "load_saved_board",
    "start_prioritization_flow",
    "edit_board",
}


# ============================================================================
# Advertisement allowlist — what MindSort-Claude tells Claude exists
# ============================================================================
# THE CONTRACT THIS FILE PREVIOUSLY LACKED. Advertisement used to be derived
# implicitly from "whatever is in the shared TOOL_REGISTRY", so a tool added to
# shared code for EITHER platform was silently advertised on the OTHER. That is
# how `_diagnostic_tiny_widget` — an OpenAI-only diagnostic (inc_91, 1bbd16c) —
# came to be advertised to Claude while being absent from Claude's TOOL_SCOPES,
# i.e. advertised but guaranteed to 403 at scope enforcement.
#
# ALLOWLIST, NOT AN EXCLUSION SET OR A registry∩TOOL_SCOPES INTERSECTION.
# Failure asymmetry is the reason: a mistake here fails as OMISSION (an intended
# tool doesn't appear — loud, caught in the first test conversation), never as
# OVER-EXPOSURE (a tool appears that shouldn't — the failure that actually
# happened, and stayed invisible for six weeks until a compliance audit).
#
# Advertisement and authorization are DISTINCT concerns and are deliberately not
# conflated: TOOL_SCOPES answers "may this caller invoke it?"; this set answers
# "should Claude know it exists?". Adding a Claude tool therefore needs BOTH.
#
# Do NOT replace this with a naming convention (e.g. skipping "_"-prefixed
# names) — that is brittle and semantic by accident.
CLAUDE_ADVERTISED_TOOLS = {
    "organize_thoughts",
    "load_saved_board",
    "read_board_before_editing",
    "start_prioritization_flow",
    "edit_board",
    "delete_my_data",
}


async def list_tools_for_claude() -> list[mcp_types.Tool]:
    """
    Build MCP Tool list from registry for Claude.

    Rules:
    - Advertises ONLY tools named in CLAUDE_ADVERTISED_TOOLS — deliberately a
      subset of the shared registry, which also carries OpenAI-only tools
    - Derives title from tool name
    - Applies destructiveHint overrides for Claude
    - Widget-producing tools get _meta.ui.resourceUri; others get _meta=None
    - Returns tools sorted by name for deterministic output
    """
    tools = []

    # Sort by name for deterministic output
    for tool_def in sorted(TOOL_REGISTRY.values(), key=lambda t: t.name):
        # Advertisement allowlist — see CLAUDE_ADVERTISED_TOOLS above.
        # Anything in the shared registry that Claude does not claim is skipped.
        if tool_def.name not in CLAUDE_ADVERTISED_TOOLS:
            continue

        # Build annotations (camelCase kwargs, snake_case sources)
        annotations = mcp_types.ToolAnnotations(
            title=_derive_title(tool_def.name),
            readOnlyHint=tool_def.read_only_hint,
            destructiveHint=_CLAUDE_DESTRUCTIVE_HINT_OVERRIDES.get(
                tool_def.name, tool_def.destructive_hint
            ),
            openWorldHint=tool_def.open_world_hint,
        )

        # Widget-producing tools get _meta.ui.resourceUri (Widget-0)
        # Non-widget tools keep _meta=None
        if tool_def.name in _WIDGET_PRODUCING_TOOLS:
            tool_meta = {"ui": {"resourceUri": WIDGET_URI}}
        else:
            tool_meta = None

        tool = mcp_types.Tool(
            name=tool_def.name,
            description=tool_def.description,
            inputSchema=deepcopy(tool_def.input_schema),
            _meta=tool_meta,
        )

        # Set annotations unconditionally (PG pattern; annotations is a declared SDK field)
        tool.annotations = annotations

        tools.append(tool)

    return tools
