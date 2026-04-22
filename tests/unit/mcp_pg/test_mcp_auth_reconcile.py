"""
Unit tests for mcp_auth.py reconciliation integration (Increment 78).

Tests the reconcile_user_via_backend function and its integration
with authenticate_request.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

import httpx

from mcp_server.priority_guardian.mcp_auth import (
    reconcile_user_via_backend,
    authenticate_request,
)


# =============================================================================
# reconcile_user_via_backend Tests
# =============================================================================

@pytest.mark.asyncio
async def test_reconcile_user_via_backend_returns_canonical_user_id():
    """When backend returns success, return the canonical user_id."""
    jwt_user_id = str(uuid4())
    canonical_user_id = str(uuid4())
    subject = "v1/test-subject"
    correlation_id = "test-corr-id"

    mock_response = {"user_id": canonical_user_id, "case": "C1"}

    with patch(
        "mcp_server.priority_guardian.http_client.reconcile_user",
        new_callable=AsyncMock,
        return_value=mock_response,
    ) as mock_reconcile:
        result = await reconcile_user_via_backend(
            jwt_user_id=jwt_user_id,
            meta={"openai/subject": subject},
            correlation_id=correlation_id,
        )

        assert result == canonical_user_id
        mock_reconcile.assert_called_once_with(jwt_user_id, subject, correlation_id)


@pytest.mark.asyncio
async def test_reconcile_user_via_backend_skips_when_subject_absent():
    """When openai/subject is absent, return jwt_user_id unchanged."""
    jwt_user_id = str(uuid4())
    correlation_id = "test-corr-id"

    with patch(
        "mcp_server.priority_guardian.http_client.reconcile_user",
        new_callable=AsyncMock,
    ) as mock_reconcile:
        # No openai/subject in meta
        result = await reconcile_user_via_backend(
            jwt_user_id=jwt_user_id,
            meta={},
            correlation_id=correlation_id,
        )

        assert result == jwt_user_id
        mock_reconcile.assert_not_called()

        # meta is None
        result = await reconcile_user_via_backend(
            jwt_user_id=jwt_user_id,
            meta=None,
            correlation_id=correlation_id,
        )

        assert result == jwt_user_id
        mock_reconcile.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_user_via_backend_graceful_degrade_on_connect_error():
    """When backend raises httpx.ConnectError, return jwt_user_id unchanged (do not raise)."""
    jwt_user_id = str(uuid4())
    subject = "v1/test-subject"
    correlation_id = "test-corr-id"

    with patch(
        "mcp_server.priority_guardian.http_client.reconcile_user",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("Connection refused"),
    ):
        result = await reconcile_user_via_backend(
            jwt_user_id=jwt_user_id,
            meta={"openai/subject": subject},
            correlation_id=correlation_id,
        )

        # Should return jwt_user_id, not raise
        assert result == jwt_user_id


@pytest.mark.asyncio
async def test_reconcile_user_via_backend_graceful_degrade_on_timeout():
    """When backend raises httpx.TimeoutException, return jwt_user_id unchanged (do not raise)."""
    jwt_user_id = str(uuid4())
    subject = "v1/test-subject"
    correlation_id = "test-corr-id"

    with patch(
        "mcp_server.priority_guardian.http_client.reconcile_user",
        new_callable=AsyncMock,
        side_effect=httpx.TimeoutException("Request timed out"),
    ):
        result = await reconcile_user_via_backend(
            jwt_user_id=jwt_user_id,
            meta={"openai/subject": subject},
            correlation_id=correlation_id,
        )

        # Should return jwt_user_id, not raise
        assert result == jwt_user_id


@pytest.mark.asyncio
async def test_reconcile_user_via_backend_graceful_degrade_on_http_status_error():
    """When backend returns 5xx, return jwt_user_id unchanged (do not raise)."""
    jwt_user_id = str(uuid4())
    subject = "v1/test-subject"
    correlation_id = "test-corr-id"

    mock_request = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 500

    with patch(
        "mcp_server.priority_guardian.http_client.reconcile_user",
        new_callable=AsyncMock,
        side_effect=httpx.HTTPStatusError("Server error", request=mock_request, response=mock_response),
    ):
        result = await reconcile_user_via_backend(
            jwt_user_id=jwt_user_id,
            meta={"openai/subject": subject},
            correlation_id=correlation_id,
        )

        # Should return jwt_user_id, not raise
        assert result == jwt_user_id


# =============================================================================
# authenticate_request Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_authenticate_request_calls_reconcile_when_subject_present():
    """
    Mock reconcile_user to return {"user_id": "canonical-uuid", "case": "C1"}.
    Verify auth_context["user_id"] is "canonical-uuid".
    """
    jwt_user_id = str(uuid4())
    canonical_user_id = str(uuid4())
    subject = "v1/test-subject"

    # Mock all the dependencies
    with patch(
        "mcp_server.priority_guardian.mcp_auth.auth_header_var"
    ) as mock_auth_header_var, patch(
        "mcp_server.priority_guardian.mcp_auth.validate_jwt",
        new_callable=AsyncMock,
        return_value={
            "user_id": jwt_user_id,
            "scopes": {"pg.access"},
            "jti": "test-jti",
            "azp": "test-azp",
            "claims": {},
        },
    ), patch(
        "mcp_server.priority_guardian.mcp_auth.reconcile_user_via_backend",
        new_callable=AsyncMock,
        return_value=canonical_user_id,
    ) as mock_reconcile, patch(
        "mcp_server.priority_guardian.mcp_auth.enforce_tool_scope"
    ):
        mock_auth_header_var.get.return_value = "Bearer test-token"

        meta_passed = {"openai/subject": subject}
        result = await authenticate_request(
            tool_name="get_priorities",
            meta=meta_passed,
        )

        assert result["user_id"] == canonical_user_id

        # Assert exact call args, not just call count, so a refactor that passes
        # wrong args (e.g., subject directly instead of meta dict) fails loudly.
        mock_reconcile.assert_called_once()
        call_args = mock_reconcile.call_args
        # authenticate_request signature: reconcile_user_via_backend(jwt_user_id, meta, correlation_id)
        assert call_args.args[0] == jwt_user_id, f"Expected jwt_user_id as first arg, got {call_args.args[0]}"
        assert call_args.args[1] == meta_passed, f"Expected meta dict as second arg, got {call_args.args[1]}"
        # correlation_id is generated inside authenticate_request; just verify it's a non-empty string
        assert isinstance(call_args.args[2], str) and call_args.args[2], (
            f"Expected non-empty correlation_id string as third arg, got {call_args.args[2]!r}"
        )


@pytest.mark.asyncio
async def test_authenticate_request_falls_back_to_jwt_user_id_when_subject_absent():
    """
    When meta has no openai/subject, authenticate_request still invokes
    reconcile_user_via_backend — the skip happens INSIDE that helper, which
    short-circuits and returns jwt_user_id without making a backend call.

    This test pins the outer behavior: auth_context["user_id"] == jwt_user_id.
    The inner skip (http_client.reconcile_user not called) is pinned separately
    in test_reconcile_user_via_backend_skips_when_subject_absent.
    """
    jwt_user_id = str(uuid4())

    with patch(
        "mcp_server.priority_guardian.mcp_auth.auth_header_var"
    ) as mock_auth_header_var, patch(
        "mcp_server.priority_guardian.mcp_auth.validate_jwt",
        new_callable=AsyncMock,
        return_value={
            "user_id": jwt_user_id,
            "scopes": {"pg.access"},
            "jti": "test-jti",
            "azp": "test-azp",
            "claims": {},
        },
    ), patch(
        "mcp_server.priority_guardian.mcp_auth.reconcile_user_via_backend",
        new_callable=AsyncMock,
        return_value=jwt_user_id,  # Falls back to jwt_user_id when no subject
    ) as mock_reconcile, patch(
        "mcp_server.priority_guardian.mcp_auth.enforce_tool_scope"
    ):
        mock_auth_header_var.get.return_value = "Bearer test-token"

        result = await authenticate_request(
            tool_name="get_priorities",
            meta={},  # No openai/subject
        )

        assert result["user_id"] == jwt_user_id
        # reconcile_user_via_backend is still called; the skip happens inside it
        mock_reconcile.assert_called_once()


@pytest.mark.asyncio
async def test_authenticate_request_graceful_degrade_on_backend_failure():
    """
    Inject httpx.ConnectError at the http_client.reconcile_user layer.
    Verify auth_context["user_id"] is the JWT sub (graceful fallback).

    This tests the full graceful degradation path: http_client fails →
    reconcile_user_via_backend catches it → returns jwt_user_id →
    authenticate_request uses that fallback value.
    """
    jwt_user_id = str(uuid4())

    with patch(
        "mcp_server.priority_guardian.mcp_auth.auth_header_var"
    ) as mock_auth_header_var, patch(
        "mcp_server.priority_guardian.mcp_auth.validate_jwt",
        new_callable=AsyncMock,
        return_value={
            "user_id": jwt_user_id,
            "scopes": {"pg.access"},
            "jti": "test-jti",
            "azp": "test-azp",
            "claims": {},
        },
    ), patch(
        # Inject failure at the http_client layer, not at reconcile_user_via_backend
        "mcp_server.priority_guardian.http_client.reconcile_user",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("Connection refused"),
    ), patch(
        "mcp_server.priority_guardian.mcp_auth.enforce_tool_scope"
    ):
        mock_auth_header_var.get.return_value = "Bearer test-token"

        result = await authenticate_request(
            tool_name="get_priorities",
            meta={"openai/subject": "v1/test-subject"},
        )

        # Should use jwt_user_id (graceful fallback from reconcile_user_via_backend)
        assert result["user_id"] == jwt_user_id
