"""
Unit tests for inc_91 diagnostic increment.

Tests:
1. MCP request-type logging emits correct distinct events
2. Diagnostic widget tool output is structurally identical to organize_thoughts
3. Widget resource serving for both main and diagnostic widgets
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from mcp import types as mcp_types


# ============================================================================
# Test MCP Request-Type Logging
# ============================================================================


class TestMCPRequestTypeLogging:
    """
    Tests that MCP request-type logging emits correct distinct events.

    Per inc_91: "Log tools/list, tools/call, resources/list, resources/read,
    resources/templates/list as distinct structured events carrying the JSON-RPC
    method name."
    """

    @pytest.mark.asyncio
    async def test_resources_list_logging(self):
        """resources/list logs mcp.request.resources_list event."""
        from mcp_server.clarity.handlers.resources import list_resources

        with patch("mcp_server.clarity.handlers.resources.logger") as mock_logger:
            result = await list_resources()

            # Verify event name and fields
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert call_args[0][0] == "mcp.request.resources_list"
            assert "resource_count" in call_args[1]

    @pytest.mark.asyncio
    async def test_resources_templates_list_logging(self):
        """resources/templates/list logs mcp.request.resources_templates_list event."""
        from mcp_server.clarity.handlers.resources import list_resource_templates

        with patch("mcp_server.clarity.handlers.resources.logger") as mock_logger:
            result = await list_resource_templates()

            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            assert call_args[0][0] == "mcp.request.resources_templates_list"
            assert "template_count" in call_args[1]

    @pytest.mark.asyncio
    async def test_resources_read_logging(self):
        """resources/read logs mcp.request.resources_read event."""
        from mcp_server.clarity.handlers.resources import (
            handle_read_resource,
            WIDGET_URI,
        )

        # Build mock request
        params = MagicMock()
        params.uri = WIDGET_URI
        req = MagicMock()
        req.params = params

        with patch("mcp_server.clarity.handlers.resources.logger") as mock_logger:
            result = await handle_read_resource(req)

            # Should log both request received and serving
            assert mock_logger.info.call_count >= 1
            first_call = mock_logger.info.call_args_list[0]
            assert first_call[0][0] == "mcp.request.resources_read"
            assert "uri" in first_call[1]

    @pytest.mark.asyncio
    async def test_tools_call_logging(self):
        """tools/call logs mcp.request.tools_call event."""
        from mcp_server.clarity.handlers.tools import call_tool_request

        # Build mock request for unknown tool (fastest path to test logging)
        params = MagicMock()
        params.name = "nonexistent_tool"
        params.arguments = {}
        params._meta = {}
        req = MagicMock()
        req.params = params

        with patch("mcp_server.clarity.handlers.tools.logger") as mock_logger:
            result = await call_tool_request(req)

            # Check that mcp.request.tools_call was logged
            info_calls = [c for c in mock_logger.info.call_args_list
                         if c[0][0] == "mcp.request.tools_call"]
            assert len(info_calls) == 1
            assert info_calls[0][1]["tool_name"] == "nonexistent_tool"


# ============================================================================
# Test Diagnostic Widget Tool Structure
# ============================================================================


class TestDiagnosticWidgetToolStructure:
    """
    Tests that diagnostic widget tool output is structurally identical to
    organize_thoughts, differing only in resource URI/size.

    Per inc_91: "Structural clone of the real tool's output — identical _meta
    shape/placement, identical outputTemplate mechanism, identical MIME."
    """

    @pytest.mark.asyncio
    async def test_diagnostic_tool_meta_structure_matches_organize_thoughts(self):
        """Diagnostic tool _meta must have EXACT same keys as organize_thoughts.

        Bug fix: Previous version used a hardcoded key list and never called
        organize_thoughts, so it wouldn't catch organize_thoughts gaining an
        extra _meta key that diagnostic lacks.
        """
        from mcp_server.clarity.tools.diagnostic_widget import handle as diag_handle
        from mcp_server.clarity.tools.organize_thoughts import handle as org_handle
        from mcp_server.clarity.handlers.resources import WIDGET_URI
        from mcp_server.clarity.tools.diagnostic_widget import DIAGNOSTIC_WIDGET_URI

        # Call diagnostic tool (side-effect-free, no mocking needed)
        diag_result = await diag_handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={"test_id": "unit-test"},
        )

        # Call organize_thoughts with valid arguments to get its actual _meta
        # Must mock persist_cluster since it's auto-persist
        with patch("mcp_server.clarity.tools.organize_thoughts.persist_cluster") as mock_persist:
            mock_persist.return_value = "mock-cluster-id"

            org_result = await org_handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={
                    "user_thoughts_exhausted_verbatim": "that's everything",
                    "user_confirmed_no_more_thoughts": True,
                    "thoughts_exhausted": True,
                    "clusters": [
                        {"cluster_name": "Test", "thought_items": ["item1", "item2"]}
                    ],
                },
            )

        # Both should succeed
        assert org_result.isError is not True, "organize_thoughts failed"
        assert diag_result.isError is not True, "diagnostic failed"

        # Get actual _meta from both tools
        diag_meta = diag_result.meta
        org_meta = org_result.meta

        # CRITICAL: Compare key sets - diagnostic must have ALL keys organize_thoughts has
        diag_keys = set(diag_meta.keys())
        org_keys = set(org_meta.keys())

        missing_in_diagnostic = org_keys - diag_keys
        extra_in_diagnostic = diag_keys - org_keys

        assert not missing_in_diagnostic, (
            f"Diagnostic _meta missing keys from organize_thoughts: {missing_in_diagnostic}. "
            f"This breaks the structural clone requirement."
        )
        assert not extra_in_diagnostic, (
            f"Diagnostic _meta has extra keys not in organize_thoughts: {extra_in_diagnostic}. "
            f"This may confound the experiment."
        )

        # Verify nested ui structure matches
        assert set(diag_meta["ui"].keys()) == set(org_meta["ui"].keys()), (
            f"ui structure mismatch: diagnostic={diag_meta['ui'].keys()}, "
            f"organize_thoughts={org_meta['ui'].keys()}"
        )

        # Verify outputTemplate points to diagnostic widget, not main widget
        assert diag_meta["openai/outputTemplate"] == DIAGNOSTIC_WIDGET_URI
        assert diag_meta["openai/outputTemplate"] != WIDGET_URI

    @pytest.mark.asyncio
    async def test_diagnostic_tool_returns_callttoolresult(self):
        """Diagnostic tool must return CallToolResult type."""
        from mcp_server.clarity.tools.diagnostic_widget import handle

        result = await handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={},
        )

        assert isinstance(result, mcp_types.CallToolResult)
        assert result.isError is not True
        assert result.structuredContent is not None

    @pytest.mark.asyncio
    async def test_diagnostic_tool_is_side_effect_free(self):
        """Diagnostic tool must not call persistence or external services."""
        from mcp_server.clarity.tools.diagnostic_widget import handle

        with patch("mcp_server.clarity.persistence.persist_cluster") as mock_persist:
            result = await handle(
                user_id="test-user",
                correlation_id="test-corr",
                arguments={"test_id": "side-effect-test"},
            )

            # persist_cluster should NOT be called
            mock_persist.assert_not_called()

        assert result.isError is not True


class TestDiagnosticToolRegistration:
    """Tests that diagnostic tool is properly registered with correct hints."""

    def test_diagnostic_tool_registered_with_readonly_hint(self):
        """Diagnostic tool must have read_only_hint=True."""
        from mcp_server.clarity.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY.get("_diagnostic_tiny_widget")
        assert tool is not None, "Diagnostic tool not registered"
        assert tool.read_only_hint is True, "Diagnostic tool must be read-only"

    def test_diagnostic_tool_has_no_required_scopes(self):
        """Diagnostic tool should not require scopes (internal tool)."""
        from mcp_server.clarity.tools import TOOL_REGISTRY

        tool = TOOL_REGISTRY.get("_diagnostic_tiny_widget")
        assert tool is not None
        # Empty list or None both acceptable
        assert not tool.required_scopes or len(tool.required_scopes) == 0


# ============================================================================
# Test Diagnostic Widget Resource Serving
# ============================================================================


class TestDiagnosticWidgetResourceServing:
    """Tests that diagnostic widget is properly served via resources/read."""

    @pytest.mark.asyncio
    async def test_diagnostic_widget_served_with_correct_mime(self):
        """Diagnostic widget must be served with text/html;profile=mcp-app."""
        from mcp_server.clarity.handlers.resources import (
            handle_read_resource,
            DIAGNOSTIC_WIDGET_URI,
        )

        params = MagicMock()
        params.uri = DIAGNOSTIC_WIDGET_URI
        req = MagicMock()
        req.params = params

        result = await handle_read_resource(req)

        assert len(result.contents) == 1
        content = result.contents[0]
        assert content.mimeType == "text/html;profile=mcp-app"

    @pytest.mark.asyncio
    async def test_diagnostic_widget_html_is_small(self):
        """Diagnostic widget must be under 10KB (size isolation test)."""
        from mcp_server.clarity.handlers.resources import (
            handle_read_resource,
            DIAGNOSTIC_WIDGET_URI,
            DIAGNOSTIC_WIDGET_HTML,
        )

        # Check raw HTML size
        html_size = len(DIAGNOSTIC_WIDGET_HTML.encode("utf-8"))
        assert html_size < 10 * 1024, f"Diagnostic widget is {html_size} bytes, must be <10KB"

    @pytest.mark.asyncio
    async def test_diagnostic_widget_has_ui_domain_meta(self):
        """Diagnostic widget resource must have ui.domain in _meta."""
        from mcp_server.clarity.handlers.resources import (
            handle_read_resource,
            DIAGNOSTIC_WIDGET_URI,
        )

        params = MagicMock()
        params.uri = DIAGNOSTIC_WIDGET_URI
        req = MagicMock()
        req.params = params

        result = await handle_read_resource(req)

        content = result.contents[0]
        # Note: MCP SDK exposes _meta as .meta attribute
        assert content.meta is not None
        assert "ui" in content.meta
        assert "domain" in content.meta["ui"]

    @pytest.mark.asyncio
    async def test_main_widget_still_served(self):
        """Main widget serving must not be broken by diagnostic changes."""
        from mcp_server.clarity.handlers.resources import (
            handle_read_resource,
            WIDGET_URI,
            WIDGET_HTML,
        )

        params = MagicMock()
        params.uri = WIDGET_URI
        req = MagicMock()
        req.params = params

        result = await handle_read_resource(req)

        assert len(result.contents) == 1
        content = result.contents[0]
        assert content.mimeType == "text/html;profile=mcp-app"
        assert content.text == WIDGET_HTML


# ============================================================================
# Test URI Consistency
# ============================================================================


class TestURIConsistency:
    """Tests that URIs are consistent between tool and resource handler."""

    def test_diagnostic_uri_matches_between_tool_and_resources(self):
        """Diagnostic widget URI must match between tool and resources module."""
        from mcp_server.clarity.tools.diagnostic_widget import DIAGNOSTIC_WIDGET_URI as TOOL_URI
        from mcp_server.clarity.handlers.resources import DIAGNOSTIC_WIDGET_URI as RESOURCE_URI

        assert TOOL_URI == RESOURCE_URI, (
            f"URI mismatch: tool={TOOL_URI}, resources={RESOURCE_URI}"
        )

    def test_diagnostic_widget_file_exists(self):
        """Diagnostic widget HTML file must exist."""
        from mcp_server.clarity.handlers.resources import DIAGNOSTIC_WIDGET_PATH

        assert DIAGNOSTIC_WIDGET_PATH.exists(), (
            f"Diagnostic widget file not found: {DIAGNOSTIC_WIDGET_PATH}"
        )


class TestDiagnosticWidgetDiscovery:
    """Tests that diagnostic widget is discoverable via list_resources."""

    @pytest.mark.asyncio
    async def test_diagnostic_widget_in_list_resources(self):
        """Diagnostic widget must appear in list_resources for ChatGPT to fetch it.

        Bug fix: Without this, ChatGPT may never call resources/read for the
        diagnostic widget, producing a false 'A/host-side' verdict.
        """
        from mcp_server.clarity.handlers.resources import (
            list_resources,
            DIAGNOSTIC_WIDGET_URI,
        )

        resources = await list_resources()
        resource_uris = [str(r.uri) for r in resources]

        assert DIAGNOSTIC_WIDGET_URI in resource_uris, (
            f"Diagnostic widget URI {DIAGNOSTIC_WIDGET_URI} not in list_resources. "
            f"Found: {resource_uris}"
        )

    @pytest.mark.asyncio
    async def test_diagnostic_widget_in_list_resource_templates(self):
        """Diagnostic widget must appear in list_resource_templates."""
        from mcp_server.clarity.handlers.resources import (
            list_resource_templates,
            DIAGNOSTIC_WIDGET_URI,
        )

        templates = await list_resource_templates()
        template_uris = [str(t.uriTemplate) for t in templates]

        assert DIAGNOSTIC_WIDGET_URI in template_uris, (
            f"Diagnostic widget URI {DIAGNOSTIC_WIDGET_URI} not in list_resource_templates. "
            f"Found: {template_uris}"
        )


class TestCSPMatching:
    """Tests that diagnostic widget matches real widget's CSP behavior."""

    def test_diagnostic_widget_has_external_cdn_reference(self):
        """Diagnostic widget must reference external CDN to match real widget's CSP behavior.

        Bug fix: Without an external asset reference, the diagnostic could render
        while the real widget fails due to CSP blocking external assets - producing
        an ambiguous 'C/size' verdict when the real cause is CSP.
        """
        from mcp_server.clarity.handlers.resources import DIAGNOSTIC_WIDGET_HTML

        # Must reference cdn.openai.com (same as real widget's KaTeX fonts)
        assert "cdn.openai.com" in DIAGNOSTIC_WIDGET_HTML, (
            "Diagnostic widget must reference cdn.openai.com to match real widget's "
            "CSP behavior. This isolates SIZE as the only variable."
        )
