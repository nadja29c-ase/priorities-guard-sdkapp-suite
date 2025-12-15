"""
Unit tests for Clarity HTTP client module.

Tests the module-level HTTP client configuration including timeouts.

IMPORTANT - Timeout Enforcement:
    Callers must use get_http_client() exclusively.
    Timeout is guaranteed at client level, not per-request.
    See test_persistence.py for caller verification tests.

Startup Behavior:
    If httpx.AsyncClient() raises during creation, MCP startup fails fast.
    This is intentional - misconfigured HTTP is not recoverable at runtime.
"""

import httpx
import pytest
from unittest.mock import patch, MagicMock

from mcp_server.clarity.http_client import get_http_client, cleanup_http_client


def _get_effective_timeout(timeout) -> float:
    """Extract effective timeout value for assertions.

    Handles both float and httpx.Timeout objects.
    For Timeout objects, returns the connect timeout as representative value.
    """
    if isinstance(timeout, httpx.Timeout):
        return timeout.connect
    return float(timeout)


class TestHttpClientConfiguration:
    """Tests for HTTP client configuration."""

    @pytest.fixture(autouse=True)
    def reset_client(self):
        """Reset the module-level client before each test."""
        import mcp_server.clarity.http_client as http_module
        http_module._http_client = None
        yield
        http_module._http_client = None

    def test_client_has_timeout_configured(self):
        """Client must be created with a timeout to prevent MCP hangs.

        This locks in the production guarantee that requests will not hang forever.
        """
        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value = MagicMock()

            get_http_client()

            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args.kwargs
            assert "timeout" in call_kwargs, "HTTP client must specify a timeout"
            timeout = call_kwargs["timeout"]
            assert isinstance(timeout, (int, float, httpx.Timeout)), \
                f"Timeout must be numeric or httpx.Timeout, got {type(timeout)}"
            assert _get_effective_timeout(timeout) > 0, "Timeout must be positive"

    def test_client_timeout_is_reasonable(self):
        """Timeout should be reasonable (not too short, not too long)."""
        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value = MagicMock()

            get_http_client()

            timeout = mock_client_class.call_args.kwargs["timeout"]
            effective = _get_effective_timeout(timeout)
            assert 5 <= effective <= 30, f"Timeout {effective}s should be between 5-30 seconds"

    def test_client_timeout_default_value(self):
        """Lock in expected default timeout value.

        Prevents silent changes during refactoring.
        If this needs to change, update intentionally.
        """
        # Expected default: 10 seconds (hardcoded in http_client.py)
        EXPECTED_DEFAULT_TIMEOUT = 10.0

        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value = MagicMock()

            get_http_client()

            timeout = mock_client_class.call_args.kwargs["timeout"]
            effective = _get_effective_timeout(timeout)
            assert effective == EXPECTED_DEFAULT_TIMEOUT, \
                f"Expected {EXPECTED_DEFAULT_TIMEOUT}s timeout, got {effective}s"

    def test_client_is_reused(self):
        """Client should be reused across calls (connection pooling)."""
        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance

            client1 = get_http_client()
            client2 = get_http_client()

            assert client1 is client2, "Client should be reused"
            mock_client_class.assert_called_once()  # Only created once

    @pytest.mark.asyncio
    async def test_cleanup_closes_client(self):
        """Cleanup should close the HTTP client."""
        from unittest.mock import AsyncMock as AsyncMockClass

        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_instance = MagicMock()
            mock_instance.aclose = AsyncMockClass(return_value=None)
            mock_client_class.return_value = mock_instance

            get_http_client()  # Create client
            await cleanup_http_client()

            mock_instance.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_resets_module_state(self):
        """Cleanup must set _http_client to None.

        Prevents subtle bugs where closed client reference remains cached.
        """
        import mcp_server.clarity.http_client as http_module
        from unittest.mock import AsyncMock as AsyncMockClass

        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_instance = MagicMock()
            mock_instance.aclose = AsyncMockClass(return_value=None)
            mock_client_class.return_value = mock_instance

            get_http_client()  # Create client
            assert http_module._http_client is not None, "Client should exist before cleanup"

            await cleanup_http_client()

            assert http_module._http_client is None, "Client reference must be cleared after cleanup"

    @pytest.mark.asyncio
    async def test_cleanup_is_idempotent_when_no_client(self):
        """Cleanup must not crash when called with no client.

        Shutdown hooks can fire before client is created.
        """
        await cleanup_http_client()  # No client exists
        await cleanup_http_client()  # Still no crash

    @pytest.mark.asyncio
    async def test_cleanup_is_idempotent_after_client_created(self):
        """Cleanup must not crash when called twice after client exists.

        Shutdown hooks can fire multiple times in production.
        """
        from unittest.mock import AsyncMock as AsyncMockClass

        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_instance = MagicMock()
            mock_instance.aclose = AsyncMockClass(return_value=None)
            mock_client_class.return_value = mock_instance

            get_http_client()  # Create client
            await cleanup_http_client()  # First cleanup
            await cleanup_http_client()  # Second cleanup - must not crash

            mock_instance.aclose.assert_called_once()  # Only closed once

    @pytest.mark.asyncio
    async def test_client_recreated_after_cleanup(self):
        """New client must be created after cleanup.

        Prevents silently reusing a closed client.
        """
        from unittest.mock import AsyncMock as AsyncMockClass

        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_instance1 = MagicMock()
            mock_instance1.aclose = AsyncMockClass(return_value=None)
            mock_instance2 = MagicMock()
            mock_client_class.side_effect = [mock_instance1, mock_instance2]

            client1 = get_http_client()
            await cleanup_http_client()
            client2 = get_http_client()

            assert client1 is not client2, "Must create new client after cleanup"
            assert client1 is mock_instance1
            assert client2 is mock_instance2
            assert mock_client_class.call_count == 2

    def test_client_creation_failure_propagates(self):
        """Client creation failure must propagate (fail fast).

        If httpx.AsyncClient() raises during creation, MCP startup should fail.
        No swallowing, no fallback - misconfigured HTTP is not recoverable.
        """
        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_client_class.side_effect = RuntimeError("Connection pool misconfigured")

            with pytest.raises(RuntimeError, match="Connection pool misconfigured"):
                get_http_client()

    @pytest.mark.asyncio
    async def test_concurrent_get_http_client_returns_same_instance(self):
        """Multiple calls to get_http_client() must return the same instance.

        IMPORTANT LIMITATION:
        This test documents expected singleton behavior, NOT thread-safety.
        - get_http_client() is synchronous
        - Python's GIL prevents true concurrent execution of pure Python
        - asyncio.gather here just runs calls sequentially under the hood

        What this test DOES verify:
        - Singleton pattern works (all callers get same instance)
        - No accidental recreation on each call

        What this test does NOT guarantee:
        - Thread-safety under true multi-threading
        - Race condition prevention

        If true thread-safety is needed, add a lock to get_http_client()
        and update this test to verify lock acquisition.
        """
        import asyncio

        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_instance = MagicMock()
            mock_client_class.return_value = mock_instance

            # Multiple calls (sequential under GIL, but documents expectation)
            async def get_client():
                return get_http_client()

            results = await asyncio.gather(*[get_client() for _ in range(10)])

            # All must return the same instance (singleton pattern)
            assert all(r is results[0] for r in results), \
                "All calls must return the same client instance"

            # Client should only be created once
            mock_client_class.assert_called_once()

    def test_timeout_bounds_all_phases(self):
        """All timeout phases (connect/read/write) must be bounded.

        If httpx.Timeout is used, no phase should be unbounded (None).
        Unbounded phases can cause MCP to hang indefinitely.
        """
        with patch("mcp_server.clarity.http_client.httpx.AsyncClient") as mock_client_class:
            mock_client_class.return_value = MagicMock()

            get_http_client()

            timeout = mock_client_class.call_args.kwargs["timeout"]

            if isinstance(timeout, httpx.Timeout):
                # All phases must be bounded
                assert timeout.connect is not None, "Connect timeout must be bounded"
                assert timeout.read is not None, "Read timeout must be bounded"
                assert timeout.write is not None, "Write timeout must be bounded"
                assert timeout.pool is not None, "Pool timeout must be bounded"

                # All phases should have positive values
                assert timeout.connect > 0, "Connect timeout must be positive"
                assert timeout.read > 0, "Read timeout must be positive"
                assert timeout.write > 0, "Write timeout must be positive"
                assert timeout.pool > 0, "Pool timeout must be positive"
            else:
                # Single float value applies to all phases - this is safe
                assert float(timeout) > 0, "Timeout must be positive"
