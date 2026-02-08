"""
Integration tests for Priority Guardian priority creation endpoint.

Tests the full POST /api/priority-guardian/priorities endpoint with test DB.
"""

import pytest
import pytest_asyncio
from datetime import date, timedelta
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.priority_guardian.db_models import PgPriority


class TestCreatePriorityHappyPath:
    """Happy path tests for priority creation."""

    @pytest.mark.asyncio
    async def test_create_deadline_priority_success(self, client, async_session: AsyncSession):
        """POST with valid deadline data returns 201 with correct fields."""
        # Create a test user first
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        response = await client.post(
            "/api/priority-guardian/priorities",
            json={
                "name": "Launch marketing site",
                "type": "deadline",
                "deadline": future_date,
            },
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 201
        data = response.json()

        assert data["success"] is True
        assert "data" in data

        priority = data["data"]["priority"]
        assert priority["name"] == "Launch marketing site"
        assert priority["type"] == "deadline"
        assert priority["calendar_keyword"] == "P1"  # First created gets P1
        assert priority["status"] == "active"
        assert priority["deadline"] == future_date
        assert priority["deliverables"] == []

        assert data["data"]["active_priority_count"] == 1
        assert data["data"]["available_keywords"] == ["P2", "P3"]

    @pytest.mark.asyncio
    async def test_create_flexible_priority_success(self, client, async_session: AsyncSession):
        """POST with valid flexible data returns 201 with all flexible-specific fields."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        response = await client.post(
            "/api/priority-guardian/priorities",
            json={
                "name": "Client outreach",
                "type": "flexible",
                "weekly_hour_target": 10.0,
                "checkpoint_date": future_date,
                "desired_result": "3 new client meetings scheduled",
            },
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 201
        data = response.json()

        assert data["success"] is True
        priority = data["data"]["priority"]

        assert priority["name"] == "Client outreach"
        assert priority["type"] == "flexible"
        assert priority["weekly_hour_target"] == 10.0
        assert priority["checkpoint_date"] == future_date
        assert priority["desired_result"] == "3 new client meetings scheduled"
        assert priority["calendar_keyword"] == "P1"


class TestWhitespaceTrimming:
    """Tests for whitespace trimming in priority fields."""

    @pytest.mark.asyncio
    async def test_name_whitespace_trimmed(self, client, async_session: AsyncSession):
        """Leading/trailing whitespace in name is trimmed in response."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        response = await client.post(
            "/api/priority-guardian/priorities",
            json={
                "name": "  Launch marketing site  ",  # Whitespace padding
                "type": "deadline",
                "deadline": future_date,
            },
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 201
        data = response.json()

        # Whitespace should be trimmed
        assert data["data"]["priority"]["name"] == "Launch marketing site"


class TestKeywordAutoAssignment:
    """Tests for automatic keyword assignment order."""

    @pytest.mark.asyncio
    async def test_keyword_assignment_order(self, client, async_session: AsyncSession):
        """Keywords are assigned in order: P1 → P2 → P3."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create first priority → should get P1
        response1 = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Priority One", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert response1.status_code == 201
        data1 = response1.json()
        assert data1["data"]["priority"]["calendar_keyword"] == "P1"
        assert data1["data"]["available_keywords"] == ["P2", "P3"]

        # Create second priority → should get P2
        response2 = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Priority Two", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert response2.status_code == 201
        data2 = response2.json()
        assert data2["data"]["priority"]["calendar_keyword"] == "P2"
        assert data2["data"]["available_keywords"] == ["P3"]

        # Create third priority → should get P3
        response3 = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Priority Three", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )
        assert response3.status_code == 201
        data3 = response3.json()
        assert data3["data"]["priority"]["calendar_keyword"] == "P3"
        assert data3["data"]["available_keywords"] == []


class TestMaxPrioritiesEnforcement:
    """Tests for max 3 active priorities limit."""

    @pytest.mark.asyncio
    async def test_fourth_priority_rejected(self, client, async_session: AsyncSession):
        """Creating 4th priority returns 409 MAX_PRIORITIES_REACHED."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create 3 priorities successfully
        for i in range(3):
            response = await client.post(
                "/api/priority-guardian/priorities",
                json={"name": f"Priority {i+1}", "type": "deadline", "deadline": future_date},
                headers={"X-User-ID": str(user_id)},
            )
            assert response.status_code == 201

        # Fourth should fail with 409
        response4 = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Priority Four", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )

        assert response4.status_code == 409
        data = response4.json()
        assert data["success"] is False
        assert data["error"]["code"] == "MAX_PRIORITIES_REACHED"


class TestAuthEnforcement:
    """Tests for X-User-ID header validation."""

    @pytest.mark.asyncio
    async def test_missing_x_user_id_returns_401(self, client):
        """Request without X-User-ID header returns 401."""
        future_date = (date.today() + timedelta(days=30)).isoformat()

        response = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Test", "type": "deadline", "deadline": future_date},
            # No X-User-ID header
        )

        # Missing X-User-ID is an auth failure → 401 (not 422)
        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["code"] == "UNAUTHORIZED"
        assert "Missing" in data["detail"]["message"]

    @pytest.mark.asyncio
    async def test_invalid_uuid_x_user_id_returns_401(self, client):
        """Request with invalid (non-UUID) X-User-ID returns 401."""
        future_date = (date.today() + timedelta(days=30)).isoformat()

        response = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Test", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": "not-a-uuid"},
        )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["code"] == "UNAUTHORIZED"

    @pytest.mark.asyncio
    async def test_valid_uuid_x_user_id_works(self, client, async_session: AsyncSession):
        """Request with valid UUID X-User-ID works."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        response = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Test", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 201


class TestValidationEnforcement:
    """Tests for request validation at the endpoint level."""

    @pytest.mark.asyncio
    async def test_deadline_type_without_deadline_returns_422(self, client, async_session: AsyncSession):
        """Deadline type without deadline field returns 422."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        response = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Test", "type": "deadline"},  # Missing deadline
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_flexible_type_without_desired_result_returns_422(
        self, client, async_session: AsyncSession
    ):
        """Flexible type without desired_result returns 422."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        response = await client.post(
            "/api/priority-guardian/priorities",
            json={
                "name": "Test",
                "type": "flexible",
                "weekly_hour_target": 10.0,
                "checkpoint_date": future_date,
                # Missing desired_result
            },
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_past_deadline_returns_422(self, client, async_session: AsyncSession):
        """Past deadline date returns 422."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        past_date = (date.today() - timedelta(days=1)).isoformat()

        response = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Test", "type": "deadline", "deadline": past_date},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 422


class TestAvailableKeywordsPostCommit:
    """Tests for available_keywords reflecting post-commit state."""

    @pytest.mark.asyncio
    async def test_available_keywords_reflects_db_state(self, client, async_session: AsyncSession):
        """available_keywords is computed from actual DB state after commit."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()

        # Create first priority
        response = await client.post(
            "/api/priority-guardian/priorities",
            json={"name": "Priority One", "type": "deadline", "deadline": future_date},
            headers={"X-User-ID": str(user_id)},
        )

        assert response.status_code == 201
        data = response.json()

        # available_keywords should reflect that P1 is now taken
        assert "P1" not in data["data"]["available_keywords"]
        assert data["data"]["available_keywords"] == ["P2", "P3"]


class TestIdempotency:
    """Sanity checks for retry behavior."""

    @pytest.mark.asyncio
    async def test_same_payload_gets_next_keyword(self, client, async_session: AsyncSession):
        """Retrying exact same payload creates new priority with next keyword."""
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = (date.today() + timedelta(days=30)).isoformat()
        payload = {"name": "Same Name", "type": "deadline", "deadline": future_date}

        # First request
        response1 = await client.post(
            "/api/priority-guardian/priorities",
            json=payload,
            headers={"X-User-ID": str(user_id)},
        )
        assert response1.status_code == 201
        assert response1.json()["data"]["priority"]["calendar_keyword"] == "P1"

        # Second request with same payload
        response2 = await client.post(
            "/api/priority-guardian/priorities",
            json=payload,
            headers={"X-User-ID": str(user_id)},
        )
        assert response2.status_code == 201
        assert response2.json()["data"]["priority"]["calendar_keyword"] == "P2"

        # Third request with same payload
        response3 = await client.post(
            "/api/priority-guardian/priorities",
            json=payload,
            headers={"X-User-ID": str(user_id)},
        )
        assert response3.status_code == 201
        assert response3.json()["data"]["priority"]["calendar_keyword"] == "P3"

        # Fourth should fail (max reached)
        response4 = await client.post(
            "/api/priority-guardian/priorities",
            json=payload,
            headers={"X-User-ID": str(user_id)},
        )
        assert response4.status_code == 409


class TestIntegrityErrorFallback:
    """Tests for IntegrityError handling (race condition safety net)."""

    @pytest.mark.asyncio
    async def test_integrity_error_returns_409_keyword_conflict(
        self, client, async_session: AsyncSession
    ):
        """
        IntegrityError from partial unique index returns 409 KEYWORD_CONFLICT, not 500.

        Simulates a race condition:
        1. Manually insert a priority with P1 keyword (bypassing the endpoint)
        2. Mock compute_available_keywords to return P1 as available (simulating stale read)
        3. Endpoint tries to INSERT with P1 → IntegrityError from unique index
        4. Assert 409 KEYWORD_CONFLICT, not 500
        """
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        # Step 1: Manually insert a priority with P1 (bypassing endpoint transaction)
        future_date = date.today() + timedelta(days=30)
        await async_session.execute(
            text("""
                INSERT INTO pg_priorities (id, user_id, name, type, calendar_keyword, status, deadline)
                VALUES (gen_random_uuid(), :user_id, 'Existing Priority', 'deadline', 'P1', 'active', :deadline)
            """),
            {"user_id": user_id, "deadline": future_date},
        )
        await async_session.commit()

        # Step 2: Mock compute_available_keywords to return P1 as if no keywords are used
        # This simulates a race condition where the SELECT didn't see the concurrent insert
        with patch(
            "backend.apps.priority_guardian.routers.priorities_router.compute_available_keywords",
            return_value=["P1", "P2", "P3"],  # Stale: P1 appears available
        ):
            # Step 3: Try to create a priority - will try to use P1 and hit IntegrityError
            response = await client.post(
                "/api/priority-guardian/priorities",
                json={
                    "name": "New Priority",
                    "type": "deadline",
                    "deadline": future_date.isoformat(),
                },
                headers={"X-User-ID": str(user_id)},
            )

        # Step 4: Assert 409 KEYWORD_CONFLICT, not 500
        assert response.status_code == 409, f"Expected 409, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["success"] is False
        assert data["error"]["code"] == "KEYWORD_CONFLICT"
        assert "race condition" in data["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_known_integrity_error_does_not_return_500(
        self, client, async_session: AsyncSession
    ):
        """
        Verify IntegrityError from partial unique index returns 409, not 500.

        Only IntegrityErrors from idx_pg_priorities_user_keyword_active are mapped
        to 409 KEYWORD_CONFLICT. Other constraint violations would return 500.
        This test triggers the known index violation.
        """
        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        # Insert P1 and P2 manually
        future_date = date.today() + timedelta(days=30)
        for keyword in ["P1", "P2"]:
            await async_session.execute(
                text("""
                    INSERT INTO pg_priorities (id, user_id, name, type, calendar_keyword, status, deadline)
                    VALUES (gen_random_uuid(), :user_id, :name, 'deadline', :keyword, 'active', :deadline)
                """),
                {"user_id": user_id, "name": f"Priority {keyword}", "keyword": keyword, "deadline": future_date},
            )
        await async_session.commit()

        # Mock to return P1 as available (completely stale)
        with patch(
            "backend.apps.priority_guardian.routers.priorities_router.compute_available_keywords",
            return_value=["P1"],  # Stale: only P1 appears available
        ):
            response = await client.post(
                "/api/priority-guardian/priorities",
                json={
                    "name": "Conflict Priority",
                    "type": "deadline",
                    "deadline": future_date.isoformat(),
                },
                headers={"X-User-ID": str(user_id)},
            )

        # Must be 409, never 500 (for this known index violation)
        assert response.status_code != 500, "Known IntegrityError must not bubble as 500"
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_unexpected_integrity_error_returns_500(
        self, client, async_session: AsyncSession
    ):
        """
        Verify unexpected IntegrityErrors (not from keyword index) return 500.

        Only the partial unique index violation is mapped to 409 KEYWORD_CONFLICT.
        Other constraint violations should return 500 to avoid masking real bugs.
        """
        from sqlalchemy.exc import IntegrityError

        user_id = uuid4()
        await async_session.execute(
            text("INSERT INTO core_users (id) VALUES (:id)"),
            {"id": user_id},
        )
        await async_session.commit()

        future_date = date.today() + timedelta(days=30)

        # Mock session.flush to raise an unexpected IntegrityError
        # (e.g., from a hypothetical other constraint)
        class MockOrigError:
            def __str__(self):
                return "violates foreign key constraint some_other_constraint"

        unexpected_error = IntegrityError(
            statement="INSERT INTO pg_priorities ...",
            params={},
            orig=MockOrigError(),
        )

        with patch(
            "backend.apps.priority_guardian.routers.priorities_router.AsyncSession.flush",
            side_effect=unexpected_error,
        ):
            response = await client.post(
                "/api/priority-guardian/priorities",
                json={
                    "name": "Test Priority",
                    "type": "deadline",
                    "deadline": future_date.isoformat(),
                },
                headers={"X-User-ID": str(user_id)},
            )

        # Unexpected IntegrityError should return 500
        assert response.status_code == 500, f"Unexpected IntegrityError should return 500, got {response.status_code}"
