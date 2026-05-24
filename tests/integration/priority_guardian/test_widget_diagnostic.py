"""
Widget Diagnostic Endpoint Integration Tests (Inc 89).

Tests:
- POST with valid payload returns 204
- POST with data > 2048 bytes returns 413
- POST with data exactly 2048 bytes succeeds (boundary)
- POST with missing event field returns 422
- POST with event field > 100 chars returns 422
- CORS preflight returns proper headers
"""

import pytest
from httpx import AsyncClient


class TestWidgetDiagnosticEndpoint:
    """Test widget-diagnostic endpoint."""

    @pytest.mark.asyncio
    async def test_valid_payload_returns_204(self, client: AsyncClient):
        """POST with valid payload returns 204 No Content."""
        response = await client.post(
            "/api/priority-guardian/widget-diagnostic",
            json={
                "event": "mount",
                "data": {"sid": "test-123", "initialDisplayMode": "inline"},
                "ts": 1716566400000,
                "ua": "Mozilla/5.0 (test)",
            },
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_minimal_payload_returns_204(self, client: AsyncClient):
        """POST with only required field returns 204."""
        response = await client.post(
            "/api/priority-guardian/widget-diagnostic",
            json={"event": "mount"},
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_data_exceeds_2048_bytes_returns_413(self, client: AsyncClient):
        """POST with data field > 2048 bytes returns 413 Payload Too Large."""
        # Create a data object that serializes to more than 2048 bytes
        large_data = {"key": "x" * 3000}

        response = await client.post(
            "/api/priority-guardian/widget-diagnostic",
            json={
                "event": "test",
                "data": large_data,
            },
        )

        assert response.status_code == 413
        assert "2048 bytes" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_data_exactly_2048_bytes_succeeds(self, client: AsyncClient):
        """POST with data field exactly 2048 bytes succeeds (boundary test)."""
        # {"key":"x...x"} with JSON separators is {"key":"..."}
        # The key name is 3 chars, quotes add 4 chars, colon adds 1 = 8 overhead + braces = 10
        # So we need 2048 - 10 = 2038 chars for the value
        value = "x" * 2038

        response = await client.post(
            "/api/priority-guardian/widget-diagnostic",
            json={
                "event": "test",
                "data": {"key": value},
            },
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_missing_event_returns_422(self, client: AsyncClient):
        """POST with missing event field returns 422 validation error."""
        response = await client.post(
            "/api/priority-guardian/widget-diagnostic",
            json={"data": {"foo": "bar"}},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_event_exceeds_100_chars_returns_422(self, client: AsyncClient):
        """POST with event field > 100 chars returns 422."""
        response = await client.post(
            "/api/priority-guardian/widget-diagnostic",
            json={"event": "x" * 101},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_event_exactly_100_chars_succeeds(self, client: AsyncClient):
        """POST with event field exactly 100 chars succeeds (boundary)."""
        response = await client.post(
            "/api/priority-guardian/widget-diagnostic",
            json={"event": "x" * 100},
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_empty_event_returns_422(self, client: AsyncClient):
        """POST with empty event field returns 422."""
        response = await client.post(
            "/api/priority-guardian/widget-diagnostic",
            json={"event": ""},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_ua_exceeds_500_chars_returns_422(self, client: AsyncClient):
        """POST with ua field > 500 chars returns 422."""
        response = await client.post(
            "/api/priority-guardian/widget-diagnostic",
            json={
                "event": "test",
                "ua": "x" * 501,
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_cors_preflight_returns_204(self, client: AsyncClient):
        """OPTIONS preflight request returns 204 with CORS headers."""
        response = await client.options(
            "/api/priority-guardian/widget-diagnostic",
        )

        assert response.status_code == 204
        assert response.headers.get("Access-Control-Allow-Origin") == "*"
        assert "POST" in response.headers.get("Access-Control-Allow-Methods", "")
        assert "Content-Type" in response.headers.get("Access-Control-Allow-Headers", "")

    @pytest.mark.asyncio
    async def test_post_returns_cors_headers(self, client: AsyncClient):
        """POST response includes CORS headers."""
        response = await client.post(
            "/api/priority-guardian/widget-diagnostic",
            json={"event": "test"},
        )

        assert response.headers.get("Access-Control-Allow-Origin") == "*"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
