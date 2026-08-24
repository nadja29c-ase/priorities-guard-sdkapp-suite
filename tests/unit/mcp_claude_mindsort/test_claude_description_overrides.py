"""
Unit tests for the Claude-only description/schema override layer in
mindsort_claude/tools_list_dupl.py.

Guards the platform split established 2026-08-24 (see
doc/Claude_Compliance/audit results/MINDSORT_CLAUDE_MCP_TOOL_AUDIT_2026-08-24.md):
mcp_server/clarity/tools/*.py is shared with the published MindSort·OpenAI app.
Claude-only compliance wording must live in the override dicts here, never in
the shared files — and the override mechanism must only ever touch
`description` strings, never silently diverge from the shared schema's actual
validation rules (type, enum, required, pattern, additionalProperties,
minLength/maxLength, items).
"""

import copy
import re

import pytest


def _get_at_path(d, path):
    node = d
    for key in path:
        node = node[key]
    return node


def _strip_all_descriptions(node):
    node = copy.deepcopy(node)

    def _strip(n):
        if isinstance(n, dict):
            n.pop("description", None)
            for v in n.values():
                _strip(v)
        elif isinstance(n, list):
            for v in n:
                _strip(v)

    _strip(node)
    return node


@pytest.mark.asyncio
async def test_claude_tools_match_advertised_allowlist():
    """Claude's advertised tool set is exactly CLAUDE_ADVERTISED_TOOLS — no more, no fewer."""
    from mcp_server.mindsort_claude.tools_list_dupl import (
        list_tools_for_claude,
        CLAUDE_ADVERTISED_TOOLS,
    )

    claude_names = {t.name for t in await list_tools_for_claude()}
    assert claude_names == CLAUDE_ADVERTISED_TOOLS


@pytest.mark.asyncio
async def test_schema_patches_change_only_description():
    """For every patched schema property, every key except `description` matches the
    shared registry's schema exactly, including nested subtrees that carry their own
    (also intentionally patched) description."""
    from mcp_server.clarity.tools import TOOL_REGISTRY
    from mcp_server.mindsort_claude.tools_list_dupl import (
        list_tools_for_claude,
        _CLAUDE_SCHEMA_DESCRIPTION_PATCHES,
    )

    claude_tools = {t.name: t for t in await list_tools_for_claude()}

    for tool_name, patches in _CLAUDE_SCHEMA_DESCRIPTION_PATCHES.items():
        shared_schema = TOOL_REGISTRY[tool_name].input_schema
        claude_schema = claude_tools[tool_name].inputSchema

        for path in patches:
            shared_node = _get_at_path(shared_schema, path)
            claude_node = _get_at_path(claude_schema, path)

            assert claude_node.get("description") != shared_node.get("description"), (
                f"{tool_name}{path}: description was not actually overridden"
            )
            assert _strip_all_descriptions(shared_node) == _strip_all_descriptions(claude_node), (
                f"{tool_name}{path}: a non-description key diverged from the shared schema"
            )


@pytest.mark.asyncio
async def test_patched_tool_schemas_preserve_structure():
    """required[], additionalProperties, and the property-name set are identical between
    the shared and Claude schemas for every tool with a description patch."""
    from mcp_server.clarity.tools import TOOL_REGISTRY
    from mcp_server.mindsort_claude.tools_list_dupl import (
        list_tools_for_claude,
        _CLAUDE_SCHEMA_DESCRIPTION_PATCHES,
    )

    claude_tools = {t.name: t for t in await list_tools_for_claude()}

    for tool_name in _CLAUDE_SCHEMA_DESCRIPTION_PATCHES:
        shared_schema = TOOL_REGISTRY[tool_name].input_schema
        claude_schema = claude_tools[tool_name].inputSchema

        assert shared_schema["required"] == claude_schema["required"]
        assert shared_schema["additionalProperties"] == claude_schema["additionalProperties"]
        assert set(shared_schema["properties"]) == set(claude_schema["properties"])


@pytest.mark.asyncio
async def test_claude_schema_is_independent_copy():
    """Mutating a Claude-facing schema must never mutate the shared TOOL_REGISTRY schema
    that the published MindSort·OpenAI app also reads from."""
    from mcp_server.clarity.tools import TOOL_REGISTRY
    from mcp_server.mindsort_claude.tools_list_dupl import (
        list_tools_for_claude,
        _CLAUDE_SCHEMA_DESCRIPTION_PATCHES,
    )

    claude_tools = {t.name: t for t in await list_tools_for_claude()}

    for tool_name in _CLAUDE_SCHEMA_DESCRIPTION_PATCHES:
        claude_tools[tool_name].inputSchema["_test_poison"] = True

    for tool_name in _CLAUDE_SCHEMA_DESCRIPTION_PATCHES:
        assert "_test_poison" not in TOOL_REGISTRY[tool_name].input_schema


@pytest.mark.asyncio
async def test_shared_registry_still_serves_original_chatgpt_text():
    """The shared/clarity registry is untouched by the Claude override layer — the
    published MindSort·OpenAI app keeps its original description text."""
    from mcp_server.clarity.tools import TOOL_REGISTRY

    expected_markers = {
        "organize_thoughts": "your default assistant behavior is SUSPENDED",
        "start_prioritization_flow": "your default assistant behavior is SUSPENDED",
        "load_saved_board": "Follow assistant_guidance in structuredContent",
        "read_board_before_editing": "ChatGPT handles",
        "edit_board": "AFTER TOOL RETURNS",
    }

    for tool_name, marker in expected_markers.items():
        assert marker in TOOL_REGISTRY[tool_name].description, (
            f"{tool_name}: shared/ChatGPT description lost {marker!r} — "
            "the Claude override layer must never modify the shared registry"
        )


@pytest.mark.asyncio
async def test_non_overridden_tools_are_byte_identical_to_shared():
    """delete_my_data has no override entry — it must get the shared registry's
    description verbatim."""
    from mcp_server.clarity.tools import TOOL_REGISTRY
    from mcp_server.mindsort_claude.tools_list_dupl import (
        list_tools_for_claude,
        _CLAUDE_DESCRIPTION_OVERRIDES,
        CLAUDE_ADVERTISED_TOOLS,
    )

    claude_tools = {t.name: t for t in await list_tools_for_claude()}
    overridden = set(_CLAUDE_DESCRIPTION_OVERRIDES)

    for name in CLAUDE_ADVERTISED_TOOLS - overridden:
        assert claude_tools[name].description == TOOL_REGISTRY[name].description


@pytest.mark.asyncio
async def test_no_forbidden_behavioral_text_in_claude_surface():
    """Scan the actual Claude-facing tools/list output (not source files) for the
    exact violation phrases the audit found — the checklist's own named
    "suspend default behavior" example, the persona assignment, the instruction to
    obey tool-result content, scripted tone direction, cross-platform leakage, and
    post-result narration scripting.

    Deliberately NOT applied to tool-result content (assistant_guidance) — that
    remains the isolated, intentionally-unresolved experimental variable, same as
    Priority Guardian.
    """
    from mcp_server.mindsort_claude.tools_list_dupl import list_tools_for_claude

    FORBIDDEN_CLAUDE_TOOL_TEXT = (
        "default assistant behavior is suspended",
        "your role instead is",
        "binding rules",
        "suspended behaviors",
        "fire-on-done",
        "follow assistant_guidance",
        "one warm sentence",
        "keep it light and inviting",
        "chatgpt handles",
        "after tool returns",
    )

    def walk_schema(schema, path, out):
        if isinstance(schema, dict):
            if isinstance(schema.get("description"), str):
                out[f"{path}.description"] = schema["description"]
            for k, v in schema.get("properties", {}).items():
                walk_schema(v, f"{path}.{k}", out)
            if "items" in schema:
                walk_schema(schema["items"], f"{path}[]", out)

    claude_tools = await list_tools_for_claude()
    findings = []
    for t in claude_tools:
        texts = {"DESCRIPTION": t.description}
        walk_schema(t.inputSchema, "schema", texts)
        for field, text in texts.items():
            low = text.lower()
            for term in FORBIDDEN_CLAUDE_TOOL_TEXT:
                if term in low:
                    findings.append(f"{t.name}::{field} contains {term!r}")

    assert not findings, "Forbidden behavioral text found in Claude surface:\n" + "\n".join(findings)
