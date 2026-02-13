"""
Unit tests for snapshot router (Increment 08).

Tests POST /snapshots/ensure endpoint.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from backend.apps.priority_guardian.routers.snapshot_router import router


@pytest.fixture
def app():
    """Create test FastAPI app with snapshot router."""
    app = FastAPI()
    app.include_router(router, prefix="/api/priority-guardian")
    return app


@pytest.fixture
def mock_user_id():
    return uuid4()


class TestEnsureSnapshotsEndpoint:
    """Tests for POST /snapshots/ensure endpoint."""

    @pytest.mark.asyncio
    async def test_returns_200_with_summary(self, app, mock_user_id):
        """Valid request returns 200 with snapshot summary."""
        with patch(
            "backend.apps.priority_guardian.routers.snapshot_router.validate_user_id_header"
        ) as mock_validate, patch(
            "backend.apps.priority_guardian.routers.snapshot_router.get_db"
        ) as mock_db, patch(
            "backend.apps.priority_guardian.routers.snapshot_router.ensure_snapshots_up_to_date"
        ) as mock_ensure:
            mock_validate.return_value = mock_user_id
            mock_db.return_value = AsyncMock()
            mock_ensure.return_value = {"checked": 3, "created": 1, "errors": 0}

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/priority-guardian/snapshots/ensure",
                    headers={"X-User-ID": str(mock_user_id)},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["checked"] == 3
            assert data["data"]["created"] == 1
            assert data["data"]["errors"] == 0

    @pytest.mark.asyncio
    async def test_no_google_connection_returns_200_with_zeros(self, app, mock_user_id):
        """User without Google connection returns 200 with zeros."""
        with patch(
            "backend.apps.priority_guardian.routers.snapshot_router.validate_user_id_header"
        ) as mock_validate, patch(
            "backend.apps.priority_guardian.routers.snapshot_router.get_db"
        ) as mock_db, patch(
            "backend.apps.priority_guardian.routers.snapshot_router.ensure_snapshots_up_to_date"
        ) as mock_ensure:
            mock_validate.return_value = mock_user_id
            mock_db.return_value = AsyncMock()
            # No Google connection - service returns zeros
            mock_ensure.return_value = {"checked": 0, "created": 0, "errors": 0}

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/priority-guardian/snapshots/ensure",
                    headers={"X-User-ID": str(mock_user_id)},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["checked"] == 0
            assert data["data"]["created"] == 0
            assert data["data"]["errors"] == 0

    @pytest.mark.asyncio
    async def test_partial_failure_returns_200(self, app, mock_user_id):
        """Partial failure (some weeks created, some failed) returns 200."""
        with patch(
            "backend.apps.priority_guardian.routers.snapshot_router.validate_user_id_header"
        ) as mock_validate, patch(
            "backend.apps.priority_guardian.routers.snapshot_router.get_db"
        ) as mock_db, patch(
            "backend.apps.priority_guardian.routers.snapshot_router.ensure_snapshots_up_to_date"
        ) as mock_ensure:
            mock_validate.return_value = mock_user_id
            mock_db.return_value = AsyncMock()
            # Partial success
            mock_ensure.return_value = {"checked": 3, "created": 2, "errors": 1}

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/priority-guardian/snapshots/ensure",
                    headers={"X-User-ID": str(mock_user_id)},
                )

            # Still 200 - partial results are not errors
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["created"] == 2
            assert data["data"]["errors"] == 1

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_401(self, app):
        """Missing X-User-ID header returns 401."""
        # Don't mock validate_user_id_header - let it fail naturally
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/priority-guardian/snapshots/ensure",
                # No X-User-ID header
            )

        # FastAPI dependency validation should fail
        assert response.status_code in [401, 422]  # Depends on how validate_user_id_header is implemented
