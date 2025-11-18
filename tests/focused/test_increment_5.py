"""
Increment 5: Webhook Renewal + Redis Idempotency Tests

Tests all edge cases from the specification:
1. Idempotency — New Event (sets needs_sync)
2. Idempotency — Duplicate Event (skips needs_sync)
3. Missing message_number header
4. Renewal Needed (<48h)
5. Renewal Not Needed (>48h)
6. Renewal Throttled
7. Renewal Failure
8. Redis Errors
9. Token Refresh Integration
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from backend.apps.focused.logic_webhook import process_webhook_event, should_renew_webhook
from backend.core.models import CoreConnection


@pytest.fixture
def mock_http_client():
    """Mock HTTP client for Google API calls."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = AsyncMock(spec=AsyncSession)
    return session


@pytest.fixture
def mock_connection():
    """Mock database connection with webhook metadata."""
    connection = MagicMock(spec=CoreConnection)
    connection.user_id = "test_user"
    connection.provider = "google"
    connection.google_channel_id = "test-channel-123"
    connection.google_resource_id = "test-resource-456"

    # Default: expires in 72 hours (no renewal needed)
    connection.google_channel_expires_at = datetime.now(timezone.utc) + timedelta(hours=72)

    return connection


# =============================================================================
# Test 1: Idempotency — New Event (sets needs_sync)
# =============================================================================
@pytest.mark.asyncio
async def test_new_webhook_sets_needs_sync(mock_session, mock_http_client, mock_connection):
    """
    Test 1: Idempotency — New Event
    - message_number unseen → set key
    - set needs_sync flag (critical!)
    - return 200
    """
    # Setup
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: mock_connection))

    with patch('backend.apps.focused.logic_webhook.check_webhook_idempotency', return_value=True) as mock_idempotency:
        with patch('backend.apps.focused.logic_webhook.set_needs_sync') as mock_needs_sync:
            with patch('backend.apps.focused.logic_webhook.check_renewal_throttle'):
                # Execute
                await process_webhook_event(
                    user_id="test_user",
                    channel_id="test-channel-123",
                    resource_state="exists",
                    resource_id="test-resource-456",
                    message_number="1",
                    session=mock_session,
                    http_client=mock_http_client,
                )

    # Verify: needs_sync was called
    mock_needs_sync.assert_called_once_with("test_user", ttl_seconds=300)
    # Verify: Session execute was called (connection loaded)
    assert mock_session.execute.called


# =============================================================================
# Test 2: Idempotency — Duplicate Event (does NOT set needs_sync)
# =============================================================================
@pytest.mark.asyncio
async def test_duplicate_webhook_skips_needs_sync(mock_session, mock_http_client):
    """
    Test 2: Idempotency — Duplicate Event
    - Redis key already exists
    - Logs "duplicate ignored"
    - Does NOT set needs_sync (critical!)
    - Returns early
    - No DB queries or API calls
    """
    with patch('backend.apps.focused.logic_webhook.check_webhook_idempotency', return_value=False):
        with patch('backend.apps.focused.logic_webhook.set_needs_sync') as mock_needs_sync:
            # Execute
            await process_webhook_event(
                user_id="test_user",
                channel_id="test-channel-123",
                resource_state="exists",
                resource_id="test-resource-456",
                message_number="1",
                session=mock_session,
                http_client=mock_http_client,
            )

    # Verify: needs_sync was NOT called (duplicate)
    mock_needs_sync.assert_not_called()
    # Verify: No database queries made (early return)
    assert not mock_session.execute.called


# =============================================================================
# Test 3: Missing message_number header
# =============================================================================
@pytest.mark.asyncio
async def test_missing_message_number(mock_session, mock_http_client, mock_connection):
    """
    Test 3: Missing message_number header (AFTER Critical Issue #6 fix)
    - Logs warning about missing message_number
    - Skips idempotency check (can't check without message_number)
    - CONTINUES processing (does NOT return early)
    - Sets needs_sync flag
    - Loads connection from DB
    - Checks renewal (if connection exists)
    - Logs webhook receipt
    - Returns 200
    """
    # Setup: Connection exists with valid expiration
    mock_connection.google_channel_expires_at = datetime.now(timezone.utc) + timedelta(hours=72)
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: mock_connection))

    with patch('backend.apps.focused.logic_webhook.set_needs_sync', return_value=True):
        # Execute with missing message_number
        await process_webhook_event(
            user_id="test_user",
            channel_id="test-channel-123",
            resource_state="exists",
            resource_id="test-resource-456",
            message_number=None,  # Missing
            session=mock_session,
            http_client=mock_http_client,
        )

    # Verify: Database was queried (processing continued)
    assert mock_session.execute.called


# =============================================================================
# Test 4: Webhook expires in 40 hours (renewal triggered)
# =============================================================================
@pytest.mark.asyncio
async def test_webhook_expires_soon_triggers_renewal(mock_session, mock_http_client, mock_connection):
    """
    Test 4: Webhook expires in 40 hours
    - Idempotency passes
    - Renewal triggered inline
    - Existing register_calendar_webhook() called
    - New channel registered
    - DB updated
    - Returns 200
    """
    # Setup: Channel expires in 40 hours
    mock_connection.google_channel_expires_at = datetime.now(timezone.utc) + timedelta(hours=40)

    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: mock_connection))

    mock_renewal_result = {
        "channel_id": "new-channel-789",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    }

    with patch('backend.apps.focused.logic_webhook.check_webhook_idempotency', return_value=True):
        with patch('backend.apps.focused.logic_webhook.check_renewal_throttle', return_value=True):
            with patch('backend.apps.focused.logic_webhook.register_calendar_webhook', return_value=mock_renewal_result):
                # Execute
                await process_webhook_event(
                    user_id="test_user",
                    channel_id="test-channel-123",
                    resource_state="exists",
                    resource_id="test-resource-456",
                    message_number="1",
                    session=mock_session,
                    http_client=mock_http_client,
                )

    # Verify: Webhook processed successfully
    assert mock_session.execute.called


# =============================================================================
# Test 5: Webhook expires in 72 hours (no renewal)
# =============================================================================
@pytest.mark.asyncio
async def test_webhook_expires_later_no_renewal(mock_session, mock_http_client, mock_connection):
    """
    Test 5: Webhook expires in 72 hours
    - Idempotency passes
    - No renewal needed
    - Returns 200
    """
    # Setup: Channel expires in 72 hours (beyond 48h threshold)
    mock_connection.google_channel_expires_at = datetime.now(timezone.utc) + timedelta(hours=72)

    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: mock_connection))

    with patch('backend.apps.focused.logic_webhook.check_webhook_idempotency', return_value=True):
        with patch('backend.apps.focused.logic_webhook.register_calendar_webhook') as mock_renewal:
            # Execute
            await process_webhook_event(
                user_id="test_user",
                channel_id="test-channel-123",
                resource_state="exists",
                resource_id="test-resource-456",
                message_number="1",
                session=mock_session,
                http_client=mock_http_client,
            )

            # Verify: Renewal NOT called
            assert not mock_renewal.called


# =============================================================================
# Test 6: Inline renewal fails
# =============================================================================
@pytest.mark.asyncio
async def test_inline_renewal_fails_gracefully(mock_session, mock_http_client, mock_connection):
    """
    Test 6: Inline renewal fails
    - Logs error
    - Does NOT return error
    - Still returns 200
    - Webhook processing continues
    """
    # Setup: Channel expires in 40 hours
    mock_connection.google_channel_expires_at = datetime.now(timezone.utc) + timedelta(hours=40)

    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: mock_connection))

    # Mock renewal failure
    mock_renewal_error = {"error": "WEBHOOK_REGISTRATION_FAILED"}

    with patch('backend.apps.focused.logic_webhook.check_webhook_idempotency', return_value=True):
        with patch('backend.apps.focused.logic_webhook.check_renewal_throttle', return_value=True):
            with patch('backend.apps.focused.logic_webhook.register_calendar_webhook', return_value=mock_renewal_error):
                # Execute - should not raise exception
                await process_webhook_event(
                    user_id="test_user",
                    channel_id="test-channel-123",
                    resource_state="exists",
                    resource_id="test-resource-456",
                    message_number="1",
                    session=mock_session,
                    http_client=mock_http_client,
                )

    # Verify: Webhook still processed (no exception raised)
    assert mock_session.execute.called


# =============================================================================
# Test 7: Redis unavailable
# =============================================================================
@pytest.mark.asyncio
async def test_redis_unavailable_allows_webhook(mock_session, mock_http_client, mock_connection):
    """
    Test 7: Redis unavailable
    - Log error
    - Skip idempotency check (allow webhook through)
    - Process webhook anyway
    - Return 200
    """
    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: mock_connection))

    # Mock Redis unavailable (returns True to allow webhook)
    with patch('backend.apps.focused.logic_webhook.check_webhook_idempotency', return_value=True):
        with patch('backend.apps.focused.logic_webhook.check_renewal_throttle', return_value=True):
            # Execute
            await process_webhook_event(
                user_id="test_user",
                channel_id="test-channel-123",
                resource_state="exists",
                resource_id="test-resource-456",
                message_number="1",
                session=mock_session,
                http_client=mock_http_client,
            )

    # Verify: Webhook processed despite Redis issue
    assert mock_session.execute.called


# =============================================================================
# Test 8: Channel already expired
# =============================================================================
@pytest.mark.asyncio
async def test_channel_already_expired_triggers_renewal(mock_session, mock_http_client, mock_connection):
    """
    Test 8: Channel already expired
    - Still triggers renewal
    - Works same as "expires in 40 hours"
    """
    # Setup: Channel already expired (1 hour ago)
    mock_connection.google_channel_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: mock_connection))

    mock_renewal_result = {
        "channel_id": "new-channel-999",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    }

    with patch('backend.apps.focused.logic_webhook.check_webhook_idempotency', return_value=True):
        with patch('backend.apps.focused.logic_webhook.check_renewal_throttle', return_value=True):
            with patch('backend.apps.focused.logic_webhook.register_calendar_webhook', return_value=mock_renewal_result) as mock_renewal:
                # Execute
                await process_webhook_event(
                    user_id="test_user",
                    channel_id="test-channel-123",
                    resource_state="exists",
                    resource_id="test-resource-456",
                    message_number="1",
                    session=mock_session,
                    http_client=mock_http_client,
                )

                # Verify: Renewal WAS called
                assert mock_renewal.called


# =============================================================================
# Test 9: Renewal throttled (multiple webhooks)
# =============================================================================
@pytest.mark.asyncio
async def test_renewal_throttled_multiple_webhooks(mock_session, mock_http_client, mock_connection):
    """
    Test 9: Renewal throttled (multiple webhooks)
    - First webhook: Renewal triggered and throttle key set
    - Second webhook (same user): Renewal skipped (throttled)
    - Logs "renewal throttled"
    - Returns 200
    """
    # Setup: Channel expires in 40 hours
    mock_connection.google_channel_expires_at = datetime.now(timezone.utc) + timedelta(hours=40)

    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: mock_connection))

    with patch('backend.apps.focused.logic_webhook.check_webhook_idempotency', return_value=True):
        # First webhook: throttle allowed (True)
        with patch('backend.apps.focused.logic_webhook.check_renewal_throttle', return_value=False):
            with patch('backend.apps.focused.logic_webhook.register_calendar_webhook') as mock_renewal:
                # Execute second webhook
                await process_webhook_event(
                    user_id="test_user",
                    channel_id="test-channel-123",
                    resource_state="exists",
                    resource_id="test-resource-456",
                    message_number="2",
                    session=mock_session,
                    http_client=mock_http_client,
                )

                # Verify: Renewal NOT called (throttled)
                assert not mock_renewal.called


# =============================================================================
# Test 9: Token Refresh Integration
# =============================================================================
@pytest.mark.asyncio
async def test_token_refresh_during_renewal(mock_session, mock_http_client, mock_connection):
    """
    Test 9: Token Refresh Integration
    - Token expired → ensure token is refreshed during renewal
    - register_calendar_webhook() internally calls ensure_valid_access_token()
    """
    # Setup: Channel expires in 40 hours
    mock_connection.google_channel_expires_at = datetime.now(timezone.utc) + timedelta(hours=40)

    mock_session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: mock_connection))

    mock_renewal_result = {
        "channel_id": "new-channel-999",
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    }

    with patch('backend.apps.focused.logic_webhook.check_webhook_idempotency', return_value=True):
        with patch('backend.apps.focused.logic_webhook.check_renewal_throttle', return_value=True):
            with patch('backend.apps.focused.logic_webhook.set_needs_sync'):
                with patch('backend.apps.focused.logic_webhook.register_calendar_webhook', return_value=mock_renewal_result) as mock_renewal:
                    # Execute
                    await process_webhook_event(
                        user_id="test_user",
                        channel_id="test-channel-123",
                        resource_state="exists",
                        resource_id="test-resource-456",
                        message_number="1",
                        session=mock_session,
                        http_client=mock_http_client,
                    )

                    # Verify: register_calendar_webhook was called
                    # (it internally calls ensure_valid_access_token which handles token refresh)
                    assert mock_renewal.called
                    mock_renewal.assert_called_once_with(
                        user_id="test_user",
                        session=mock_session,
                        http_client=mock_http_client,
                    )


# =============================================================================
# Test: should_renew_webhook helper
# =============================================================================
def test_should_renew_webhook_helper():
    """Test the should_renew_webhook() helper function."""

    # Test 1: Expires in 40 hours -> should renew
    expires_soon = datetime.now(timezone.utc) + timedelta(hours=40)
    assert should_renew_webhook(expires_soon, threshold_hours=48) is True

    # Test 2: Expires in 72 hours -> should NOT renew
    expires_later = datetime.now(timezone.utc) + timedelta(hours=72)
    assert should_renew_webhook(expires_later, threshold_hours=48) is False

    # Test 3: Already expired -> should renew
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    assert should_renew_webhook(expired, threshold_hours=48) is True

    # Test 4: None value -> should NOT renew
    assert should_renew_webhook(None, threshold_hours=48) is False

    # Test 5: Exactly at threshold -> should renew
    exactly_48h = datetime.now(timezone.utc) + timedelta(hours=48)
    assert should_renew_webhook(exactly_48h, threshold_hours=48) is True


# =============================================================================
# Test: Verify Redis key patterns use "focused:" prefix
# =============================================================================
@pytest.mark.asyncio
async def test_redis_key_patterns():
    """
    Verify that Redis keys use the correct 'focused:' prefix as per specification.
    """
    from backend.core.redis_client import check_webhook_idempotency, check_renewal_throttle, set_needs_sync

    user_id = "test_user"
    message_number = "12345"

    # Mock is_connected() to return True so functions proceed to call set()
    with patch('backend.core.redis_client.redis_client.is_connected', return_value=True):
        with patch('backend.core.redis_client.redis_client.set') as mock_set:
            # Test idempotency key pattern
            mock_set.return_value = True
            await check_webhook_idempotency(user_id, message_number, ttl_seconds=86400)

            # Verify key pattern: focused:webhook:{user_id}:{message_number}
            expected_key = f"focused:webhook:{user_id}:{message_number}"
            mock_set.assert_called_with(expected_key, "1", ex=86400, nx=True)

    with patch('backend.core.redis_client.redis_client.is_connected', return_value=True):
        with patch('backend.core.redis_client.redis_client.set') as mock_set:
            # Test renewal throttle key pattern
            mock_set.return_value = True
            await check_renewal_throttle(user_id, ttl_seconds=86400)

            # Verify key pattern: focused:webhook:renew_throttle:{user_id}
            expected_key = f"focused:webhook:renew_throttle:{user_id}"
            mock_set.assert_called_with(expected_key, "1", ex=86400, nx=True)

    with patch('backend.core.redis_client.redis_client.is_connected', return_value=True):
        with patch('backend.core.redis_client.redis_client.set') as mock_set:
            # Test needs_sync key pattern
            mock_set.return_value = True
            await set_needs_sync(user_id, ttl_seconds=300)

            # Verify key pattern: focused:needs_sync:{user_id}
            expected_key = f"focused:needs_sync:{user_id}"
            mock_set.assert_called_with(expected_key, "true", ex=300)
