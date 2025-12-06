"""
Unit tests for OAuth session cookie utilities (Increment 19).

Tests cookie configuration and security attributes.
"""

import pytest
from unittest.mock import MagicMock, patch

from backend.core.oauth_provider.cookies import (
    COOKIE_NAME,
    COOKIE_MAX_AGE,
    COOKIE_PATH,
    get_session_cookie,
    set_session_cookie,
    delete_session_cookie,
)


class TestCookieConstants:
    """Tests for cookie configuration constants."""

    def test_cookie_name(self):
        """Cookie name must be pg_session."""
        assert COOKIE_NAME == "pg_session"

    def test_cookie_max_age_is_two_years(self):
        """Cookie max_age must be 2 years (63072000 seconds)."""
        two_years_seconds = 2 * 365 * 24 * 60 * 60
        assert COOKIE_MAX_AGE == two_years_seconds
        assert COOKIE_MAX_AGE == 63072000

    def test_cookie_path_is_oauth(self):
        """Cookie path must be /oauth."""
        assert COOKIE_PATH == "/oauth"


class TestGetSessionCookie:
    """Tests for reading session cookie from request."""

    def test_returns_cookie_value_when_present(self):
        """get_session_cookie should return cookie value if present."""
        mock_request = MagicMock()
        mock_request.cookies = {COOKIE_NAME: "test_token_value"}

        result = get_session_cookie(mock_request)

        assert result == "test_token_value"

    def test_returns_none_when_cookie_missing(self):
        """get_session_cookie should return None if cookie not present."""
        mock_request = MagicMock()
        mock_request.cookies = {}

        result = get_session_cookie(mock_request)

        assert result is None


class TestSetSessionCookie:
    """Tests for setting session cookie on response."""

    def test_sets_cookie_with_correct_name_and_value(self):
        """set_session_cookie should set cookie with correct name and value."""
        mock_response = MagicMock()

        set_session_cookie(mock_response, "my_token_123")

        mock_response.set_cookie.assert_called_once()
        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["key"] == COOKIE_NAME
        assert call_kwargs["value"] == "my_token_123"

    def test_sets_httponly_flag(self):
        """set_session_cookie should always set HttpOnly flag."""
        mock_response = MagicMock()

        set_session_cookie(mock_response, "token")

        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["httponly"] is True

    def test_sets_samesite_lax(self):
        """set_session_cookie should set SameSite=lax."""
        mock_response = MagicMock()

        set_session_cookie(mock_response, "token")

        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["samesite"] == "lax"

    def test_sets_correct_path(self):
        """set_session_cookie should set Path=/oauth."""
        mock_response = MagicMock()

        set_session_cookie(mock_response, "token")

        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["path"] == COOKIE_PATH

    def test_sets_correct_max_age(self):
        """set_session_cookie should set Max-Age to 2 years."""
        mock_response = MagicMock()

        set_session_cookie(mock_response, "token")

        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["max_age"] == COOKIE_MAX_AGE

    @patch("backend.core.oauth_provider.cookies.settings")
    def test_sets_secure_in_production(self, mock_settings):
        """set_session_cookie should set Secure flag when ENV != 'dev'."""
        mock_settings.ENV = "production"
        mock_response = MagicMock()

        set_session_cookie(mock_response, "token")

        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["secure"] is True

    @patch("backend.core.oauth_provider.cookies.settings")
    def test_no_secure_in_dev(self, mock_settings):
        """set_session_cookie should NOT set Secure flag when ENV == 'dev'."""
        mock_settings.ENV = "dev"
        mock_response = MagicMock()

        set_session_cookie(mock_response, "token")

        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["secure"] is False


class TestDeleteSessionCookie:
    """Tests for deleting session cookie.

    Note: Uses set_cookie with max_age=0 instead of delete_cookie
    because delete_cookie doesn't accept security attributes.
    """

    def test_deletes_cookie_with_correct_key(self):
        """delete_session_cookie should set cookie with correct key."""
        mock_response = MagicMock()

        delete_session_cookie(mock_response)

        mock_response.set_cookie.assert_called_once()
        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["key"] == COOKIE_NAME

    def test_deletes_with_empty_value_and_zero_max_age(self):
        """delete_session_cookie should set empty value with max_age=0."""
        mock_response = MagicMock()

        delete_session_cookie(mock_response)

        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["value"] == ""
        assert call_kwargs["max_age"] == 0
        assert call_kwargs["expires"] == 0

    def test_deletes_with_correct_path(self):
        """delete_session_cookie should use correct path."""
        mock_response = MagicMock()

        delete_session_cookie(mock_response)

        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["path"] == COOKIE_PATH

    def test_deletes_with_httponly_flag(self):
        """delete_session_cookie should preserve HttpOnly flag."""
        mock_response = MagicMock()

        delete_session_cookie(mock_response)

        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["httponly"] is True

    def test_deletes_with_samesite_lax(self):
        """delete_session_cookie should preserve SameSite=lax."""
        mock_response = MagicMock()

        delete_session_cookie(mock_response)

        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["samesite"] == "lax"

    @patch("backend.core.oauth_provider.cookies.settings")
    def test_deletes_with_secure_in_production(self, mock_settings):
        """delete_session_cookie should use Secure flag in production."""
        mock_settings.ENV = "production"
        mock_response = MagicMock()

        delete_session_cookie(mock_response)

        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["secure"] is True

    @patch("backend.core.oauth_provider.cookies.settings")
    def test_deletes_without_secure_in_dev(self, mock_settings):
        """delete_session_cookie should NOT use Secure flag in dev."""
        mock_settings.ENV = "dev"
        mock_response = MagicMock()

        delete_session_cookie(mock_response)

        call_kwargs = mock_response.set_cookie.call_args[1]
        assert call_kwargs["secure"] is False
