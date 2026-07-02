"""
Tool scope invariant tests.

Ensures all registered tools have non-empty required_scopes.

Background: audience is shared suite-wide (aud=www for tokens minted without
resource param), so scope enforcement is the only cross-app isolation mechanism.
A tool registered with empty required_scopes becomes callable by any valid token
from any app in the suite — a MindSort clarity.write token could invoke it.

This test catches such misregistrations at CI time rather than in production.
"""

import pytest


class TestToolScopeInvariants:
    """Ensure all tools have non-empty required_scopes for cross-app isolation."""

    def test_pg_openai_all_tools_have_scopes(self):
        """
        PG-OpenAI: Every tool in TOOL_REGISTRY must have non-empty required_scopes.

        Bug this catches: registering a new tool without specifying scopes,
        creating a scope-bypass path.
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
