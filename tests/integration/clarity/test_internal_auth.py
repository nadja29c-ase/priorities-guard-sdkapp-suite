"""
Integration tests for internal API secret enforcement.

Tests that persistence endpoints properly enforce X-Internal-Secret header
in production mode and skip verification in dev mode.
"""

import pytest
import pytest_asyncio
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreUser


class TestInternalSecretProduction:
    """Tests for production mode (INTERNAL_API_SECRET is set)."""

    @pytest.fixture
    async def test_user(self, async_session: AsyncSession) -> CoreUser:
        """Create a test user for persistence tests."""
        user = CoreUser(
            id=uuid4(),
            chatgpt_user_id=f"test_chatgpt_{uuid4().hex[:8]}",
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    @pytest.fixture
    def valid_payload(self):
        """Valid cluster payload for testing."""
        return {
            "cluster_data": {
                "clusters": [
                    {
                        "cluster_name": "Test Cluster",
                        "thought_items": ["item1"],
                        "subclusters": [],
                        "tags": [],
                    }
                ]
            },
            "thoughts_exhausted": True,
            "correctly_clustered": None,
        }

    @pytest.mark.asyncio
    async def test_missing_internal_secret_returns_403(self, client, test_user, valid_payload):
        """In production mode, missing X-Internal-Secret returns 403."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.post(
                "/api/clarity/clusters",
                headers={"X-User-ID": str(test_user.id)},
                # No X-Internal-Secret header
                json=valid_payload,
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_wrong_internal_secret_returns_403(self, client, test_user, valid_payload):
        """In production mode, wrong X-Internal-Secret returns 403."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.post(
                "/api/clarity/clusters",
                headers={
                    "X-User-ID": str(test_user.id),
                    "X-Internal-Secret": "wrong-secret",
                },
                json=valid_payload,
            )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_correct_internal_secret_returns_201(self, client, test_user, valid_payload):
        """In production mode, correct X-Internal-Secret allows request."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", "production-secret"):
            response = await client.post(
                "/api/clarity/clusters",
                headers={
                    "X-User-ID": str(test_user.id),
                    "X-Internal-Secret": "production-secret",
                },
                json=valid_payload,
            )

        assert response.status_code == 201
        assert "cluster_id" in response.json()


class TestInternalSecretDevMode:
    """Tests for dev mode (INTERNAL_API_SECRET is empty)."""

    @pytest.fixture
    async def test_user(self, async_session: AsyncSession) -> CoreUser:
        """Create a test user for persistence tests."""
        user = CoreUser(
            id=uuid4(),
            chatgpt_user_id=f"test_chatgpt_{uuid4().hex[:8]}",
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    @pytest.fixture
    def valid_payload(self):
        """Valid cluster payload for testing."""
        return {
            "cluster_data": {
                "clusters": [
                    {
                        "cluster_name": "Test Cluster",
                        "thought_items": ["item1"],
                        "subclusters": [],
                        "tags": [],
                    }
                ]
            },
            "thoughts_exhausted": True,
            "correctly_clustered": None,
        }

    @pytest.mark.asyncio
    async def test_empty_secret_skips_verification(self, client, test_user, valid_payload):
        """In dev mode (empty secret), no X-Internal-Secret header required."""
        with patch("backend.core.config.settings.INTERNAL_API_SECRET", ""):
            response = await client.post(
                "/api/clarity/clusters",
                headers={"X-User-ID": str(test_user.id)},
                # No X-Internal-Secret header - should still work in dev mode
                json=valid_payload,
            )

        assert response.status_code == 201
        assert "cluster_id" in response.json()
