# (duplicate) — exists only because shared list_tools() embeds ChatGPT-specific _meta.
# Reads from mcp_server/priority_guardian/tools/ (source of truth — never modified here).
# Post-OpenAI-approval refactor: move to mcp_server/shared/ and delete this file.

from copy import deepcopy
from mcp import types as mcp_types

from mcp_server.priority_guardian.tools import TOOL_REGISTRY


def _derive_title(tool_name: str) -> str:
    """Derive human-readable title from snake_case tool name."""
    return " ".join(word.capitalize() for word in tool_name.split("_"))


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

        tool = mcp_types.Tool(
            name=tool_def.name,
            description=tool_def.description,
            inputSchema=deepcopy(tool_def.input_schema),
            _meta=None,
        )

        # Set annotations with hints from ToolDefinition
        tool.annotations = mcp_types.ToolAnnotations(
            title=_derive_title(tool_def.name),
            readOnlyHint=tool_def.read_only_hint,
            destructiveHint=tool_def.destructive_hint,
            openWorldHint=tool_def.open_world_hint,
        )

        tools.append(tool)

    return tools
