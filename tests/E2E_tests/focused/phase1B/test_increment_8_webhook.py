"""
Increment 8 — Phase 1B: Webhook Lifecycle E2E Tests (5 tests)

Tests the complete webhook lifecycle using:
- REAL DB + REAL Redis (isolated via env prefix "test:")
- REAL webhook processing logic (NO internal mocking)
- REAL token encryption/decryption
- ONLY mock: Google Calendar webhook API (register_webhook, stop_webhook)

Test Categories:
- Test 1: Fresh webhook registration
- Test 2: Webhook reception after registration
- Test 3: Re-registration replaces old channel
- Test 4: Event-driven renewal (<48h warning)
- Test 5: Idempotent renewal (duplicate warnings)
"""

import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from backend.core.models import CoreConnection


# =============================================================================
# FIXED REFERENCE TIME - prevents flaky tests from millisecond drift
# =============================================================================
REF_TIME = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class TestWebhookLifecycle:
    """Webhook lifecycle tests covering registration, reception, and renewal."""

    @pytest.mark.asyncio
    async def test_01_fresh_webhook_registration(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_without_channel: dict,
        mock_webhook,
        patch_google_webhook,
    ):
        """
        Test 1: Fresh webhook registration for user without existing channel.

        Uses test_user_without_channel fixture (user has OAuth but no webhook).

        Verifies:
        - watch_calendar endpoint registers webhook with Google
        - Response contains channel_id and expiration
        - DB stores channel_id, resource_id, expires_at
        - Google API (mock) was called exactly once
        """
        user_id = test_user_without_channel["user_id"]

        # Verify no existing channel (fixture creates user without channel)
        async_session.expire_all()
        result = await async_session.execute(
            select(CoreConnection).where(
                CoreConnection.user_id == user_id,
                CoreConnection.provider == "google",
            )
        )
        conn_before = result.scalar_one()
        assert conn_before.google_channel_id is None, "Fixture should create user without channel"

        # Register webhook
        response = await client.post(
            "/api/focused/tools/watch_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        response_json = response.json()

        # Verify response structure
        assert response_json.get("success") is True, f"Registration failed: {response_json}"
        data = response_json.get("data", {})
        assert "channel_id" in data, f"Response missing channel_id: {response_json}"
        assert "expires_at" in data, f"Response missing expires_at: {response_json}"

        # Verify DB storage
        async_session.expire_all()
        result = await async_session.execute(
            select(CoreConnection).where(
                CoreConnection.user_id == user_id,
                CoreConnection.provider == "google",
            )
        )
        conn = result.scalar_one()

        assert conn.google_channel_id == data["channel_id"], "channel_id not stored in DB"
        assert conn.google_resource_id is not None, "resource_id not stored in DB"
        assert conn.google_channel_expires_at is not None, "expires_at not stored in DB"

        # Expiration should be precisely ~7 days
        now = datetime.now(timezone.utc)
        expected_expiry = now + timedelta(days=7)
        actual_expiry = conn.google_channel_expires_at
        expiry_delta = abs((actual_expiry - expected_expiry).total_seconds())
        assert expiry_delta < 300, \
            f"Expiration should be ~7 days from now (within 5 min), got delta of {expiry_delta}s"

        # Verify Google API was called
        assert len(mock_webhook.watch_calls) == 1, "Expected exactly 1 watch call"
        assert mock_webhook.watch_calls[0]["channel_id"] == data["channel_id"]

    @pytest.mark.asyncio
    async def test_02_webhook_reception_and_idempotency(
        self,
        client: AsyncClient,
        test_user_with_connection: dict,
        mock_webhook,
        patch_google_webhook,
        mock_google,
        patch_google_list_events,
        redis_helpers,
    ):
        """
        Test 2: Webhook reception sets needs_sync and verifies idempotency.

        Webhook logic:
        1. Validate headers
        2. Check idempotency (message_number) - skip if duplicate
        3. Set needs_sync = true
        4. Check expiration (renewal only if <48h remaining - NOT this test)
        5. Return 200

        This test uses a channel with ~7 days until expiration, so NO renewal.

        Verifies:
        - msg_12345: processed, sets needs_sync, stores idempotency key
        - msg_12345 (duplicate): ignored, needs_sync NOT re-set
        - msg_12346 (new): processed, sets needs_sync
        - msg_12345 (duplicate again): still ignored
        - NO renewal triggered (expiration is ~7 days out)
        """
        user_id = test_user_with_connection["user_id"]
        channel_id = test_user_with_connection["channel_id"]
        resource_id = test_user_with_connection["resource_id"]
        msg_1 = "test_02_msg_12345"
        msg_2 = "test_02_msg_12346"

        # Setup: Clear any existing state
        await redis_helpers.del_needs(user_id)
        await redis_helpers.clear_idempotency(user_id, msg_1)
        await redis_helpers.clear_idempotency(user_id, msg_2)
        assert await redis_helpers.get_needs(user_id) is False
        assert await redis_helpers.has_idempotency_key(user_id, msg_1) is False
        assert await redis_helpers.has_idempotency_key(user_id, msg_2) is False

        # === WEBHOOK 1: msg_12345 (new) ===
        response1 = await client.post(
            "/webhook/focused/google_calendar",
            headers={
                "X-Goog-Channel-ID": channel_id,
                "X-Goog-Resource-ID": resource_id,
                "X-Goog-Resource-State": "exists",
                "X-Goog-Message-Number": msg_1,
            },
        )
        assert response1.status_code == 200
        assert await redis_helpers.get_needs(user_id) is True, \
            "msg_12345 should set needs_sync=true"
        assert await redis_helpers.has_idempotency_key(user_id, msg_1) is True, \
            "msg_12345 should store idempotency key"

        # Clear needs_sync to test duplicate behavior
        await redis_helpers.del_needs(user_id)

        # === WEBHOOK 2: msg_12345 (duplicate) ===
        response2 = await client.post(
            "/webhook/focused/google_calendar",
            headers={
                "X-Goog-Channel-ID": channel_id,
                "X-Goog-Resource-ID": resource_id,
                "X-Goog-Resource-State": "exists",
                "X-Goog-Message-Number": msg_1,  # Same as webhook 1
            },
        )
        assert response2.status_code == 200
        assert await redis_helpers.get_needs(user_id) is False, \
            "Duplicate msg_12345 should be ignored - needs_sync NOT re-set"

        # === WEBHOOK 3: msg_12346 (new - different message number) ===
        response3 = await client.post(
            "/webhook/focused/google_calendar",
            headers={
                "X-Goog-Channel-ID": channel_id,
                "X-Goog-Resource-ID": resource_id,
                "X-Goog-Resource-State": "exists",
                "X-Goog-Message-Number": msg_2,  # Different message number
            },
        )
        assert response3.status_code == 200
        assert await redis_helpers.get_needs(user_id) is True, \
            "New msg_12346 should set needs_sync=true"
        assert await redis_helpers.has_idempotency_key(user_id, msg_2) is True, \
            "msg_12346 should store its own idempotency key"

        # Clear needs_sync again
        await redis_helpers.del_needs(user_id)

        # === WEBHOOK 4: msg_12345 (duplicate again) ===
        response4 = await client.post(
            "/webhook/focused/google_calendar",
            headers={
                "X-Goog-Channel-ID": channel_id,
                "X-Goog-Resource-ID": resource_id,
                "X-Goog-Resource-State": "exists",
                "X-Goog-Message-Number": msg_1,  # Still duplicate
            },
        )
        assert response4.status_code == 200
        assert await redis_helpers.get_needs(user_id) is False, \
            "msg_12345 should still be ignored on third attempt"

        # Both idempotency keys should exist
        assert await redis_helpers.has_idempotency_key(user_id, msg_1) is True
        assert await redis_helpers.has_idempotency_key(user_id, msg_2) is True

        # Verify NO renewal occurred (channel expiration is ~7 days out)
        assert len(mock_webhook.watch_calls) == 0, \
            "No renewal should occur - expiration is not within 48h"

    @pytest.mark.asyncio
    async def test_03_re_registration_replaces_old_channel(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_webhook,
        patch_google_webhook,
    ):
        """
        Test 3: Re-registration stops old channel and creates new one.

        Verifies:
        - Old channel is stopped via stop_webhook
        - New channel is created via register_webhook
        - DB is updated with new channel_id
        - Old and new channel_ids are different
        """
        user_id = test_user_with_connection["user_id"]
        old_channel_id = test_user_with_connection["channel_id"]
        old_resource_id = test_user_with_connection["resource_id"]

        # Register webhook (should replace existing)
        response = await client.post(
            "/api/focused/tools/watch_calendar",
            json={"user_id": user_id},
            headers={"X-User-ID": user_id},
        )

        assert response.status_code == 200
        response_json = response.json()

        # Response structure: {"success": true, "data": {"channel_id": "...", ...}}
        assert response_json.get("success") is True, f"Registration failed: {response_json}"
        data = response_json.get("data", {})
        new_channel_id = data["channel_id"]

        # Verify different channel ID
        assert new_channel_id != old_channel_id, "New channel should have different ID"

        # Verify old channel was stopped
        assert len(mock_webhook.stop_calls) == 1, "Old channel should be stopped"
        assert mock_webhook.stop_calls[0]["channel_id"] == old_channel_id
        assert mock_webhook.stop_calls[0]["resource_id"] == old_resource_id

        # Verify new channel was created
        assert len(mock_webhook.watch_calls) == 1, "New channel should be created"
        assert mock_webhook.watch_calls[0]["channel_id"] == new_channel_id

        # Verify DB updated
        async_session.expire_all()
        result = await async_session.execute(
            select(CoreConnection).where(
                CoreConnection.user_id == user_id,
                CoreConnection.provider == "google",
            )
        )
        conn = result.scalar_one()
        assert conn.google_channel_id == new_channel_id

    @pytest.mark.asyncio
    async def test_04_event_driven_renewal_under_48h(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_webhook,
        patch_google_webhook,
        mock_google,
        patch_google_list_events,
    ):
        """
        Test 4: Channel expiring within 48h triggers automatic renewal.

        NOTE: Google webhooks do NOT have a separate "expiring" resource_state.
        Renewal is triggered by checking the channel's expiration timestamp
        stored in the DB, not by the X-Goog-Resource-State header.

        Any webhook (resource_state="exists", "sync", etc.) will trigger
        the expiration check. If expires_at < now + 48h, renewal occurs.

        Verifies:
        - Setup: Channel expiration set to 40h from now (under 48h threshold)
        - Any webhook triggers expiration check
        - Old channel is stopped
        - New channel is created
        - DB is updated with new expiration (~7 days)
        """
        user_id = test_user_with_connection["user_id"]
        old_channel_id = test_user_with_connection["channel_id"]

        # Setup: Set expiration to 40 hours from now (under 48h threshold)
        async_session.expire_all()
        result = await async_session.execute(
            select(CoreConnection).where(
                CoreConnection.user_id == user_id,
                CoreConnection.provider == "google",
            )
        )
        conn = result.scalar_one()
        conn.google_channel_expires_at = datetime.now(timezone.utc) + timedelta(hours=40)
        await async_session.flush()

        # Send webhook - resource_state="exists" is a normal calendar change notification
        # Renewal is triggered by expiration timestamp check, NOT resource_state
        response = await client.post(
            "/webhook/focused/google_calendar",
            headers={
                "X-Goog-Channel-ID": old_channel_id,
                "X-Goog-Resource-ID": test_user_with_connection["resource_id"],
                "X-Goog-Resource-State": "exists",  # Normal notification, not "expiring"
                "X-Goog-Message-Number": "renewal_test_1",
            },
        )

        assert response.status_code == 200

        # Verify renewal occurred
        assert len(mock_webhook.stop_calls) >= 1, "Old channel should be stopped"
        assert len(mock_webhook.watch_calls) >= 1, "New channel should be created"

        # Verify DB has new expiration
        async_session.expire_all()
        result = await async_session.execute(
            select(CoreConnection).where(
                CoreConnection.user_id == user_id,
                CoreConnection.provider == "google",
            )
        )
        conn = result.scalar_one()

        # New expiration should be precisely ~7 days (not 40 hours)
        now = datetime.now(timezone.utc)
        expected_expiry = now + timedelta(days=7)
        actual_expiry = conn.google_channel_expires_at
        expiry_delta = abs((actual_expiry - expected_expiry).total_seconds())
        assert expiry_delta < 300, \
            f"Expiration should be ~7 days from now (within 5 min), got delta of {expiry_delta}s"

        # Channel ID should be different
        assert conn.google_channel_id != old_channel_id, "Channel ID should change after renewal"

    @pytest.mark.asyncio
    async def test_05_renewal_throttle_prevents_duplicates(
        self,
        client: AsyncClient,
        async_session: AsyncSession,
        test_user_with_connection: dict,
        mock_webhook,
        patch_google_webhook,
        mock_google,
        patch_google_list_events,
        redis_helpers,
    ):
        """
        Test 5: Renewal throttle prevents redundant renewals.

        Clean E2E flow - NO artificial state manipulation between webhooks:
        1. Setup: Clear throttle, set near-expiration
        2. First webhook → renewal occurs → throttle key set
        3. Second webhook → throttled (no renewal)
        4. Third webhook → throttled (no renewal)
        5. Verify: only 1 stop, only 1 watch, throttle key exists

        The renewal throttle uses Redis SET NX with 24h TTL.
        Key format: focused:webhook:renew_throttle:{user_id}
        """
        user_id = test_user_with_connection["user_id"]
        channel_id = test_user_with_connection["channel_id"]
        resource_id = test_user_with_connection["resource_id"]

        # === SETUP (only place where we manipulate state) ===
        # Clear any existing throttle from previous tests
        await redis_helpers.clear_throttle(user_id)
        assert await redis_helpers.has_throttle_key(user_id) is False, \
            "Throttle key should not exist before test"

        # Set channel expiration to 40 hours from now (under 48h threshold)
        async_session.expire_all()
        result = await async_session.execute(
            select(CoreConnection).where(
                CoreConnection.user_id == user_id,
                CoreConnection.provider == "google",
            )
        )
        conn = result.scalar_one()
        conn.google_channel_expires_at = datetime.now(timezone.utc) + timedelta(hours=40)
        await async_session.flush()

        # === FIRST WEBHOOK (should trigger renewal) ===
        response1 = await client.post(
            "/webhook/focused/google_calendar",
            headers={
                "X-Goog-Channel-ID": channel_id,
                "X-Goog-Resource-ID": resource_id,
                "X-Goog-Resource-State": "exists",
                "X-Goog-Message-Number": "throttle_test_1",
            },
        )
        assert response1.status_code == 200
        assert len(mock_webhook.watch_calls) == 1, "First webhook should trigger renewal"
        assert len(mock_webhook.stop_calls) == 1, "First webhook should stop old channel"

        # Verify throttle key was set by production code
        assert await redis_helpers.has_throttle_key(user_id) is True, \
            "Throttle key should be set after renewal"
        throttle_ttl = await redis_helpers.get_throttle_ttl(user_id)
        assert 86000 < throttle_ttl <= 86400, \
            f"Throttle TTL should be ~24h (86400s), got {throttle_ttl}s"

        # === SECOND WEBHOOK (should be throttled - NO state manipulation) ===
        response2 = await client.post(
            "/webhook/focused/google_calendar",
            headers={
                "X-Goog-Channel-ID": channel_id,
                "X-Goog-Resource-ID": resource_id,
                "X-Goog-Resource-State": "exists",
                "X-Goog-Message-Number": "throttle_test_2",
            },
        )
        assert response2.status_code == 200
        assert len(mock_webhook.watch_calls) == 1, \
            "Second webhook should be throttled - still only 1 watch"
        assert len(mock_webhook.stop_calls) == 1, \
            "Second webhook should be throttled - still only 1 stop"

        # === THIRD WEBHOOK (should also be throttled - NO state manipulation) ===
        response3 = await client.post(
            "/webhook/focused/google_calendar",
            headers={
                "X-Goog-Channel-ID": channel_id,
                "X-Goog-Resource-ID": resource_id,
                "X-Goog-Resource-State": "exists",
                "X-Goog-Message-Number": "throttle_test_3",
            },
        )
        assert response3.status_code == 200
        assert len(mock_webhook.watch_calls) == 1, \
            "Third webhook should be throttled - still only 1 watch"
        assert len(mock_webhook.stop_calls) == 1, \
            "Third webhook should be throttled - still only 1 stop"

        # === FINAL VERIFICATION ===
        # Verify the stop was for the original channel
        assert mock_webhook.stop_calls[0]["channel_id"] == channel_id, \
            "Stop should be for the original channel"

        # Verify final DB state
        async_session.expire_all()
        result = await async_session.execute(
            select(CoreConnection).where(
                CoreConnection.user_id == user_id,
                CoreConnection.provider == "google",
            )
        )
        conn = result.scalar_one()

        # Channel should be renewed (different from original)
        new_channel_id = conn.google_channel_id
        assert new_channel_id != channel_id, \
            "Channel should be renewed after first warning"

        # Verify the watch created the channel now stored in DB
        assert mock_webhook.watch_calls[0]["channel_id"] == new_channel_id, \
            "Watch should create the channel now stored in DB"

        # Expiration should be precisely ~7 days (renewed)
        now = datetime.now(timezone.utc)
        expected_expiry = now + timedelta(days=7)
        actual_expiry = conn.google_channel_expires_at
        expiry_delta = abs((actual_expiry - expected_expiry).total_seconds())
        assert expiry_delta < 300, \
            f"Expiration should be ~7 days from now (within 5 min), got delta of {expiry_delta}s"

        # Throttle key should still exist
        assert await redis_helpers.has_throttle_key(user_id) is True, \
            "Throttle key should still exist after all webhooks"
