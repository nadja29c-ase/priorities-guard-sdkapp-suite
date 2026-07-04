"""
Tool scope invariant tests.

Ensures all registered tools have non-empty required_scopes and that enforcement
sources stay synchronized with tool registries.

Background: audience is shared suite-wide (aud=www for tokens minted without
resource param), so scope enforcement is the only cross-app isolation mechanism.
A tool registered with empty required_scopes becomes callable by any valid token
from any app in the suite — a MindSort clarity.write token could invoke it.

ENFORCEMENT-SOURCE MATRIX
-------------------------
App             | Metadata source           | Enforcement source
----------------|---------------------------|--------------------
PG-OpenAI       | TOOL_REGISTRY.required_scopes | TOOL_REGISTRY.required_scopes
MindSort-OpenAI | TOOL_REGISTRY.required_scopes | config.TOOL_SCOPES dict
PG-Claude       | (shares PG-OpenAI registry)   | (shares PG-OpenAI registry)
MindSort-Claude | (no registry, _dupl pattern)  | config.TOOL_SCOPES dict

PG-Claude coverage: covered via shared registry — tools_dupl.py imports get_tool
from mcp_server.priority_guardian.tools, the same TOOL_REGISTRY object that
test_pg_openai_all_tools_have_scopes iterates. No separate test needed.

IMPORT CONSTRAINT
-----------------
Import config modules only, NEVER mcp_auth or the shim (mcp_auth_dupl).
The shim executes process-wide rebinding on import — see the warning header in
mcp_server/mindsort_claude/mcp_auth_dupl.py. Violating this contaminates the
test session and causes cross-test pollution.

This test module catches misregistrations at CI time rather than in production.
"""

import pytest


class TestToolScopeInvariants:
    """Ensure all tools have non-empty required_scopes for cross-app isolation."""

    # =========================================================================
    # Registry-based tests (metadata source)
    # =========================================================================

    def test_pg_openai_all_tools_have_scopes(self):
        """
        PG-OpenAI: Every tool in TOOL_REGISTRY must have non-empty required_scopes.

        Bug this catches: registering a new tool without specifying scopes,
        creating a scope-bypass path.

        Also covers PG-Claude: tools_dupl.py imports get_tool from
        mcp_server.priority_guardian.tools — same registry, same coverage.
        """
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY

        tools_without_scopes = []
        for name, tool_def in TOOL_REGISTRY.items():
            if not tool_def.required_scopes:
                tools_without_scopes.append(name)

        assert not tools_without_scopes, (
            f"PG-OpenAI tools registered without required_scopes (cross-app isolation gap): "
            f"{tools_without_scopes}"
        )

    def test_mindsort_openai_all_tools_have_scopes(self):
        """
        MindSort-OpenAI: Every tool in TOOL_REGISTRY must have non-empty required_scopes.

        Bug this catches: registering a new tool without specifying scopes,
        creating a scope-bypass path.

        NOTE: This tests the METADATA source (registry). The ENFORCEMENT source
        is config.TOOL_SCOPES — see test_mindsort_openai_tool_scopes_dict_non_empty.
        """
        from mcp_server.clarity.tools import TOOL_REGISTRY

        tools_without_scopes = []
        for name, tool_def in TOOL_REGISTRY.items():
            if not tool_def.required_scopes:
                tools_without_scopes.append(name)

        assert not tools_without_scopes, (
            f"MindSort-OpenAI tools registered without required_scopes (cross-app isolation gap): "
            f"{tools_without_scopes}"
        )

    # =========================================================================
    # Dict-based tests (enforcement source)
    # =========================================================================

    def test_mindsort_openai_tool_scopes_dict_non_empty(self):
        """
        MindSort-OpenAI: Every entry in config.TOOL_SCOPES must have non-empty scope list.

        Bug this catches: TOOL_SCOPES = {"tool": []} passes `all([]) == True`
        in scope enforcement, creating an implicit fail-open where any valid
        token can call the tool regardless of its scopes.

        This is the ENFORCEMENT source — mcp_auth.enforce_tool_scope reads from
        TOOL_SCOPES, not from TOOL_REGISTRY.required_scopes.
        """
        from mcp_server.clarity.config import TOOL_SCOPES

        empty_scope_tools = [
            name for name, scopes in TOOL_SCOPES.items()
            if not scopes
        ]

        assert not empty_scope_tools, (
            f"MindSort-OpenAI TOOL_SCOPES has tools with empty scope lists "
            f"(implicit fail-open via all([]) == True): {empty_scope_tools}"
        )

    def test_mindsort_claude_tool_scopes_dict_non_empty(self):
        """
        MindSort-Claude: Every entry in config.TOOL_SCOPES must have non-empty scope list.

        Bug this catches: TOOL_SCOPES = {"tool": []} passes `all([]) == True`
        in scope enforcement, creating an implicit fail-open.

        This is the submission app — scope enforcement is the only cross-app
        isolation mechanism.
        """
        from mcp_server.mindsort_claude.config import TOOL_SCOPES

        empty_scope_tools = [
            name for name, scopes in TOOL_SCOPES.items()
            if not scopes
        ]

        assert not empty_scope_tools, (
            f"MindSort-Claude TOOL_SCOPES has tools with empty scope lists "
            f"(implicit fail-open via all([]) == True): {empty_scope_tools}"
        )

    # =========================================================================
    # Drift-catcher tests (registry ↔ dict synchronization)
    # =========================================================================

    def test_mindsort_openai_registry_keys_in_tool_scopes(self):
        """
        MindSort-OpenAI: Every TOOL_REGISTRY key must have an entry in TOOL_SCOPES.

        Bug this catches: adding a tool to the registry but forgetting to add
        it to TOOL_SCOPES → tool appears in tools/list but enforce_tool_scope
        raises InsufficientScopeError("<tool not registered>") — fail-closed but
        with a confusing scope error instead of a clear "unknown tool" message.
        """
        from mcp_server.clarity.tools import TOOL_REGISTRY
        from mcp_server.clarity.config import TOOL_SCOPES

        missing_from_dict = [
            name for name in TOOL_REGISTRY.keys()
            if name not in TOOL_SCOPES
        ]

        assert not missing_from_dict, (
            f"MindSort-OpenAI tools in TOOL_REGISTRY but missing from TOOL_SCOPES "
            f"(fail-closed with confusing scope error at dispatch): {missing_from_dict}"
        )

    def test_mindsort_claude_registry_keys_in_tool_scopes(self):
        """
        MindSort-Claude: Every TOOL_REGISTRY key must have an entry in TOOL_SCOPES.

        Bug this catches: same as MindSort-OpenAI — tool-added-dict-forgotten
        causes fail-closed dispatch with confusing scope error.

        Valid because tools_list_dupl iterates the clarity registry unfiltered:
        mcp_server/mindsort_claude/tools_list_dupl.py imports TOOL_REGISTRY
        from mcp_server.clarity.tools.
        """
        from mcp_server.clarity.tools import TOOL_REGISTRY
        from mcp_server.mindsort_claude.config import TOOL_SCOPES

        missing_from_dict = [
            name for name in TOOL_REGISTRY.keys()
            if name not in TOOL_SCOPES
        ]

        assert not missing_from_dict, (
            f"MindSort-Claude tools in TOOL_REGISTRY but missing from TOOL_SCOPES "
            f"(fail-closed with confusing scope error at dispatch): {missing_from_dict}"
        )

    # =========================================================================
    # Cross-platform parity test
    # =========================================================================

    def test_mindsort_openai_claude_tool_scopes_parity(self):
        """
        MindSort-OpenAI and MindSort-Claude TOOL_SCOPES dicts must be identical.

        Bug this catches: divergence between the two platforms' scope definitions.
        If they differ, one platform accepts a tool call the other rejects, or
        vice versa — confusing behavior for users and a potential security gap.

        This makes divergence a conscious, test-failing decision rather than
        accidental drift.
        """
        from mcp_server.clarity.config import TOOL_SCOPES as OPENAI_SCOPES
        from mcp_server.mindsort_claude.config import TOOL_SCOPES as CLAUDE_SCOPES

        assert OPENAI_SCOPES == CLAUDE_SCOPES, (
            f"MindSort TOOL_SCOPES divergence between OpenAI and Claude:\n"
            f"OpenAI-only keys: {set(OPENAI_SCOPES.keys()) - set(CLAUDE_SCOPES.keys())}\n"
            f"Claude-only keys: {set(CLAUDE_SCOPES.keys()) - set(OPENAI_SCOPES.keys())}\n"
            f"Value differences: {[(k, OPENAI_SCOPES.get(k), CLAUDE_SCOPES.get(k)) for k in OPENAI_SCOPES if OPENAI_SCOPES.get(k) != CLAUDE_SCOPES.get(k)]}"
        )

    # =========================================================================
    # Metadata/enforcement parity test
    # =========================================================================

    def test_mindsort_openai_registry_matches_tool_scopes(self):
        """
        MindSort-OpenAI: TOOL_REGISTRY.required_scopes must equal TOOL_SCOPES per tool.

        Bug this catches: registry and dict divergence. The registry field feeds
        widget securitySchemes metadata (advertised scopes), while TOOL_SCOPES
        is the enforcement source. Mismatch means advertised ≠ enforced:
        - Registry has broader scopes → widget shows unnecessary permissions
        - Registry has narrower scopes → widget claims safety it doesn't have

        Both are user trust violations.
        """
        from mcp_server.clarity.tools import TOOL_REGISTRY
        from mcp_server.clarity.config import TOOL_SCOPES

        mismatches = []
        for name, tool_def in TOOL_REGISTRY.items():
            registry_scopes = set(tool_def.required_scopes) if tool_def.required_scopes else set()
            dict_scopes = set(TOOL_SCOPES.get(name, []))

            if registry_scopes != dict_scopes:
                mismatches.append(
                    f"{name}: registry={sorted(registry_scopes)}, dict={sorted(dict_scopes)}"
                )

        assert not mismatches, (
            f"MindSort-OpenAI TOOL_REGISTRY.required_scopes ≠ TOOL_SCOPES (advertised ≠ enforced):\n"
            + "\n".join(mismatches)
        )
