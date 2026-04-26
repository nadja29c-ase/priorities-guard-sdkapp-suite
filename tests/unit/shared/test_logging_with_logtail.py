"""
Unit tests for shared logging module with Better Stack (logtail) integration.

Tests verify:
- Scrubber runs before LogtailHandler (GDPR safety net)
- Payload is JSON string (structlog -> stdlib bridge)
- LogtailHandler conditional attachment
- Idempotency guard
- Graceful degradation on init failure
- No backend coupling
"""

import ast
import json
import logging
import os
import sys
from importlib import reload
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import structlog


# Global list for capturing records - needs to survive module reload
_captured_records = []


def make_capturing_handler_class(name="CapturingHandler"):
    """Create a fresh handler class with the specified name."""
    class Handler(logging.Handler):
        def __init__(self, **kwargs):
            super().__init__()

        def emit(self, record):
            _captured_records.append(record)

    Handler.__name__ = name
    Handler.__qualname__ = name
    return Handler


@pytest.fixture(autouse=True)
def reset_logging_state():
    """Reset logging state before and after each test."""
    # Clear structlog configuration
    structlog.reset_defaults()

    # Remove all handlers from root logger
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Clear captured records
    _captured_records.clear()

    # Reset log level
    logging.root.setLevel(logging.WARNING)

    yield

    # Restore original state
    structlog.reset_defaults()
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    _captured_records.clear()


@pytest.fixture
def captured_records():
    """Provide access to captured LogRecords."""
    return _captured_records


class TestScrubberIntegration:
    """Tests for scrubber running before LogtailHandler."""

    def test_scrubber_redacts_access_token_before_handler_receives_data(
        self, captured_records
    ):
        """Scrubber must redact sensitive fields before LogtailHandler sees them."""
        HandlerClass = make_capturing_handler_class("TestLogtailHandler")

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                logger.info("oauth.token_received", access_token="secret-oauth-token-12345")

        matching = [r for r in captured_records if "oauth.token_received" in str(r.msg)]
        assert len(matching) >= 1, f"Expected at least one matching log record. Got: {[str(r.msg) for r in captured_records]}"

        # Parse the JSON payload
        record = matching[0]
        assert isinstance(record.msg, str), "record.msg should be a JSON string"
        payload = json.loads(record.msg)

        # Verify the token is redacted
        assert payload.get("access_token") == "[REDACTED]"
        assert "secret-oauth-token-12345" not in record.msg

    def test_scrubber_redacts_all_sensitive_keys(self, captured_records):
        """All sensitive keys in REDACT_KEYS must be scrubbed."""
        sensitive_keys = [
            "access_token",
            "refresh_token",
            "authorization_code",
            "token",
            "code_verifier",
            "code_challenge",
            "client_secret",
            "password",
            "secret",
            "encrypted_access_token",
            "encrypted_refresh_token",
        ]

        HandlerClass = make_capturing_handler_class("TestLogtailHandler2")

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                # Log with all sensitive keys
                logger.info("security.test", **{k: f"value-{k}" for k in sensitive_keys})

        matching = [r for r in captured_records if "security.test" in str(r.msg)]
        assert len(matching) >= 1

        payload = json.loads(matching[0].msg)
        for key in sensitive_keys:
            assert payload.get(key) == "[REDACTED]", f"Key {key} should be redacted"

    def test_scrubber_redacts_client_secret_enc(self, captured_records):
        """client_secret_enc (DB column on CoreConnection) must be redacted."""
        HandlerClass = make_capturing_handler_class("TestLogtailHandler_secret_enc")

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                logger.info(
                    "oauth.client_loaded",
                    client_secret_enc="encrypted-secret-payload",
                    id_token="should-also-be-redacted",
                )

        matching = [r for r in captured_records if "oauth.client_loaded" in str(r.msg)]
        assert len(matching) >= 1

        payload = json.loads(matching[0].msg)
        assert payload.get("client_secret_enc") == "[REDACTED]"
        assert payload.get("id_token") == "[REDACTED]"
        assert "encrypted-secret-payload" not in matching[0].msg
        assert "should-also-be-redacted" not in matching[0].msg


class TestPayloadShape:
    """Tests for payload format reaching handlers."""

    def test_payload_is_json_string_not_dict(self, captured_records):
        """LogRecord.msg must be a JSON string for logtail compatibility."""
        HandlerClass = make_capturing_handler_class("TestLogtailHandler3")

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                logger.info("test.event", foo="bar", count=42)

        matching = [r for r in captured_records if "test.event" in str(r.msg)]
        assert len(matching) >= 1

        record = matching[0]
        # Must be a string
        assert isinstance(record.msg, str), "record.msg must be a string"
        # Must be valid JSON
        parsed = json.loads(record.msg)
        assert isinstance(parsed, dict)
        assert parsed.get("event") == "test.event"
        assert parsed.get("foo") == "bar"
        assert parsed.get("count") == 42


class TestLogtailHandlerAttachment:
    """Tests for conditional LogtailHandler attachment."""

    def test_handler_added_when_token_set(self):
        """LogtailHandler should be added when BETTER_STACK_SOURCE_TOKEN is set."""
        mock_handler_instance = MagicMock()
        mock_handler_instance.__class__.__name__ = "LogtailHandler"
        mock_handler_instance.level = logging.NOTSET  # Handler needs a level for logging comparison
        mock_handler_class = MagicMock(return_value=mock_handler_instance)

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = mock_handler_class

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

        mock_handler_class.assert_called_once_with(source_token="test-token")
        assert mock_handler_instance in logging.root.handlers

    def test_handler_not_added_when_token_empty(self):
        """LogtailHandler should NOT be added when token is empty."""
        mock_handler_class = MagicMock()

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = mock_handler_class

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

        mock_handler_class.assert_not_called()

    def test_handler_not_added_when_token_unset(self):
        """LogtailHandler should NOT be added when token env var is unset."""
        mock_handler_class = MagicMock()

        env = {"ENV": "dev"}  # Explicitly don't include BETTER_STACK_SOURCE_TOKEN

        with patch.dict(os.environ, env, clear=True):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = mock_handler_class

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

        mock_handler_class.assert_not_called()


class TestIdempotency:
    """Tests for idempotency guard."""

    def test_calling_configure_twice_adds_only_one_handler(self):
        """Calling configure_logging() twice should attach only one LogtailHandler."""
        call_count = 0

        class FakeLogtailHandler(logging.Handler):
            def __init__(self, **kwargs):
                nonlocal call_count
                call_count += 1
                super().__init__()

            def emit(self, record):
                pass

        # Set class name for idempotency check
        FakeLogtailHandler.__name__ = "LogtailHandler"

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = FakeLogtailHandler

                import shared.logging as shared_logging
                reload(shared_logging)

                # First call
                shared_logging.configure_logging()

                # Second call - should detect existing handler and skip
                structlog.reset_defaults()  # Reset structlog but keep handlers
                shared_logging.configure_logging()

        # Handler should only be created once
        assert call_count == 1, f"LogtailHandler should only be instantiated once, but was called {call_count} times"


class TestGracefulDegradation:
    """Tests for graceful degradation on init failure."""

    def test_init_failure_does_not_raise(self):
        """configure_logging should not raise if LogtailHandler init fails."""

        def failing_handler(**kwargs):
            raise Exception("Network unreachable")

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = failing_handler

                import shared.logging as shared_logging
                reload(shared_logging)

                # Should not raise
                shared_logging.configure_logging()

    def test_init_failure_logs_warning(self, caplog):
        """Init failure should log a warning with error details."""

        def failing_handler(**kwargs):
            raise Exception("Network unreachable")

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = failing_handler

                import shared.logging as shared_logging
                reload(shared_logging)

                with caplog.at_level(logging.WARNING):
                    shared_logging.configure_logging()

        # Check caplog for the warning
        assert any("betterstack.init_failed" in r.message for r in caplog.records) or \
               any("Network unreachable" in r.message for r in caplog.records), \
               f"Expected init_failed warning in logs. Got: {[r.message for r in caplog.records]}"

    def test_init_failure_does_not_add_handler(self):
        """Failed init should not leave a handler attached."""

        def failing_handler(**kwargs):
            raise Exception("Network unreachable")

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = failing_handler

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

        # No LogtailHandler should be attached
        logtail_handlers = [
            h for h in logging.root.handlers if type(h).__name__ == "LogtailHandler"
        ]
        assert len(logtail_handlers) == 0


class TestNoBackendCoupling:
    """Tests for ensuring shared.logging has no backend dependencies."""

    def test_no_backend_imports_in_source(self):
        """shared/logging.py must not have import statements from backend.*"""
        shared_logging_path = (
            Path(__file__).parent.parent.parent.parent / "shared" / "logging.py"
        )
        assert shared_logging_path.exists(), f"File not found: {shared_logging_path}"

        source = shared_logging_path.read_text()

        # Check for actual import statements (not just any text containing "from backend")
        # Look for patterns like "from backend." or "import backend"
        lines = source.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Skip comments and docstrings
            if stripped.startswith("#"):
                continue
            if stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            # Check for actual import statements
            if stripped.startswith("from backend"):
                pytest.fail(f"Found backend import on line {i+1}: {line}")
            if stripped.startswith("import backend"):
                pytest.fail(f"Found backend import on line {i+1}: {line}")

    def test_no_backend_imports_via_ast(self):
        """Verify no backend imports using AST analysis."""
        shared_logging_path = (
            Path(__file__).parent.parent.parent.parent / "shared" / "logging.py"
        )
        source = shared_logging_path.read_text()
        tree = ast.parse(source)

        backend_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("backend"):
                        backend_imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("backend"):
                    backend_imports.append(node.module)

        assert len(backend_imports) == 0, f"Found backend imports: {backend_imports}"


class TestExistingProcessors:
    """Tests for existing structlog processors still running."""

    def test_correlation_id_added(self, captured_records):
        """Logs should have correlation_id field."""
        HandlerClass = make_capturing_handler_class("TestLogtailHandler4")

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                logger.info("test.correlation")

        matching = [r for r in captured_records if "test.correlation" in str(r.msg)]
        assert len(matching) >= 1

        payload = json.loads(matching[0].msg)
        assert "correlation_id" in payload
        assert payload["correlation_id"] == "system"  # Default for non-HTTP logs

    def test_timestamp_added_iso_format(self, captured_records):
        """Logs should have ISO 8601 timestamp."""
        HandlerClass = make_capturing_handler_class("TestLogtailHandler5")

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                logger.info("test.timestamp")

        matching = [r for r in captured_records if "test.timestamp" in str(r.msg)]
        assert len(matching) >= 1

        payload = json.loads(matching[0].msg)
        assert "timestamp" in payload
        # ISO 8601 format check (basic)
        assert "T" in payload["timestamp"]
        assert "-" in payload["timestamp"]

    def test_json_renderer_produces_json(self, captured_records):
        """Logs should be valid JSON."""
        HandlerClass = make_capturing_handler_class("TestLogtailHandler6")

        with patch.dict(os.environ, {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                logger.info("test.json", data={"nested": {"value": 123}})

        matching = [r for r in captured_records if "test.json" in str(r.msg)]
        assert len(matching) >= 1

        # Should parse as valid JSON
        payload = json.loads(matching[0].msg)
        assert payload["data"] == {"nested": {"value": 123}}


class TestServiceField:
    """Tests for service field injection (filtering across single Better Stack source)."""

    def test_service_field_uses_env_var_when_set(self, captured_records):
        """SERVICE_NAME env var should appear as 'service' field in payload."""
        HandlerClass = make_capturing_handler_class("TestLogtailHandler_service_env")

        with patch.dict(
            os.environ,
            {
                "BETTER_STACK_SOURCE_TOKEN": "test-token",
                "ENV": "dev",
                "SERVICE_NAME": "priority-guardian-backend",
            },
        ):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                logger.info("test.service_field")

        matching = [r for r in captured_records if "test.service_field" in str(r.msg)]
        assert len(matching) >= 1

        payload = json.loads(matching[0].msg)
        assert payload.get("service") == "priority-guardian-backend"

    def test_service_field_default_when_env_unset(self, captured_records):
        """When SERVICE_NAME is unset, fall back to 'priority-guard-suite'."""
        HandlerClass = make_capturing_handler_class("TestLogtailHandler_service_default")

        env = {"BETTER_STACK_SOURCE_TOKEN": "test-token", "ENV": "dev"}  # no SERVICE_NAME

        with patch.dict(os.environ, env, clear=True):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                logger.info("test.service_default")

        matching = [r for r in captured_records if "test.service_default" in str(r.msg)]
        assert len(matching) >= 1

        payload = json.loads(matching[0].msg)
        assert payload.get("service") == "priority-guard-suite"

    def test_explicit_service_kwarg_not_overwritten(self, captured_records):
        """If caller passes service= kwarg explicitly, processor must not overwrite it."""
        HandlerClass = make_capturing_handler_class("TestLogtailHandler_service_explicit")

        with patch.dict(
            os.environ,
            {
                "BETTER_STACK_SOURCE_TOKEN": "test-token",
                "ENV": "dev",
                "SERVICE_NAME": "priority-guardian-backend",
            },
        ):
            with patch.dict("sys.modules", {"logtail": MagicMock()}):
                sys.modules["logtail"].LogtailHandler = HandlerClass

                import shared.logging as shared_logging
                reload(shared_logging)

                shared_logging.configure_logging()

                logger = structlog.get_logger("test")
                # RequestLoggingMiddleware passes service=service_name as kwarg
                logger.info("http.request", service="priority-guardian-mcp")

        matching = [r for r in captured_records if "http.request" in str(r.msg)]
        assert len(matching) >= 1

        payload = json.loads(matching[0].msg)
        # Explicit kwarg wins over env var
        assert payload.get("service") == "priority-guardian-mcp"
