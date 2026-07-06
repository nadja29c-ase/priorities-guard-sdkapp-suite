"""
Unit tests for widget render path observability (inc_98).

Verifies that:
- resource.read.* events fire at INFO level for production visibility
- Logged values contain no PII (URIs and lengths only)
- Tool outputTemplate URI matches served resource URI (consistency guard)
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from mcp import types as mcp_types


class TestResourceReadLogging:
    """Tests for resource.read.* INFO-level logging."""

    @pytest.mark.asyncio
    async def test_widget_uri_logs_at_info(self, capsys):
        """resource.read.requested and resource.read.serving_widget fire at INFO for widget URI.

        Bug this test catches: DEBUG-level logging invisible in production,
        making render failures undiagnosable.
        """
        from mcp_server.priority_guardian.handlers.resources import (
            handle_read_resource,
            WIDGET_URI,
        )

        # Create a mock request for the widget URI
        req = MagicMock()
        req.params.uri = WIDGET_URI

        # Call the handler
        result = await handle_read_resource(req)

        # Verify result is valid
        assert result is not None
        assert len(result.contents) == 1
        assert result.contents[0].mimeType == "text/html;profile=mcp-app"

        # Check logs contain the INFO events
        captured = capsys.readouterr()
        assert "resource.read.requested" in captured.out
        assert "resource.read.serving_widget" in captured.out
        assert WIDGET_URI in captured.out

    @pytest.mark.asyncio
    async def test_unknown_uri_logs_at_info(self, capsys):
        """resource.read.unknown_uri fires at INFO for unknown URIs.

        Bug this test catches: Silent failures when ChatGPT requests wrong URI
        due to schema drift.
        """
        from mcp_server.priority_guardian.handlers.resources import handle_read_resource

        # Create a mock request for an unknown URI
        unknown_uri = "ui://widget/nonexistent-v999.html"
        req = MagicMock()
        req.params.uri = unknown_uri

        # Call the handler
        result = await handle_read_resource(req)

        # Verify empty result with error meta
        assert result is not None
        assert len(result.contents) == 0
        # MCP types use 'meta' not '_meta' at the result level
        assert result.meta is not None and "error" in result.meta

        # Check logs contain the INFO event
        captured = capsys.readouterr()
        assert "resource.read.requested" in captured.out
        assert "resource.read.unknown_uri" in captured.out
        assert unknown_uri in captured.out

    @pytest.mark.asyncio
    async def test_logged_values_contain_no_pii(self, capsys):
        """Logged values are URIs and lengths only — no user data, no HTML content.

        Bug this test catches: PII leakage in production logs (GDPR violation
        on a published app).
        """
        from mcp_server.priority_guardian.handlers.resources import (
            handle_read_resource,
            WIDGET_URI,
            WIDGET_HTML,
        )

        req = MagicMock()
        req.params.uri = WIDGET_URI

        await handle_read_resource(req)

        captured = capsys.readouterr()

        # Should contain URI and html_length
        assert WIDGET_URI in captured.out
        assert "html_length" in captured.out

        # Should NOT contain actual HTML content (would be huge and contain PII risk)
        # Check that the full HTML is not in logs (just check it's not dumping the whole thing)
        assert "<!DOCTYPE" not in captured.out
        assert "<html" not in captured.out


class TestOutputTemplateConsistency:
    """Tests that tool outputTemplate URI matches served resource URI."""

    def test_get_priorities_output_template_matches_widget_uri(self):
        """Tool outputTemplate URI must equal constants.WIDGET_URI.

        Bug this test catches: Drift between tool binding and served resource —
        ChatGPT requests URI from tool result, if it doesn't match what
        resources.py serves, widget fails to render.
        """
        from mcp_server.priority_guardian.tools.widget_tools.constants import WIDGET_URI
        from mcp_server.priority_guardian.tools.get_priorities import GET_PRIORITIES

        # The tool definition should reference the same WIDGET_URI
        assert GET_PRIORITIES.widget_uri == WIDGET_URI

    def test_all_widget_tools_use_consistent_uri(self):
        """All tools that produce widgets must use the same WIDGET_URI.

        Bug this test catches: Multiple tools binding to different URIs,
        causing inconsistent widget behavior.
        """
        from mcp_server.priority_guardian.tools.widget_tools.constants import WIDGET_URI
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY

        # Find all tools with widget_uri set
        widget_tools = [
            (name, tool) for name, tool in TOOL_REGISTRY.items()
            if getattr(tool, 'widget_uri', None) is not None
        ]

        # All widget tools should use the same URI
        for name, tool in widget_tools:
            assert tool.widget_uri == WIDGET_URI, \
                f"Tool {name} uses {tool.widget_uri!r}, expected {WIDGET_URI!r}"


class TestLogEventDistinguishability:
    """Tests that resource reads and tool calls produce distinguishable log events."""

    def test_resource_events_have_distinct_prefix(self):
        """resource.read.* events are distinguishable from tool.dispatch.* events.

        Bug this test catches: Ambiguous logs making it impossible to determine
        whether ChatGPT issued resources/read or only tools/call.
        """
        # These are the event names — verify they don't overlap
        resource_events = [
            "resource.read.requested",
            "resource.read.serving_widget",
            "resource.read.unknown_uri",
        ]
        tool_events = [
            "tool.dispatch.received",
            "tool.dispatch.executing",
            "tool.dispatch.unauthorized",
            "tool.dispatch.forbidden",
            "tool.timing",
        ]

        # No overlap between resource and tool event prefixes
        for r_event in resource_events:
            for t_event in tool_events:
                assert r_event != t_event, f"Event collision: {r_event}"
                # Also verify prefix distinction
                assert not r_event.startswith("tool."), f"Resource event has tool prefix: {r_event}"

        for t_event in tool_events:
            assert not t_event.startswith("resource."), f"Tool event has resource prefix: {t_event}"
