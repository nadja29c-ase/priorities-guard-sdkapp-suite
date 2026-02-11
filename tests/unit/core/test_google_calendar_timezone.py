"""
Unit tests for get_user_timezone() in google_calendar module.

Tests timezone fetching with various success and failure scenarios.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import httpx

from backend.core.google_calendar import get_user_timezone


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_http_client():
    """Create a mock httpx.AsyncClient."""
    return AsyncMock()


def make_response(status_code: int, json_data: dict | None = None):
    """Create a mock httpx.Response."""
    response = MagicMock()
    response.status_code = status_code
    if json_data is not None:
        response.json.return_value = json_data
    return response


# =============================================================================
# Success Tests
# =============================================================================

class TestTimezoneSuccess:
    """Tests for successful timezone fetch."""

    @pytest.mark.asyncio
    async def test_returns_timezone_on_200(self, mock_http_client):
        """Returns timezone string on successful 200 response."""
        mock_http_client.get.return_value = make_response(
            200, {"value": "Europe/Berlin"}
        )

        result = await get_user_timezone(
            mock_http_client, "access_token_123", "corr-id"
        )

        assert result == "Europe/Berlin"

    @pytest.mark.asyncio
    async def test_returns_america_timezone(self, mock_http_client):
        """Returns American timezone correctly."""
        mock_http_client.get.return_value = make_response(
            200, {"value": "America/New_York"}
        )

        result = await get_user_timezone(mock_http_client, "token", None)

        assert result == "America/New_York"

    @pytest.mark.asyncio
    async def test_returns_utc_timezone(self, mock_http_client):
        """Returns UTC timezone when user has UTC set."""
        mock_http_client.get.return_value = make_response(
            200, {"value": "UTC"}
        )

        result = await get_user_timezone(mock_http_client, "token", None)

        assert result == "UTC"

    @pytest.mark.asyncio
    async def test_calls_correct_endpoint(self, mock_http_client):
        """Calls Google Calendar settings API with correct URL and headers."""
        mock_http_client.get.return_value = make_response(
            200, {"value": "Europe/London"}
        )

        await get_user_timezone(mock_http_client, "my_access_token", "corr-123")

        mock_http_client.get.assert_called_once()
        call_args = mock_http_client.get.call_args

        # Check URL
        assert call_args[0][0] == "https://www.googleapis.com/calendar/v3/users/me/settings/timezone"

        # Check Authorization header
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer my_access_token"


# =============================================================================
# Fallback to UTC Tests
# =============================================================================

class TestTimezoneFallbackToUTC:
    """Tests for fallback to UTC on various error conditions."""

    @pytest.mark.asyncio
    async def test_returns_utc_on_401(self, mock_http_client):
        """Returns UTC fallback on 401 (expired/invalid token)."""
        mock_http_client.get.return_value = make_response(401)

        result = await get_user_timezone(mock_http_client, "bad_token", None)

        assert result == "UTC"

    @pytest.mark.asyncio
    async def test_returns_utc_on_403(self, mock_http_client):
        """Returns UTC fallback on 403 (insufficient scopes)."""
        mock_http_client.get.return_value = make_response(403)

        result = await get_user_timezone(mock_http_client, "token", None)

        assert result == "UTC"

    @pytest.mark.asyncio
    async def test_returns_utc_on_500(self, mock_http_client):
        """Returns UTC fallback on 500 server error."""
        mock_http_client.get.return_value = make_response(500)

        result = await get_user_timezone(mock_http_client, "token", None)

        assert result == "UTC"

    @pytest.mark.asyncio
    async def test_returns_utc_on_timeout(self, mock_http_client):
        """Returns UTC fallback on timeout."""
        mock_http_client.get.side_effect = httpx.TimeoutException("Timeout")

        result = await get_user_timezone(mock_http_client, "token", None)

        assert result == "UTC"

    @pytest.mark.asyncio
    async def test_returns_utc_on_network_error(self, mock_http_client):
        """Returns UTC fallback on network error."""
        mock_http_client.get.side_effect = httpx.NetworkError("Connection failed")

        result = await get_user_timezone(mock_http_client, "token", None)

        assert result == "UTC"

    @pytest.mark.asyncio
    async def test_returns_utc_on_unexpected_exception(self, mock_http_client):
        """Returns UTC fallback on unexpected exception."""
        mock_http_client.get.side_effect = Exception("Unexpected error")

        result = await get_user_timezone(mock_http_client, "token", None)

        assert result == "UTC"

    @pytest.mark.asyncio
    async def test_returns_utc_on_missing_value_field(self, mock_http_client):
        """Returns UTC fallback when response missing 'value' field."""
        mock_http_client.get.return_value = make_response(
            200, {"timezone": "Europe/Berlin"}  # Wrong field name
        )

        result = await get_user_timezone(mock_http_client, "token", None)

        assert result == "UTC"

    @pytest.mark.asyncio
    async def test_returns_utc_on_null_value(self, mock_http_client):
        """Returns UTC fallback when value is null."""
        mock_http_client.get.return_value = make_response(
            200, {"value": None}
        )

        result = await get_user_timezone(mock_http_client, "token", None)

        assert result == "UTC"

    @pytest.mark.asyncio
    async def test_returns_utc_on_empty_value(self, mock_http_client):
        """Returns UTC fallback when value is empty string."""
        mock_http_client.get.return_value = make_response(
            200, {"value": ""}
        )

        result = await get_user_timezone(mock_http_client, "token", None)

        assert result == "UTC"

    @pytest.mark.asyncio
    async def test_returns_utc_on_non_string_value(self, mock_http_client):
        """Returns UTC fallback when value is not a string."""
        mock_http_client.get.return_value = make_response(
            200, {"value": 12345}
        )

        result = await get_user_timezone(mock_http_client, "token", None)

        assert result == "UTC"


# =============================================================================
# Never Raises Tests
# =============================================================================

class TestNeverRaises:
    """Verify function never raises - always returns a string."""

    @pytest.mark.asyncio
    async def test_always_returns_string_on_error(self, mock_http_client):
        """Function always returns a string, never raises."""
        error_scenarios = [
            httpx.TimeoutException("timeout"),
            httpx.NetworkError("network"),
            httpx.ConnectError("connect"),
            Exception("generic"),
            ValueError("value"),
            RuntimeError("runtime"),
        ]

        for error in error_scenarios:
            mock_http_client.get.side_effect = error
            result = await get_user_timezone(mock_http_client, "token", None)
            assert isinstance(result, str)
            assert result == "UTC"
