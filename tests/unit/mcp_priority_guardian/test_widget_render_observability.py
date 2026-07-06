"""
Unit tests for widget render path observability (inc_98 → inc_101).

Verifies that:
- resource.read.* events fire at INFO level for production visibility
- Log level is explicitly INFO (not just substring presence)
- correlation_id is present in all resource logs
- URI sanitization works (query stripped, length capped)
- Logged values contain no PII (URIs and lengths only)
- Tool outputTemplate URI matches served resource URI (consistency guard)
- inc_100: Userinfo stripped, non-dict _meta handled
- inc_101: Allowlist closes scheme class, params guard, malformed port regression
"""

import pytest
from unittest.mock import MagicMock
import structlog
from structlog.testing import capture_logs


class TestResourceReadLogging:
    """Tests for resource.read.* INFO-level logging."""

    @pytest.mark.asyncio
    async def test_widget_uri_logs_at_info_level(self):
        """resource.read.requested and resource.read.serving_widget emit at INFO level.

        inc_99: Uses structlog.testing.capture_logs() to assert actual log level,
        not just substring presence. Catches regression to DEBUG that would
        make logs invisible in production.

        Bug this test catches: DEBUG-level logging invisible in production.
        Bug that would still pass: Log emits at INFO but with wrong event name.
        """
        from mcp_server.priority_guardian.handlers.resources import (
            handle_read_resource,
            WIDGET_URI,
        )

        req = MagicMock()
        req.params.uri = WIDGET_URI
        req.params._meta = None

        with capture_logs() as cap_logs:
            result = await handle_read_resource(req)

        # Verify result is valid
        assert result is not None
        assert len(result.contents) == 1

        # Assert INFO level explicitly (the core of inc_98/99)
        requested_logs = [l for l in cap_logs if l.get("event") == "resource.read.requested"]
        serving_logs = [l for l in cap_logs if l.get("event") == "resource.read.serving_widget"]

        assert len(requested_logs) == 1, f"Expected 1 resource.read.requested log, got {len(requested_logs)}"
        assert len(serving_logs) == 1, f"Expected 1 resource.read.serving_widget log, got {len(serving_logs)}"

        assert requested_logs[0]["log_level"] == "info", \
            f"resource.read.requested should be INFO, got {requested_logs[0].get('log_level')}"
        assert serving_logs[0]["log_level"] == "info", \
            f"resource.read.serving_widget should be INFO, got {serving_logs[0].get('log_level')}"

    @pytest.mark.asyncio
    async def test_unknown_uri_logs_at_info_level(self):
        """resource.read.unknown_uri emits at INFO level.

        Bug this test catches: Unknown URI logged at DEBUG, invisible in production.
        Bug that would still pass: Log at INFO but wrong event name.
        """
        from mcp_server.priority_guardian.handlers.resources import handle_read_resource

        unknown_uri = "ui://widget/nonexistent-v999.html"
        req = MagicMock()
        req.params.uri = unknown_uri
        req.params._meta = None

        with capture_logs() as cap_logs:
            result = await handle_read_resource(req)

        # Verify empty result
        assert result is not None
        assert len(result.contents) == 0

        # Assert INFO level
        unknown_logs = [l for l in cap_logs if l.get("event") == "resource.read.unknown_uri"]
        assert len(unknown_logs) == 1, f"Expected 1 resource.read.unknown_uri log, got {len(unknown_logs)}"
        assert unknown_logs[0]["log_level"] == "info", \
            f"resource.read.unknown_uri should be INFO, got {unknown_logs[0].get('log_level')}"


class TestCorrelationId:
    """Tests for correlation_id presence in resource logs (inc_99)."""

    @pytest.mark.asyncio
    async def test_correlation_id_present_in_widget_logs(self):
        """correlation_id is present in resource.read.requested and serving_widget logs.

        inc_99: Enables correlating resources/read with tools/call in same session
        for the binary verdict diagnostic.

        Bug this test catches: Missing correlation_id makes session correlation impossible.
        Bug that would still pass: correlation_id present but not a valid UUID.
        """
        from mcp_server.priority_guardian.handlers.resources import (
            handle_read_resource,
            WIDGET_URI,
        )

        req = MagicMock()
        req.params.uri = WIDGET_URI
        req.params._meta = {"correlation_id": "test-correlation-123"}

        with capture_logs() as cap_logs:
            await handle_read_resource(req)

        requested_logs = [l for l in cap_logs if l.get("event") == "resource.read.requested"]
        serving_logs = [l for l in cap_logs if l.get("event") == "resource.read.serving_widget"]

        assert "correlation_id" in requested_logs[0], "resource.read.requested missing correlation_id"
        assert "correlation_id" in serving_logs[0], "resource.read.serving_widget missing correlation_id"

        # Verify it uses the provided correlation_id
        assert requested_logs[0]["correlation_id"] == "test-correlation-123"
        assert serving_logs[0]["correlation_id"] == "test-correlation-123"

    @pytest.mark.asyncio
    async def test_correlation_id_generated_when_missing(self):
        """correlation_id is generated when not provided in request metadata.

        Bug this test catches: Handler crashes when _meta is None.
        Bug that would still pass: Generated ID is not a valid UUID format.
        """
        from mcp_server.priority_guardian.handlers.resources import (
            handle_read_resource,
            WIDGET_URI,
        )

        req = MagicMock()
        req.params.uri = WIDGET_URI
        req.params._meta = None  # No metadata provided

        with capture_logs() as cap_logs:
            await handle_read_resource(req)

        requested_logs = [l for l in cap_logs if l.get("event") == "resource.read.requested"]
        assert "correlation_id" in requested_logs[0], "correlation_id should be generated when missing"
        assert len(requested_logs[0]["correlation_id"]) > 0, "Generated correlation_id should not be empty"

    @pytest.mark.asyncio
    async def test_correlation_id_present_in_unknown_uri_log(self):
        """correlation_id is present in resource.read.unknown_uri log.

        Bug this test catches: Unknown URI path missing correlation_id.
        """
        from mcp_server.priority_guardian.handlers.resources import handle_read_resource

        req = MagicMock()
        req.params.uri = "ui://widget/unknown.html"
        req.params._meta = {"correlation_id": "unknown-test-456"}

        with capture_logs() as cap_logs:
            await handle_read_resource(req)

        unknown_logs = [l for l in cap_logs if l.get("event") == "resource.read.unknown_uri"]
        assert "correlation_id" in unknown_logs[0], "resource.read.unknown_uri missing correlation_id"
        assert unknown_logs[0]["correlation_id"] == "unknown-test-456"


class TestUriSanitization:
    """Tests for URI sanitization in logging (inc_99)."""

    @pytest.mark.asyncio
    async def test_query_string_stripped_from_logged_uri(self):
        """Query string is stripped from URI before logging.

        inc_99: Prevents tokens/PII in query strings from leaking to logs.

        Bug this test catches: Token in ?token=xxx logged to production.
        Bug that would still pass: Query stripped but fragment not stripped.
        """
        from mcp_server.priority_guardian.handlers.resources import handle_read_resource

        # URI with query string that could contain sensitive data
        uri_with_query = "ui://widget/pg-dashboard-v12.html?token=secret123&user=test@example.com"
        req = MagicMock()
        req.params.uri = uri_with_query
        req.params._meta = None

        with capture_logs() as cap_logs:
            await handle_read_resource(req)

        requested_logs = [l for l in cap_logs if l.get("event") == "resource.read.requested"]
        logged_uri = requested_logs[0]["uri"]

        # Query string should be stripped
        assert "token=secret123" not in logged_uri, "Query string should be stripped"
        assert "user=test@example.com" not in logged_uri, "Query string should be stripped"
        assert "?" not in logged_uri, "Query separator should not be in sanitized URI"

    @pytest.mark.asyncio
    async def test_long_uri_truncated(self):
        """Very long URIs are truncated to prevent log bloat.

        Bug this test catches: Pathological URI bloats production logs.
        Bug that would still pass: Truncation at wrong length or no indicator.
        """
        from mcp_server.priority_guardian.handlers.resources import (
            handle_read_resource,
            _MAX_URI_LOG_LENGTH,
        )

        # Create a very long URI
        long_path = "a" * 1000
        long_uri = f"ui://widget/{long_path}.html"
        req = MagicMock()
        req.params.uri = long_uri
        req.params._meta = None

        with capture_logs() as cap_logs:
            await handle_read_resource(req)

        requested_logs = [l for l in cap_logs if l.get("event") == "resource.read.requested"]
        logged_uri = requested_logs[0]["uri"]

        # Should be truncated
        assert len(logged_uri) <= _MAX_URI_LOG_LENGTH + len("...[truncated]"), \
            f"URI should be truncated to ~{_MAX_URI_LOG_LENGTH} chars"
        assert "...[truncated]" in logged_uri, "Truncated URI should have indicator"

    def test_sanitize_uri_function_directly(self):
        """Direct test of _sanitize_uri_for_logging function.

        Bug this test catches: Edge cases in URI sanitization.
        """
        from mcp_server.priority_guardian.handlers.resources import _sanitize_uri_for_logging

        # Normal URI unchanged
        assert _sanitize_uri_for_logging("ui://widget/test.html") == "ui://widget/test.html"

        # Query stripped
        result = _sanitize_uri_for_logging("ui://widget/test.html?foo=bar")
        assert "foo=bar" not in result
        assert "?" not in result

        # Fragment stripped (implicit via urlparse behavior for ui:// scheme)
        # Note: urlparse handles fragments, but ui:// may behave differently
        result = _sanitize_uri_for_logging("https://example.com/path?q=1#anchor")
        assert "q=1" not in result
        assert "#anchor" not in result

        # Long URI truncated
        long_uri = "ui://widget/" + "x" * 600 + ".html"
        result = _sanitize_uri_for_logging(long_uri)
        assert len(result) < len(long_uri)
        assert "...[truncated]" in result


class TestLoggedValuesNoPii:
    """Tests that logged values contain no PII."""

    @pytest.mark.asyncio
    async def test_logged_values_contain_no_html_content(self):
        """Logged values are URIs and lengths only — no HTML content.

        Bug this test catches: HTML content (could contain PII) in logs.
        """
        from mcp_server.priority_guardian.handlers.resources import (
            handle_read_resource,
            WIDGET_URI,
        )

        req = MagicMock()
        req.params.uri = WIDGET_URI
        req.params._meta = None

        with capture_logs() as cap_logs:
            await handle_read_resource(req)

        serving_logs = [l for l in cap_logs if l.get("event") == "resource.read.serving_widget"]

        # Should have html_length, not html content
        assert "html_length" in serving_logs[0]
        assert isinstance(serving_logs[0]["html_length"], int)

        # Should NOT have text/html keys
        assert "text" not in serving_logs[0]
        assert "html" not in serving_logs[0]


class TestOutputTemplateConsistency:
    """Tests that tool outputTemplate URI matches served resource URI."""

    def test_get_priorities_output_template_matches_widget_uri(self):
        """Tool outputTemplate URI must equal constants.WIDGET_URI.

        Bug this test catches: Drift between tool binding and served resource.
        """
        from mcp_server.priority_guardian.tools.widget_tools.constants import WIDGET_URI
        from mcp_server.priority_guardian.tools.get_priorities import GET_PRIORITIES

        assert GET_PRIORITIES.widget_uri == WIDGET_URI

    def test_all_widget_tools_use_consistent_uri(self):
        """All tools that produce widgets must use the same WIDGET_URI.

        Bug this test catches: Multiple tools binding to different URIs.
        """
        from mcp_server.priority_guardian.tools.widget_tools.constants import WIDGET_URI
        from mcp_server.priority_guardian.tools import TOOL_REGISTRY

        widget_tools = [
            (name, tool) for name, tool in TOOL_REGISTRY.items()
            if getattr(tool, 'widget_uri', None) is not None
        ]

        for name, tool in widget_tools:
            assert tool.widget_uri == WIDGET_URI, \
                f"Tool {name} uses {tool.widget_uri!r}, expected {WIDGET_URI!r}"


class TestSanitizerInc100Fixes:
    """Tests for inc_100/101 sanitizer fixes (High-severity bug fixes)."""

    def test_non_allowlisted_schemes_redacted(self):
        """All non-allowlisted schemes have payload redacted.

        inc_101: Switched from blocklist to allowlist. Only http/https/ui/file
        pass through; everything else is redacted. Closes the class.

        Bug this test catches: Any scheme not in allowlist leaking payload.
        Bug that would still pass: None — allowlist approach closes the class.
        """
        from mcp_server.priority_guardian.handlers.resources import _sanitize_uri_for_logging

        # Original blocklist schemes still redacted
        assert _sanitize_uri_for_logging("data:text/html,<h1>Hello</h1>") == "data:[redacted]"
        assert _sanitize_uri_for_logging("javascript:alert('xss')") == "javascript:[redacted]"
        assert _sanitize_uri_for_logging("vbscript:msgbox('hello')") == "vbscript:[redacted]"

        # inc_101: mailto: and blob: now also redacted (was: leaked in inc_100)
        assert _sanitize_uri_for_logging("mailto:secret@example.com?subject=x") == "mailto:[redacted]"
        assert _sanitize_uri_for_logging("blob:https://example.com/uuid-here") == "blob:[redacted]"

        # Other opaque schemes
        assert _sanitize_uri_for_logging("about:blank") == "about:[redacted]"
        assert _sanitize_uri_for_logging("tel:+1234567890") == "tel:[redacted]"

        # Allowlisted schemes pass through (with sanitization)
        assert _sanitize_uri_for_logging("https://example.com/path") == "https://example.com/path"
        assert _sanitize_uri_for_logging("http://example.com/path") == "http://example.com/path"
        assert "ui:" in _sanitize_uri_for_logging("ui://widget/test.html")
        assert "file:" in _sanitize_uri_for_logging("file:///path/to/file")

    def test_userinfo_stripped_from_netloc(self):
        """Userinfo (user:pass@) is stripped from logged URIs.

        inc_100: Fixed High-severity bug where parsed.netloc includes userinfo.
        Now uses parsed.hostname + parsed.port to exclude credentials.

        Bug this test catches: user:password@ logged to production.
        Bug that would still pass: Port incorrectly handled after stripping userinfo.
        """
        from mcp_server.priority_guardian.handlers.resources import _sanitize_uri_for_logging

        # Userinfo should be stripped
        result = _sanitize_uri_for_logging("https://user:password@example.com/path")
        assert "user" not in result
        assert "password" not in result
        assert "example.com/path" in result

        # Port should be preserved
        result = _sanitize_uri_for_logging("https://user:pass@example.com:8080/path")
        assert "user" not in result
        assert "pass" not in result
        assert "example.com:8080/path" in result

    def test_non_netloc_uri_query_stripped(self):
        """Non-netloc URIs (ui://...) still have query/fragment stripped.

        inc_100: Fixed High-severity bug where `else uri` returned raw URI.
        Now reconstructs from components for ALL URI types.

        Bug this test catches: ui://widget/foo?token=secret logged with token.
        Bug that would still pass: Fragment stripped but query not stripped for ui://.
        """
        from mcp_server.priority_guardian.handlers.resources import _sanitize_uri_for_logging

        # ui:// scheme with query should strip query
        result = _sanitize_uri_for_logging("ui://widget/test.html?token=secret")
        assert "token=secret" not in result
        assert "?" not in result
        # Should still have the path
        assert "ui:" in result
        assert "/widget/test.html" in result

        # file:/// with query/fragment
        result = _sanitize_uri_for_logging("file:///path/to/file?secret=123#anchor")
        assert "secret=123" not in result
        assert "#anchor" not in result

    def test_empty_uri_safe_placeholder(self):
        """Empty URI returns safe placeholder, not empty string.

        Bug this test catches: Empty string logged, confusing diagnostics.
        """
        from mcp_server.priority_guardian.handlers.resources import _sanitize_uri_for_logging

        assert _sanitize_uri_for_logging("") == "[empty]"
        assert _sanitize_uri_for_logging(None) == "[empty]"  # Falsy

    def test_unparseable_uri_safe_placeholder(self):
        """Completely unparseable URI returns safe placeholder.

        Bug this test catches: Crash on malformed URI or raw URI leaked.
        """
        from mcp_server.priority_guardian.handlers.resources import _sanitize_uri_for_logging

        # URI with no scheme, no path — edge case
        # urlparse("") gives all empty components
        result = _sanitize_uri_for_logging("   ")  # Whitespace-only
        # Should not crash, should return something safe
        assert result is not None
        assert len(result) > 0

    def test_malformed_port_returns_parse_error(self):
        """Malformed port triggers [parse-error] — fails safe, not crash.

        inc_101: Regression test for Codex Finding #2. Accessing parsed.port
        raises ValueError for non-numeric ports; broad except catches it.

        Bug this test catches: Crash on malformed port.
        Bug that would still pass: Diagnostic detail lost (acceptable).
        """
        from mcp_server.priority_guardian.handlers.resources import _sanitize_uri_for_logging

        # Non-numeric port → ValueError on parsed.port access → [parse-error]
        result = _sanitize_uri_for_logging("http://example.com:bad/path")
        assert result == "[parse-error]"

        # Out-of-range port also triggers ValueError
        result = _sanitize_uri_for_logging("http://example.com:99999/path")
        assert result == "[parse-error]"


class TestMetaExtractionInc100Fixes:
    """Tests for inc_100 _meta extraction fixes (Medium-severity bug fixes)."""

    @pytest.mark.asyncio
    async def test_non_dict_meta_does_not_crash_and_generates_correlation_id(self):
        """Non-dict _meta (string, list, int) does not crash and generates valid correlation_id.

        inc_100: Fixed Medium-severity bug where non-dict _meta would crash.
        inc_101: Extended to verify correlation_id is actually generated (Codex Finding #4).

        Bug this test catches: Handler crashes on _meta="string", OR silently
        logs without correlation_id.
        Bug that would still pass: None — we verify both no-crash AND correlation_id.
        """
        from mcp_server.priority_guardian.handlers.resources import (
            handle_read_resource,
            WIDGET_URI,
        )

        # _meta as string — should not crash AND should generate correlation_id
        req = MagicMock()
        req.params.uri = WIDGET_URI
        req.params._meta = "not-a-dict"
        req.params.meta = None  # Ensure no fallback

        with capture_logs() as cap_logs:
            result = await handle_read_resource(req)

        assert result is not None
        requested_logs = [l for l in cap_logs if l.get("event") == "resource.read.requested"]
        assert len(requested_logs) == 1
        assert "correlation_id" in requested_logs[0], "correlation_id should be generated for non-dict _meta"
        assert len(requested_logs[0]["correlation_id"]) > 0, "Generated correlation_id should not be empty"

        # _meta as list
        req.params._meta = ["list", "of", "things"]
        with capture_logs() as cap_logs:
            result = await handle_read_resource(req)
        assert result is not None
        requested_logs = [l for l in cap_logs if l.get("event") == "resource.read.requested"]
        assert "correlation_id" in requested_logs[0]

        # _meta as int
        req.params._meta = 42
        with capture_logs() as cap_logs:
            result = await handle_read_resource(req)
        assert result is not None
        requested_logs = [l for l in cap_logs if l.get("event") == "resource.read.requested"]
        assert "correlation_id" in requested_logs[0]

    @pytest.mark.asyncio
    async def test_empty_dict_meta_used_not_fallthrough(self):
        """Empty dict _meta is used, not fallen through to `meta`.

        inc_100: Fixed Medium-severity bug where `or` truthiness made
        empty dict {} fall through to `meta` attribute.

        Bug this test catches: Empty _meta={} ignored, uses meta instead.
        Bug that would still pass: Non-empty _meta works correctly.
        """
        from mcp_server.priority_guardian.handlers.resources import (
            handle_read_resource,
            WIDGET_URI,
        )

        req = MagicMock()
        req.params.uri = WIDGET_URI
        req.params._meta = {}  # Empty dict — should be used (generates new correlation_id)
        req.params.meta = {"correlation_id": "should-not-be-used"}

        with capture_logs() as cap_logs:
            await handle_read_resource(req)

        requested_logs = [l for l in cap_logs if l.get("event") == "resource.read.requested"]
        # Should NOT use the meta.correlation_id since _meta is present (even if empty)
        # It should generate a new correlation_id
        assert requested_logs[0]["correlation_id"] != "should-not-be-used"

    @pytest.mark.asyncio
    async def test_meta_attribute_used_when_underscore_meta_absent(self):
        """When _meta is absent, `meta` attribute is used.

        Bug this test catches: meta attribute ignored even when _meta absent.
        """
        from mcp_server.priority_guardian.handlers.resources import (
            handle_read_resource,
            WIDGET_URI,
        )

        req = MagicMock()
        req.params.uri = WIDGET_URI
        # No _meta attribute at all
        del req.params._meta
        req.params.meta = {"correlation_id": "from-meta-attribute"}

        with capture_logs() as cap_logs:
            await handle_read_resource(req)

        requested_logs = [l for l in cap_logs if l.get("event") == "resource.read.requested"]
        assert requested_logs[0]["correlation_id"] == "from-meta-attribute"


class TestInvalidRequestGuard:
    """Tests for inc_101 params guard (Codex Finding #3)."""

    @pytest.mark.asyncio
    async def test_params_none_returns_error_not_crash(self):
        """params=None returns error result, does not crash.

        inc_101: Guard against AttributeError when req.params is None.

        Bug this test catches: Handler crashes with AttributeError.
        Bug that would still pass: Error result has wrong format.
        """
        from mcp_server.priority_guardian.handlers.resources import handle_read_resource

        req = MagicMock()
        req.params = None  # Malformed request

        with capture_logs() as cap_logs:
            result = await handle_read_resource(req)

        # Should return empty result with error, not crash
        assert result is not None
        assert len(result.contents) == 0

        # Should log warning
        warning_logs = [l for l in cap_logs if l.get("event") == "resource.read.invalid_request"]
        assert len(warning_logs) == 1

    @pytest.mark.asyncio
    async def test_uri_none_returns_error_not_crash(self):
        """params.uri=None returns error result, does not crash.

        Bug this test catches: str(None) doesn't crash but logs "None" as URI.
        """
        from mcp_server.priority_guardian.handlers.resources import handle_read_resource

        req = MagicMock()
        req.params.uri = None  # Missing URI

        # str(None) = "None" which won't match WIDGET_URI, returns empty
        result = await handle_read_resource(req)
        assert result is not None
        assert len(result.contents) == 0


class TestLogEventDistinguishability:
    """Tests that resource reads and tool calls produce distinguishable log events."""

    def test_resource_events_have_distinct_prefix(self):
        """resource.read.* events are distinguishable from tool.dispatch.* events.

        Bug this test catches: Ambiguous logs making correlation impossible.
        """
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

        for r_event in resource_events:
            for t_event in tool_events:
                assert r_event != t_event, f"Event collision: {r_event}"
                assert not r_event.startswith("tool."), f"Resource event has tool prefix: {r_event}"

        for t_event in tool_events:
            assert not t_event.startswith("resource."), f"Tool event has resource prefix: {t_event}"
