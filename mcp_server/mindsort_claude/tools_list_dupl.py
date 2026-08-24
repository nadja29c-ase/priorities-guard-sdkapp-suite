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
# Claude-only description/schema overrides (compliance surface split)
# ============================================================================
#
# mcp_server/clarity/tools/*.py is shared with the published MindSort·OpenAI app
# (mcp_server/clarity/tools/__init__.py reads the same TOOL_REGISTRY). Some of
# those descriptions carry conversational-coaching content — persona assignment,
# "your default assistant behavior is SUSPENDED", scripted dialogue, an
# instruction to obey tool-result content as commands — that is not reproduced
# here for Claude. This section replaces only `description` text (top-level and
# schema-property) for Claude; it never touches the shared files, so ChatGPT's
# behavior is unaffected.
#
# See doc/Claude_Compliance/audit results/MINDSORT_CLAUDE_MCP_TOOL_AUDIT_2026-08-24.md.
#
# delete_my_data has no entry here — its shared description had no coaching
# content to begin with; Claude uses the shared text unchanged.
_CLAUDE_DESCRIPTION_OVERRIDES: dict[str, str] = {
    "organize_thoughts": """
Creates and persists a MindSort board from a complete set of user-provided thoughts, represented in the tool input as visual clusters.

Intended for cognitive-overload or brain-dump requests involving scattered, unstructured thoughts. It is not intended for planning, scheduling, project execution, general productivity questions, or emotional and relationship decisions.

MindSort workflow context: thought collection precedes clustering. This tool validates, normalizes, and persists the clustered representation. A valid call requires:
- thoughts_exhausted = true
- user_confirmed_no_more_thoughts = true
- user_thoughts_exhausted_verbatim contains the user's explicit completion statement
- clusters contains the complete thought set to be placed on the board

Valid completion evidence is an explicit statement from the user that no additional thoughts remain. Silence and item count are not completion evidence.

The tool also supports replacing or reclustering an existing board from a complete merged thought set. A successful call overwrites the saved board and has no undo.
""",

    "load_saved_board": """
Retrieves the user's saved MindSort board and displays it through the board widget.

This tool is available only for explicit board-display requests, such as viewing, showing, or loading the board. It is not a general context-retrieval tool and is not used for planning or unrelated task execution.

For existing-board data needed before merging or reclustering, use read_board_before_editing. For targeted board modifications, use edit_board.

The result represents one of four states: backend error, no saved board, an intentionally empty saved board, or a saved board containing clusters.
""",

    "read_board_before_editing": """
Retrieves the user's saved MindSort board data without rendering the board widget.

Used when the existing board contents are required to construct a complete merged or reclustered board before an organize_thoughts call—for example, when adding many thoughts or reorganizing existing clusters.

It is not used for displaying the board, general context retrieval, planning, or unrelated requests. Explicit board-display requests use load_saved_board. Targeted additions, renames, deletions, tags, or priority changes use edit_board.

The result contains clusters, board-history state, empty-snapshot state, and the saved-board hash when available.
""",

    "start_prioritization_flow": """
Applies and persists up to three user-selected priority assignments on an existing MindSort board. The saved board is fetched automatically.

MindSort prioritization uses a user-stated criterion—such as progress toward a goal, removal of a blocker, or relief—followed by explicit user-selected board targets. This tool records those decisions; it does not infer or choose priorities.

A valid call requires:
- user_prioritization_criterion_verbatim contains the user's stated criterion
- user_priorities_verbatim contains the user's explicitly stated priority choices
- priorities contains the corresponding assignments

The priorities array replaces the board's current assignments rather than appending to them. A later call adding another priority therefore contains the full cumulative priority set, including previously confirmed assignments. Maximum: three assignments.

Cluster and subcluster targets are identified with name. Individual thought-item targets are identified with item_index and parent_name.
""",

    "edit_board": """
Performs targeted modifications on an existing MindSort board. Supported changes include adding a small number of items, renaming or deleting board elements, adding or removing tags, setting or clearing priorities, and applying batches of specific operations.

Board existence must already be established in the current conversation through load_saved_board, read_board_before_editing, or organize_thoughts. The board is fetched automatically; no board payload is accepted.

This tool is appropriate for:
- One to three targeted additions with known destination clusters
- Specific renames, deletions, tags, or priority changes
- Several clearly specified operations supplied through the operations array
- Reassigning or swapping priorities already present on the board

Four or more new thoughts, ambiguous placement, or requests to reorganize the board require the complete-board flow: read_board_before_editing followed by organize_thoughts.

Initial priority selection based on a prioritization criterion uses start_prioritization_flow rather than edit_board.

Thought items can be targeted by exact text, with parent_name when duplicate text exists. If both text and item_index are supplied, item_index takes precedence.
""",
}

# Claude-only schema *property description* patches, applied after deepcopy() of the shared
# input_schema. Each path is walked from the schema root; only the "description" string at
# that path is replaced. type/enum/required/pattern/additionalProperties/minLength/maxLength
# are never touched here — they stay sourced from the shared registry, so there is nothing
# to drift out of sync with its validation rules.
_CLAUDE_SCHEMA_DESCRIPTION_PATCHES: dict[str, dict[tuple, str]] = {
    "organize_thoughts": {
        ("properties", "user_thoughts_exhausted_verbatim"): (
            "The user's explicit statement that they have no additional thoughts "
            "to add. Preserve the user's wording. Must be non-empty."
        ),
        ("properties", "thoughts_exhausted"): (
            "True when the user has explicitly indicated that the thought-collection "
            "stage is complete. Silence or item count does not establish completion."
        ),
        ("properties", "user_confirmed_no_more_thoughts"): (
            "True when the user explicitly confirms that no additional thoughts remain. "
            "The confirmation is user-provided rather than inferred."
        ),
        ("properties", "clusters", "items", "properties", "cluster_name"): (
            "Name representing the common theme of the contained thought items. "
            "Specific theme names are preferred over broad labels such as Work, "
            "Personal, Health, or Tasks. User wording is retained when it already "
            "identifies the theme clearly."
        ),
    },
    "start_prioritization_flow": {
        ("properties", "user_prioritization_criterion_verbatim"): (
            "The user's own words describing what matters most in the current "
            "prioritization decision. Common criterion categories include progress "
            "toward a goal, removing a blocker, and obtaining relief. Must be non-empty."
        ),
        ("properties", "user_priorities_verbatim"): (
            "The user's own words explicitly naming their selected board priorities "
            "and, when stated, their relative ranking. Must be non-empty."
        ),
        ("properties", "priorities"): (
            "Complete cumulative set of priority assignments that will replace the "
            "board's current assignments. Cluster and subcluster targets use name; "
            "thought-item targets use item_index with parent_name. Maximum 3."
        ),
        ("properties", "priorities", "items", "properties", "reason"): (
            "Criterion category associated with this assignment: blocker for removing "
            "an obstacle, goal-aligned for progress toward a stated goal, or relief "
            "for reducing mental load or stress."
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

        # Claude-only description/schema overrides — see block above. Falls through to
        # the shared registry's text for any tool/field with no override entry.
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

        # Set annotations unconditionally (PG pattern; annotations is a declared SDK field)
        tool.annotations = annotations

        tools.append(tool)

    return tools
