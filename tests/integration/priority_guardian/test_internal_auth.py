"""
Integration tests for internal API secret enforcement on Priority Guardian routers.

Tests that PG endpoints properly enforce X-Internal-Secret header
in production mode and skip verification in dev mode.
"""

import pytest
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreUser


class TestInternalSecretProduction:
    """Tests for production mode (INTERNAL_API_SECRET is set)."""

    @pytest.fixture
    async def test_user(self, async_session: AsyncSession) -> CoreUser:
        """Create a test user for 200 path tests."""
        user = CoreUser(
            id=uuid4(),
            chatgpt_user_id=f"test_chatgpt_{uuid4().hex[:8]}",
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    # =========================================================================
    # 403 Rejection Tests - No DB fixtures needed
    # =========================================================================

    @pytest.mark.asyncio
    async def test_priorities_missing_internal_secret_returns_403(self, client):
        """GET /priorities without X-Internal-Secret returns 403 in production mode."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.get(
                "/api/priority-guardian/priorities",
                headers={"X-User-ID": str(uuid4())},
                # No X-Internal-Secret header
            )

        assert response.status_code == 403
        body = response.json()
        assert body["detail"] == "Forbidden"
        assert "production-secret" not in str(body)

    @pytest.mark.asyncio
    async def test_priorities_wrong_internal_secret_returns_403(self, client):
        """GET /priorities with wrong X-Internal-Secret returns 403."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.get(
                "/api/priority-guardian/priorities",
                headers={
                    "X-User-ID": str(uuid4()),
                    "X-Internal-Secret": "wrong-secret",
                },
            )

        assert response.status_code == 403
        body = response.json()
        assert body["detail"] == "Forbidden"
        assert "wrong-secret" not in str(body)
        assert "production-secret" not in str(body)

    @pytest.mark.asyncio
    async def test_post_priorities_missing_internal_secret_returns_403(self, client):
        """POST /priorities without X-Internal-Secret returns 403."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.post(
                "/api/priority-guardian/priorities",
                headers={"X-User-ID": str(uuid4())},
                json={"name": "Test Priority", "type": "deadline"},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_calendar_missing_internal_secret_returns_403(self, client):
        """GET /calendar/time-allocation without X-Internal-Secret returns 403."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.get(
                "/api/priority-guardian/calendar/time-allocation",
                headers={"X-User-ID": str(uuid4())},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_disconnect_missing_internal_secret_returns_403(self, client):
        """POST /disconnect without X-Internal-Secret returns 403."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.post(
                "/api/priority-guardian/disconnect",
                headers={"X-User-ID": str(uuid4())},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_weekly_report_missing_internal_secret_returns_403(self, client):
        """GET /weekly-report without X-Internal-Secret returns 403."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.get(
                "/api/priority-guardian/weekly-report",
                headers={"X-User-ID": str(uuid4())},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_patterns_missing_internal_secret_returns_403(self, client):
        """GET /patterns without X-Internal-Secret returns 403."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.get(
                "/api/priority-guardian/patterns",
                headers={"X-User-ID": str(uuid4())},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_snapshots_missing_internal_secret_returns_403(self, client):
        """POST /snapshots/ensure without X-Internal-Secret returns 403."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.post(
                "/api/priority-guardian/snapshots/ensure",
                headers={"X-User-ID": str(uuid4())},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_connection_status_missing_internal_secret_returns_403(self, client):
        """GET /google/connection-status without X-Internal-Secret returns 403."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.get(
                "/api/priority-guardian/google/connection-status",
                headers={"X-User-ID": str(uuid4())},
            )

        assert response.status_code == 403
        assert response.json()["detail"] == "Forbidden"

    # =========================================================================
    # Dependency Ordering Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_correct_secret_missing_user_id_returns_401(self, client):
        """Correct X-Internal-Secret but missing X-User-ID returns 401.

        Verifies dependency ordering: verify_internal_call runs first and passes,
        then validate_user_id_header rejects with 401. If someone reorders the
        router dependencies, this test catches it.
        """
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.get(
                "/api/priority-guardian/priorities",
                headers={
                    "X-Internal-Secret": "production-secret",
                    # No X-User-ID header
                },
            )

        assert response.status_code == 401
        body = response.json()
        assert body["detail"]["code"] == "UNAUTHORIZED"

    # =========================================================================
    # Health Endpoint - Must remain unauthenticated
    # =========================================================================

    @pytest.mark.asyncio
    async def test_health_accessible_without_internal_secret(self, client):
        """GET /health remains accessible without X-Internal-Secret."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.get("/api/priority-guardian/health")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "ok"

    # =========================================================================
    # 200 Path Tests - Require test user
    # =========================================================================

    @pytest.mark.asyncio
    async def test_priorities_correct_internal_secret_returns_200(self, client, test_user):
        """GET /priorities with correct X-Internal-Secret returns 200."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.get(
                "/api/priority-guardian/priorities",
                headers={
                    "X-User-ID": str(test_user.id),
                    "X-Internal-Secret": "production-secret",
                },
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "priorities" in body["data"]


class TestInternalSecretDevMode:
    """Tests for dev mode (INTERNAL_API_SECRET is empty)."""

    @pytest.fixture
    async def test_user(self, async_session: AsyncSession) -> CoreUser:
        """Create a test user."""
        user = CoreUser(
            id=uuid4(),
            chatgpt_user_id=f"test_chatgpt_{uuid4().hex[:8]}",
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    @pytest.mark.asyncio
    async def test_priorities_accessible_without_internal_secret_in_dev(self, client, test_user):
        """GET /priorities works without X-Internal-Secret in dev mode."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", ""):
            response = await client.get(
                "/api/priority-guardian/priorities",
                headers={"X-User-ID": str(test_user.id)},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True


class TestRouterLevelProtection:
    """Tests verifying router-level enforcement (all endpoints protected automatically)."""

    @pytest.mark.asyncio
    async def test_all_protected_routers_reject_without_secret(self, client):
        """All protected routers reject requests without X-Internal-Secret.

        This test ensures router-level dependencies are applied, meaning
        any new endpoint added to these routers will be automatically protected.
        """
        protected_endpoints = [
            ("GET", "/api/priority-guardian/priorities"),
            ("POST", "/api/priority-guardian/priorities"),
            ("GET", "/api/priority-guardian/calendar/time-allocation"),
            ("POST", "/api/priority-guardian/snapshots/ensure"),
            ("GET", "/api/priority-guardian/weekly-report"),
            ("GET", "/api/priority-guardian/patterns"),
            ("POST", "/api/priority-guardian/disconnect"),
            ("GET", "/api/priority-guardian/google/connection-status"),
        ]

        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            for method, path in protected_endpoints:
                headers = {"X-User-ID": str(uuid4())}

                if method == "GET":
                    response = await client.get(path, headers=headers)
                elif method == "POST":
                    response = await client.post(path, headers=headers, json={})

                assert response.status_code == 403, f"{method} {path} should return 403"
                assert response.json()["detail"] == "Forbidden"
