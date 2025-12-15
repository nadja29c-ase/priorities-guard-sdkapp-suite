"""
Unit tests for Clarity persistence module.

Note on patching INTERNAL_API_SECRET:
  We patch at 'mcp_server.clarity.persistence.INTERNAL_API_SECRET' because
  persistence.py imports it directly: `from .config import INTERNAL_API_SECRET`.
  If that import style changes, these patches will need updating.
"""

import httpx
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from mcp_server.clarity.persistence import persist_cluster, get_cluster


class TestPersistCluster:
    """Tests for the persist_cluster function."""

    @pytest.mark.asyncio
    async def test_persist_cluster_success(self):
        """Should return cluster_id on successful persistence."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"cluster_id": "test-cluster-123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await persist_cluster(
                user_id="user-456",
                cluster_data={"clusters": [{"cluster_name": "Test"}]},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

        assert result == "test-cluster-123"
        mock_client.post.assert_called_once()

        # Verify URL and payload
        call_args = mock_client.post.call_args
        assert call_args.args[0].endswith("/api/clarity/clusters")
        assert "X-User-ID" in call_args.kwargs["headers"]
        assert call_args.kwargs["json"]["thoughts_exhausted"] is True

    @pytest.mark.asyncio
    async def test_persist_cluster_failure_returns_none(self):
        """Should return None on non-201 response."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await persist_cluster(
                user_id="user-456",
                cluster_data={"clusters": []},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_persist_cluster_exception_returns_none(self):
        """Should return None on network/exception error."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Network error"))

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await persist_cluster(
                user_id="user-456",
                cluster_data={"clusters": []},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_persist_cluster_empty_user_id_returns_none(self):
        """Should return None when user_id is empty string (defensive boundary test).

        Documents behavior: sends X-User-ID: '' header, backend returns 401,
        function returns None without crashing.
        """
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await persist_cluster(
                user_id="",
                cluster_data={"clusters": []},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_persist_cluster_uses_post_not_get(self):
        """Should use POST method, never GET (defensive method check)."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"cluster_id": "test-123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.get = AsyncMock()

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            await persist_cluster(
                user_id="user-456",
                cluster_data={"clusters": []},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

        mock_client.post.assert_called_once()
        mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_cluster_uses_shared_http_client(self):
        """Should use get_http_client() which has timeout configured.

        IMPORTANT: The timeout guarantee comes from the shared HTTP client
        (see http_client.py: httpx.AsyncClient(timeout=10.0)).

        This test ensures we always use get_http_client() and don't bypass it
        with a custom client that might lack timeout configuration.
        If this test fails, MCP could hang on slow/unresponsive backends.
        """
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"cluster_id": "test-123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client") as mock_get_client:
            mock_get_client.return_value = mock_client

            await persist_cluster(
                user_id="user-456",
                cluster_data={"clusters": []},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

            # Verify get_http_client() was called (not bypassed)
            mock_get_client.assert_called_once()
            # Verify the exact client instance was used (locks timeout end-to-end)
            assert mock_client is mock_get_client.return_value
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_persist_cluster_logs_on_failure(self):
        """Should log warning on failure (ops visibility guarantee)."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Network failure"))

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            with patch("mcp_server.clarity.persistence.logger") as mock_logger:
                await persist_cluster(
                    user_id="user-456",
                    cluster_data={"clusters": []},
                    thoughts_exhausted=True,
                    correctly_clustered=None,
                )

                mock_logger.warning.assert_called_once()
                # Verify error details are logged
                call_args = mock_logger.warning.call_args
                assert "clarity.persist.error" in call_args.args

    @pytest.mark.asyncio
    async def test_persist_cluster_includes_internal_secret(self):
        """Should include X-Internal-Secret header when configured."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"cluster_id": "test-123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            with patch("mcp_server.clarity.persistence.INTERNAL_API_SECRET", "secret-key"):
                await persist_cluster(
                    user_id="user-456",
                    cluster_data={"clusters": []},
                    thoughts_exhausted=True,
                    correctly_clustered=None,
                )

        call_args = mock_client.post.call_args
        assert call_args.kwargs["headers"]["X-Internal-Secret"] == "secret-key"

    @pytest.mark.asyncio
    async def test_persist_cluster_headers_not_overwritten(self):
        """Both X-User-ID and X-Internal-Secret must be present together.

        Catches accidental header dict overwrite like:
            headers = {"X-Internal-Secret": ...}  # silently drops X-User-ID
        """
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"cluster_id": "test-123"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            with patch("mcp_server.clarity.persistence.INTERNAL_API_SECRET", "secret-key"):
                await persist_cluster(
                    user_id="user-456",
                    cluster_data={"clusters": []},
                    thoughts_exhausted=True,
                    correctly_clustered=None,
                )

        headers = mock_client.post.call_args.kwargs["headers"]
        # Both headers must be present simultaneously
        assert "X-User-ID" in headers, "X-User-ID must not be overwritten"
        assert "X-Internal-Secret" in headers, "X-Internal-Secret must be present"
        assert headers["X-User-ID"] == "user-456"
        assert headers["X-Internal-Secret"] == "secret-key"

    @pytest.mark.asyncio
    async def test_persist_cluster_null_cluster_id_returns_none(self):
        """Partial success payloads with null cluster_id must return None.

        Backend might return:
            {"cluster_id": null}

        This is a partial success that should be treated as failure.
        Prevents leaking None as valid ID into ChatGPT context.
        """
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"cluster_id": None}  # Partial success

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await persist_cluster(
                user_id="user-456",
                cluster_data={"clusters": [{"cluster_name": "Test"}]},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

        # None cluster_id is returned as-is (caller decides if acceptable)
        # This documents current behavior - if stricter, add validation
        assert result is None

    @pytest.mark.asyncio
    async def test_persist_cluster_200_is_treated_as_failure(self):
        """Only 201 Created is valid - 200 OK must be treated as failure.

        Strict contract enforcement. Backend refactors might accidentally
        change to 200 - this test catches the drift immediately.

        201 = resource created (correct for POST creating new cluster)
        200 = generic success (wrong for creation semantics)
        """
        mock_response = MagicMock()
        mock_response.status_code = 200  # Wrong - should be 201
        mock_response.json.return_value = {"cluster_id": "test-cluster-123"}
        mock_response.text = "OK"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await persist_cluster(
                user_id="user-456",
                cluster_data={"clusters": [{"cluster_name": "Test"}]},
                thoughts_exhausted=True,
                correctly_clustered=None,
            )

        # 200 is not 201, so treated as failure
        assert result is None


class TestGetCluster:
    """Tests for the get_cluster function."""

    @pytest.mark.asyncio
    async def test_get_cluster_returns_single_latest_snapshot(self):
        """Documents contract: backend returns the single most recent cluster snapshot.

        IMPORTANT CONTRACT ASSUMPTION (Increment 10):
        - Backend GET /api/clarity/clusters returns ONE snapshot (the latest)
        - Not a list, not paginated - single most recent row per user
        - Backend handles ordering (ORDER BY created_at DESC LIMIT 1)
        - If backend changes to return multiple/paginated, this test should fail
          and get_my_clusters tool logic needs updating

        This test doesn't verify ordering (can't at this layer) but documents
        the assumption that callers depend on.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cluster_id": "latest-snapshot-id",
            "cluster_data": {"clusters": [{"cluster_name": "Latest"}]},
            "thoughts_exhausted": True,
            "correctly_clustered": True,
            "created_at": "2025-01-15T12:00:00Z",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        # Contract: returns a single dict, not a list
        assert isinstance(result, dict)
        assert "cluster_id" in result
        assert "cluster_data" in result
        assert "created_at" in result

    @pytest.mark.asyncio
    async def test_get_cluster_rejects_list_response(self):
        """Contract enforcement: backend must return dict, not list.

        If backend changes to return multiple/paginated results as a list,
        persistence layer rejects it (returns None) and logs contract violation.
        Prevents silent contract drift where list[0] would be accessed incorrectly.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"cluster_id": "cluster-1", "cluster_data": {}},
            {"cluster_id": "cluster-2", "cluster_data": {}},
        ]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        # Contract enforced: list response rejected, returns None
        assert result is None

    @pytest.mark.asyncio
    async def test_get_cluster_logs_contract_violation_for_list(self):
        """Should log warning when backend returns list (ops visibility)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"cluster_id": "cluster-1"}]

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            with patch("mcp_server.clarity.persistence.logger") as mock_logger:
                await get_cluster(user_id="user-456")

                mock_logger.warning.assert_called_once()
                call_args = mock_logger.warning.call_args
                assert "clarity.retrieve.contract_violation" in call_args.args

    @pytest.mark.asyncio
    async def test_get_cluster_success(self):
        """Should return cluster_data when 200 response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cluster_id": "cluster-abc",
            "cluster_data": {"clusters": [{"cluster_name": "Test Cluster"}]},
            "thoughts_exhausted": True,
            "correctly_clustered": None,
            "created_at": "2025-01-15T10:00:00Z",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        assert result is not None
        assert result["cluster_id"] == "cluster-abc"
        assert result["cluster_data"]["clusters"][0]["cluster_name"] == "Test Cluster"
        mock_client.get.assert_called_once()

        # Verify URL and headers
        call_args = mock_client.get.call_args
        assert call_args.args[0].endswith("/api/clarity/clusters")
        assert call_args.kwargs["headers"]["X-User-ID"] == "user-456"

    @pytest.mark.asyncio
    async def test_get_cluster_not_found(self):
        """Should return None when 404 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not Found"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-no-clusters")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cluster_network_error_returns_none(self):
        """Should return None on network exception (connection refused, timeout, etc)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Network error"))

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cluster_uses_get_not_post(self):
        """Should use GET method, never POST (defensive method check)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"cluster_id": "test-123", "cluster_data": {}}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.post = AsyncMock()

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            await get_cluster(user_id="user-456")

        mock_client.get.assert_called_once()
        mock_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_cluster_uses_shared_http_client(self):
        """Should use get_http_client() which has timeout configured.

        IMPORTANT: The timeout guarantee comes from the shared HTTP client
        (see http_client.py: httpx.AsyncClient(timeout=10.0)).

        This test ensures we always use get_http_client() and don't bypass it
        with a custom client that might lack timeout configuration.
        If this test fails, MCP could hang on slow/unresponsive backends.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"cluster_id": "test-123", "cluster_data": {}}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client") as mock_get_client:
            mock_get_client.return_value = mock_client

            await get_cluster(user_id="user-456")

            # Verify get_http_client() was called (not bypassed)
            mock_get_client.assert_called_once()
            # Verify the exact client instance was used (locks timeout end-to-end)
            assert mock_client is mock_get_client.return_value
            mock_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cluster_logs_on_failure(self):
        """Should log warning on failure (ops visibility guarantee)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Network failure"))

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            with patch("mcp_server.clarity.persistence.logger") as mock_logger:
                await get_cluster(user_id="user-456")

                mock_logger.warning.assert_called_once()
                # Verify error details are logged
                call_args = mock_logger.warning.call_args
                assert "clarity.retrieve.error" in call_args.args

    @pytest.mark.asyncio
    async def test_get_cluster_includes_internal_secret(self):
        """Should include X-Internal-Secret header when configured."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cluster_id": "cluster-abc",
            "cluster_data": {"clusters": []},
            "thoughts_exhausted": True,
            "correctly_clustered": None,
            "created_at": "2025-01-15T10:00:00Z",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            with patch("mcp_server.clarity.persistence.INTERNAL_API_SECRET", "secret-key"):
                await get_cluster(user_id="user-456")

        call_args = mock_client.get.call_args
        assert call_args.kwargs["headers"]["X-Internal-Secret"] == "secret-key"

    @pytest.mark.asyncio
    async def test_get_cluster_headers_not_overwritten(self):
        """Both X-User-ID and X-Internal-Secret must be present together.

        Catches accidental header dict overwrite like:
            headers = {"X-Internal-Secret": ...}  # silently drops X-User-ID
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "cluster_id": "cluster-abc",
            "cluster_data": {"clusters": []},
            "thoughts_exhausted": True,
            "correctly_clustered": None,
            "created_at": "2025-01-15T10:00:00Z",
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            with patch("mcp_server.clarity.persistence.INTERNAL_API_SECRET", "secret-key"):
                await get_cluster(user_id="user-456")

        headers = mock_client.get.call_args.kwargs["headers"]
        # Both headers must be present simultaneously
        assert "X-User-ID" in headers, "X-User-ID must not be overwritten"
        assert "X-Internal-Secret" in headers, "X-Internal-Secret must be present"
        assert headers["X-User-ID"] == "user-456"
        assert headers["X-Internal-Secret"] == "secret-key"

    @pytest.mark.asyncio
    async def test_get_cluster_server_error_returns_none(self):
        """Should return None on 500 server error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cluster_unexpected_payload_passes_through(self):
        """Should pass through unexpected JSON shapes (caller handles gracefully).

        Note: This documents current behavior. The MCP layer trusts the backend
        but consumers (get_my_clusters tool) handle missing keys with .get() defaults.
        If stricter validation is needed, add it to persistence.py and update this test.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpected": "shape"}  # Missing expected keys

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        # Currently passes through as-is (no validation at persistence layer)
        assert result == {"unexpected": "shape"}
        # Consumer must handle missing keys gracefully

    @pytest.mark.asyncio
    async def test_get_cluster_invalid_json_returns_none(self):
        """Should return None when backend returns invalid JSON (e.g., HTML error page).

        This locks in the 'never crash MCP on backend weirdness' guarantee.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cluster_none_user_id_returns_none(self):
        """Should return None when user_id is None (defensive boundary test).

        Documents behavior: sends X-User-ID: None header, backend returns 401,
        function returns None without crashing. Type hint says str but we handle
        None gracefully at the boundary.
        """
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id=None)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cluster_empty_user_id_returns_none(self):
        """Should return None when user_id is empty string (defensive boundary test).

        Documents behavior: sends X-User-ID: '' header, backend returns 401,
        function returns None without crashing.
        """
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cluster_timeout_returns_none(self):
        """Timeout exceptions must return None, not crash.

        Explicitly locks timeout behavior separate from generic exceptions.
        Clarifies that httpx.TimeoutException is handled gracefully.

        This is critical for MCP reliability - slow backends must not hang.
        """
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Request timed out"))

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_cluster_non_dict_json_returns_none(self):
        """Non-dict JSON responses (string, int, array) must return None.

        Guards against:
        - Misconfigured reverse proxies returning string messages
        - Backend bugs returning primitive values
        - Truthy non-dict payloads like "OK" or 1

        Only dict responses are valid for cluster data.
        """
        # Test string response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = "OK"  # String, not dict

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        assert result is None, "String response must be rejected"

    @pytest.mark.asyncio
    async def test_get_cluster_integer_json_returns_none(self):
        """Integer JSON response must return None.

        Edge case where backend returns a count or ID instead of object.
        """
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = 42  # Integer, not dict

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("mcp_server.clarity.persistence.get_http_client", return_value=mock_client):
            result = await get_cluster(user_id="user-456")

        assert result is None, "Integer response must be rejected"
