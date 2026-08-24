"""
Unit tests for the Claude-only description/schema override layer in
priority_guardian_claude/tools_list_dupl.py.

Guards the platform split established 2026-08-24 (see
doc/Claude_Compliance/audit results/PG_CLAUDE_MCP_TOOL_AUDIT_2026-08-24.md):
mcp_server/priority_guardian/tools/*.py is shared with the published ChatGPT
app. Claude-only compliance wording must live in the override dicts here,
never in the shared files — and the override mechanism must only ever touch
`description` strings, never silently diverge from the shared schema's
actual validation rules (type, enum, required, pattern, additionalProperties,
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


def _without_description(node):
    node = copy.deepcopy(node)
    node.pop("description", None)
    return node


@pytest.mark.asyncio
async def test_claude_tools_match_shared_public_visibility_set():
    """Claude's advertised tool set is exactly the shared registry's public tools — no more, no fewer."""
    from mcp_server.priority_guardian.tools import TOOL_REGISTRY
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude

    shared_public = {name for name, td in TOOL_REGISTRY.items() if td.visibility == "public"}
    claude_names = {t.name for t in await list_tools_for_claude()}

    assert claude_names == shared_public


@pytest.mark.asyncio
async def test_schema_patches_change_only_description():
    """For every patched schema property, every key except `description` matches the
    shared registry's schema exactly — type, enum, required-ness (minLength/maxLength),
    pattern, and any nested `items` contract."""
    from mcp_server.priority_guardian.tools import TOOL_REGISTRY
    from mcp_server.priority_guardian_claude.tools_list_dupl import (
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

            assert claude_node["description"] != shared_node.get("description"), (
                f"{tool_name}{path}: description was not actually overridden"
            )
            assert _without_description(shared_node) == _without_description(claude_node), (
                f"{tool_name}{path}: a non-description key diverged from the shared schema"
            )


@pytest.mark.asyncio
async def test_patched_tool_schemas_preserve_structure():
    """required[], additionalProperties, and the property-name set are identical between
    the shared and Claude schemas for every tool with a description patch — the patch
    mechanism must never add, remove, or reorder fields."""
    from mcp_server.priority_guardian.tools import TOOL_REGISTRY
    from mcp_server.priority_guardian_claude.tools_list_dupl import (
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
    that the published ChatGPT app also reads from."""
    from mcp_server.priority_guardian.tools import TOOL_REGISTRY
    from mcp_server.priority_guardian_claude.tools_list_dupl import (
        list_tools_for_claude,
        _CLAUDE_SCHEMA_DESCRIPTION_PATCHES,
    )

    claude_tools = {t.name: t for t in await list_tools_for_claude()}

    for tool_name in _CLAUDE_SCHEMA_DESCRIPTION_PATCHES:
        claude_tools[tool_name].inputSchema["_test_poison"] = True

    for tool_name in _CLAUDE_SCHEMA_DESCRIPTION_PATCHES:
        assert "_test_poison" not in TOOL_REGISTRY[tool_name].input_schema


@pytest.mark.asyncio
async def test_description_overrides_drop_coaching_markers_for_claude():
    """Claude's description for each overridden tool does not contain the ChatGPT-only
    coaching/tone/imperative-sequencing language the audit flagged."""
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude

    claude_tools = {t.name: t for t in await list_tools_for_claude()}

    forbidden_markers = {
        "create_priority": ["coaching register", "warm and acknowledging", "empathically"],
        "onboarding_calendar_setup": ["empathically", "Example for empathic tone"],
        "inspect_adapt": ["ONE question at a time", "NEVER exceed"],
        "get_priority_events": ["IMMEDIATELY call"],
        "render_weekly_report": ["immediately call"],
    }

    for tool_name, markers in forbidden_markers.items():
        description = claude_tools[tool_name].description
        for marker in markers:
            assert marker not in description, (
                f"{tool_name}: Claude description still contains {marker!r}"
            )


def test_shared_registry_still_serves_original_chatgpt_text():
    """The shared/OpenAI registry is untouched by the Claude override layer — ChatGPT's
    published app keeps its original coaching descriptions."""
    from mcp_server.priority_guardian.tools import TOOL_REGISTRY

    expected_markers = {
        "create_priority": "coaching register",
        "onboarding_calendar_setup": "empathically",
        "inspect_adapt": "ONE question at a time",
        "get_priority_events": "IMMEDIATELY call",
        "render_weekly_report": "immediately call",
    }

    for tool_name, marker in expected_markers.items():
        assert marker in TOOL_REGISTRY[tool_name].description, (
            f"{tool_name}: shared/ChatGPT description lost {marker!r} — "
            "the Claude override layer must never modify the shared registry"
        )


@pytest.mark.asyncio
async def test_no_residual_conversational_verbs_in_claude_surface():
    """Scan the actual Claude-facing tools/list output (not source files) for
    conversational/behavioral vocabulary. Legitimate "when the user asks/is asking"
    invocation boundaries and "mentioned by the user" (describing the user's own
    words) are allowed; every other hit is a real finding.

    Vocabulary includes walk/teach/guide/facilitate — missed by an earlier pass
    of this check because it only searched for the bare word "ask", not "asks"/
    "asking", and never included these four at all.
    """
    from mcp_server.priority_guardian_claude.tools_list_dupl import list_tools_for_claude

    # Word-boundary regexes — a plain substring search would false-positive on e.g.
    # "ask" inside "tasks" or "wait" inside "waiting" being a different word entirely.
    terms = [
        r"\bwalk(s|ed|ing)?\b", r"\bteach(es|ing)?\b", r"\bguide[sd]?\b", r"\bfacilitate[sd]?\b",
        r"\bask\b", r"\bexplain(s|ed|ing)?\b", r"\bwait(s|ed|ing)?\b",
        r"\bmention(s|ed|ing)?\b", r"\bnarrate[sd]?\b",
        r"\btone\b", r"\bcoach(es)?\b", r"\bempath\w*\b", r"\bgently\b", r"\bwarm(ly)?\b",
        r"\bimmediately\b", r"no confirmation",
    ]
    allowed_snippets = ("when the user", "mentioned by the user")

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
            for term in terms:
                for m in re.finditer(term, low):
                    start, end = max(0, m.start() - 40), min(len(text), m.end() + 40)
                    snippet = text[start:end].lower()
                    if not any(a in snippet for a in allowed_snippets):
                        findings.append(f"{t.name}::{field}: ...{text[start:end]!r}...")

    assert not findings, "Residual conversational/behavioral vocabulary found:\n" + "\n".join(findings)


@pytest.mark.asyncio
async def test_non_overridden_tools_are_byte_identical_to_shared():
    """Tools with no entry in _CLAUDE_DESCRIPTION_OVERRIDES get the shared registry's
    description verbatim — no silent divergence for tools nobody meant to change."""
    from mcp_server.priority_guardian.tools import TOOL_REGISTRY
    from mcp_server.priority_guardian_claude.tools_list_dupl import (
        list_tools_for_claude,
        _CLAUDE_DESCRIPTION_OVERRIDES,
    )

    claude_tools = {t.name: t for t in await list_tools_for_claude()}
    overridden = set(_CLAUDE_DESCRIPTION_OVERRIDES)

    for name, tool_def in TOOL_REGISTRY.items():
        if tool_def.visibility != "public" or name in overridden:
            continue
        assert claude_tools[name].description == tool_def.description
