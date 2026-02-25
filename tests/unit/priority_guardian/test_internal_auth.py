"""
Unit tests for verify_internal_call dependency.

Tests the internal API secret verification for PG router protection.
"""

import pytest
from unittest.mock import patch
from fastapi import HTTPException

from backend.core.dependencies import verify_internal_call


class TestVerifyInternalCallProductionMode:
    """Tests for production mode (INTERNAL_API_SECRET is set)."""

    def test_missing_header_raises_403(self):
        """Missing X-Internal-Secret header raises 403 in production mode."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            with pytest.raises(HTTPException) as exc_info:
                verify_internal_call(x_internal_secret=None)

            assert exc_info.value.status_code == 403
            assert exc_info.value.detail == "Forbidden"

    def test_wrong_header_raises_403(self):
        """Wrong X-Internal-Secret header raises 403 in production mode."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            with pytest.raises(HTTPException) as exc_info:
                verify_internal_call(x_internal_secret="wrong-secret")

            assert exc_info.value.status_code == 403
            assert exc_info.value.detail == "Forbidden"

    def test_correct_header_passes(self):
        """Correct X-Internal-Secret header passes in production mode."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            # Should not raise
            result = verify_internal_call(x_internal_secret="production-secret")
            assert result is None

    def test_403_response_never_reveals_secret(self):
        """403 response body never contains the actual or attempted secret."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            with pytest.raises(HTTPException) as exc_info:
                verify_internal_call(x_internal_secret="attempted-secret")

            error_str = str(exc_info.value.detail)
            # Never reveal expected secret
            assert "production-secret" not in error_str
            # Never echo back attempted secret
            assert "attempted-secret" not in error_str
            # Generic message only
            assert exc_info.value.detail == "Forbidden"

    def test_empty_string_header_raises_403(self):
        """Empty string header raises 403 in production mode."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            with pytest.raises(HTTPException) as exc_info:
                verify_internal_call(x_internal_secret="")

            assert exc_info.value.status_code == 403


class TestVerifyInternalCallDevMode:
    """Tests for dev mode (INTERNAL_API_SECRET is empty)."""

    def test_empty_secret_skips_verification(self):
        """Empty INTERNAL_API_SECRET skips verification (dev mode)."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", ""):
            # Should not raise with missing header
            result = verify_internal_call(x_internal_secret=None)
            assert result is None

    def test_dev_mode_accepts_any_header(self):
        """Dev mode accepts any header value without error."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", ""):
            # Should not raise with any value
            result = verify_internal_call(x_internal_secret="any-value")
            assert result is None

    def test_dev_mode_accepts_empty_string_header(self):
        """Dev mode accepts empty string header without error."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", ""):
            result = verify_internal_call(x_internal_secret="")
            assert result is None
