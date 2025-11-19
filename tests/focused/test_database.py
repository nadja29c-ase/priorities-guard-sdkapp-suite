"""
Production-grade migration audit for core schema.

Covers:
- core_users
- core_connections (+ webhook fields, provider_metadata)
- oauth_state
- focused_user_keywords
- focused_focus_sessions

Goals:
- Verify constraints, indexes, ENUMs, FK behavior
- Verify soft-delete + retention-related fields
- Verify timestamptz usage and JSON metadata
"""

import asyncio
from uuid import uuid4
from datetime import datetime, timezone

import pytest
from sqlalchemy import text, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_test_user(async_session: AsyncSession) -> str:
    """Insert a core_users row and return its UUID as string."""
    user_id = str(uuid4())
    await async_session.execute(
        text("INSERT INTO core_users (id) VALUES (:id)"),
        {"id": user_id},
    )
    await async_session.commit()
    return user_id


# ---------------------------------------------------------------------------
# 1. Schema / index sanity checks
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_focused_focus_sessions_indexes_exist(async_session: AsyncSession):
    """
    focused_focus_sessions must have all required indexes from the migration:
      - idx_focus_sessions_start_time
      - idx_focus_sessions_end_time
      - idx_focus_sessions_focus_blocks
      - idx_focus_sessions_user_hash
      - idx_focus_sessions_cleanup
      - idx_focus_sessions_ical_uid
    """
    inspector = inspect(async_session.bind)
    indexes = inspector.get_indexes("focused_focus_sessions")
    names = {idx["name"] for idx in indexes}

    expected = {
        "idx_focus_sessions_start_time",
        "idx_focus_sessions_end_time",
        "idx_focus_sessions_focus_blocks",
        "idx_focus_sessions_user_hash",
        "idx_focus_sessions_cleanup",
        "idx_focus_sessions_ical_uid",
    }

    missing = expected - names
    assert not missing, f"Missing indexes on focused_focus_sessions: {missing}"


@pytest.mark.asyncio
async def test_core_connections_indexes_exist(async_session: AsyncSession):
    """
    core_connections must have:
      - ix_token_expires
      - ix_user_provider
      - ix_channel_expires
    """
    inspector = inspect(async_session.bind)
    indexes = inspector.get_indexes("core_connections")
    names = {idx["name"] for idx in indexes}

    expected = {
        "ix_token_expires",
        "ix_user_provider",
        "ix_channel_expires",
    }

    missing = expected - names
    assert not missing, f"Missing indexes on core_connections: {missing}"


@pytest.mark.asyncio
async def test_oauth_state_index_exists(async_session: AsyncSession):
    """
    oauth_state must have index on expires_at:
      - idx_oauth_state_expires_at
    """
    inspector = inspect(async_session.bind)
    indexes = inspector.get_indexes("oauth_state")
    names = {idx["name"] for idx in indexes}

    assert "idx_oauth_state_expires_at" in names


@pytest.mark.asyncio
async def test_focused_user_keywords_index_exists(async_session: AsyncSession):
    """
    focused_user_keywords must have:
      - ix_focused_user_keywords_user_id
    """
    inspector = inspect(async_session.bind)
    indexes = inspector.get_indexes("focused_user_keywords")
    names = {idx["name"] for idx in indexes}

    assert "ix_focused_user_keywords_user_id" in names


# ---------------------------------------------------------------------------
# 2. ENUM presence and status values
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_event_status_enum_exists(async_session: AsyncSession):
    """
    PostgreSQL ENUM type 'event_status_enum' must exist.
    """
    result = await async_session.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'event_status_enum'
            )
            """
        )
    )
    exists = result.scalar_one()
    assert exists is True


@pytest.mark.asyncio
async def test_focus_sessions_status_accepts_deleted(async_session: AsyncSession):
    """
    status column on focused_focus_sessions must accept 'deleted'.
    """
    user_id = await _create_test_user(async_session)

    await async_session.execute(
        text(
            """
            INSERT INTO focused_focus_sessions (
                user_id, google_event_id, google_calendar_id,
                google_ical_uid, google_updated_at,
                start_time, end_time,
                sha256_content_hash, status, version
            ) VALUES (
                :user_id, 'status_test', 'primary',
                'ical_status', now(),
                '2025-01-01 09:00:00+00', '2025-01-01 10:00:00+00',
                repeat('a', 64), 'active', 1
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    # Update to deleted
    await async_session.execute(
        text(
            """
            UPDATE focused_focus_sessions
            SET status = 'deleted'
            WHERE google_event_id = 'status_test'
            """
        )
    )
    await async_session.commit()

    result = await async_session.execute(
        text(
            """
            SELECT status FROM focused_focus_sessions
            WHERE google_event_id = 'status_test'
            """
        )
    )
    status = result.scalar_one()
    assert status == "deleted"


# ---------------------------------------------------------------------------
# 3. Unique constraints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_focus_sessions_unique_user_event_calendar(async_session: AsyncSession):
    """
    uq_focus_sessions_user_event must prevent duplicate
    (user_id, google_event_id, google_calendar_id).
    """
    user_id = await _create_test_user(async_session)

    # First insert
    await async_session.execute(
        text(
            """
            INSERT INTO focused_focus_sessions (
                user_id, google_event_id, google_calendar_id,
                google_ical_uid, google_updated_at,
                start_time, end_time,
                sha256_content_hash, status, version
            ) VALUES (
                :user_id, 'dup_test', 'primary',
                'ical_dup1', now(),
                '2025-01-01 09:00:00+00', '2025-01-01 10:00:00+00',
                repeat('b', 64), 'active', 1
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    # Duplicate insert with same (user_id, event_id, calendar_id)
    with pytest.raises(IntegrityError) as exc_info:
        await async_session.execute(
            text(
                """
                INSERT INTO focused_focus_sessions (
                    user_id, google_event_id, google_calendar_id,
                    google_ical_uid, google_updated_at,
                    start_time, end_time,
                    sha256_content_hash, status, version
                ) VALUES (
                    :user_id, 'dup_test', 'primary',
                    'ical_dup2', now(),
                    '2025-01-01 10:00:00+00', '2025-01-01 11:00:00+00',
                    repeat('c', 64), 'active', 1
                )
                """
            ),
            {"user_id": user_id},
        )
        await async_session.commit()

    assert "uq_focus_sessions_user_event" in str(exc_info.value)
    await async_session.rollback()


@pytest.mark.asyncio
async def test_core_connections_unique_user_provider(async_session: AsyncSession):
    """
    uq_user_provider must prevent multiple connections
    per (user_id, provider).
    """
    user_id = await _create_test_user(async_session)

    # First connection
    await async_session.execute(
        text(
            """
            INSERT INTO core_connections (
                user_id, provider, encrypted_access_token,
                token_expires_at, scopes
            ) VALUES (
                :user_id, 'google', 'token1',
                now() + interval '1 hour',
                ARRAY['calendar.readonly']::text[]
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    # Second connection for same user + provider
    with pytest.raises(IntegrityError) as exc_info:
        await async_session.execute(
            text(
                """
                INSERT INTO core_connections (
                    user_id, provider, encrypted_access_token,
                    token_expires_at, scopes
                ) VALUES (
                    :user_id, 'google', 'token2',
                    now() + interval '1 hour',
                    ARRAY['calendar.readonly']::text[]
                )
                """
            ),
            {"user_id": user_id},
        )
        await async_session.commit()

    assert "uq_user_provider" in str(exc_info.value)
    await async_session.rollback()


# ---------------------------------------------------------------------------
# 4. Check constraints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_focus_sessions_sha256_length_enforced(async_session: AsyncSession):
    """
    ck_focus_sessions_hash_length: sha256_content_hash must be exactly 64 chars.
    """
    user_id = await _create_test_user(async_session)

    with pytest.raises(IntegrityError) as exc_info:
        await async_session.execute(
            text(
                """
                INSERT INTO focused_focus_sessions (
                    user_id, google_event_id, google_calendar_id,
                    google_ical_uid, google_updated_at,
                    start_time, end_time,
                    sha256_content_hash, status, version
                ) VALUES (
                    :user_id, 'hash_len_test', 'primary',
                    'ical_hash', now(),
                    '2025-01-01 09:00:00+00', '2025-01-01 10:00:00+00',
                    'too_short',  -- length != 64
                    'active', 1
                )
                """
            ),
            {"user_id": user_id},
        )
        await async_session.commit()

    assert "ck_focus_sessions_hash_length" in str(exc_info.value)
    await async_session.rollback()


@pytest.mark.asyncio
async def test_focus_sessions_description_max_length(async_session: AsyncSession):
    """
    ck_focus_sessions_description_length:
    event_description must be <= 8192 chars (if not NULL).
    """
    user_id = await _create_test_user(async_session)

    # Too long
    with pytest.raises(IntegrityError) as exc_info:
        await async_session.execute(
            text(
                """
                INSERT INTO focused_focus_sessions (
                    user_id, google_event_id, google_calendar_id,
                    google_ical_uid, google_updated_at,
                    start_time, end_time, event_description,
                    sha256_content_hash, status, version
                ) VALUES (
                    :user_id, 'desc_too_long', 'primary',
                    'ical_desc', now(),
                    '2025-01-01 09:00:00+00', '2025-01-01 10:00:00+00',
                    repeat('x', 9000),  -- > 8192
                    repeat('d', 64), 'active', 1
                )
                """
            ),
            {"user_id": user_id},
        )
        await async_session.commit()

    assert "ck_focus_sessions_description_length" in str(exc_info.value)
    await async_session.rollback()

    # At boundary (8192) should succeed
    await async_session.execute(
        text(
            """
            INSERT INTO focused_focus_sessions (
                user_id, google_event_id, google_calendar_id,
                google_ical_uid, google_updated_at,
                start_time, end_time, event_description,
                sha256_content_hash, status, version
            ) VALUES (
                :user_id, 'desc_ok', 'primary',
                'ical_desc_ok', now(),
                '2025-01-01 09:00:00+00', '2025-01-01 10:00:00+00',
                repeat('y', 8192),
                repeat('e', 64), 'active', 1
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()


@pytest.mark.asyncio
async def test_core_connections_empty_access_token_rejected(async_session: AsyncSession):
    """
    ck_encrypted_access_token_not_empty: disallow empty string.
    """
    user_id = await _create_test_user(async_session)

    with pytest.raises(IntegrityError) as exc_info:
        await async_session.execute(
            text(
                """
                INSERT INTO core_connections (
                    user_id, provider, encrypted_access_token,
                    token_expires_at, scopes
                ) VALUES (
                    :user_id, 'google', '',
                    now() + interval '1 hour',
                    ARRAY['scope1']::text[]
                )
                """
            ),
            {"user_id": user_id},
        )
        await async_session.commit()

    assert "ck_encrypted_access_token_not_empty" in str(exc_info.value)
    await async_session.rollback()


# ---------------------------------------------------------------------------
# 5. Timezone / timestamptz handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_focus_sessions_timestamps_are_timestamptz(async_session: AsyncSession):
    """
    start_time / end_time must be timestamp with time zone.
    """
    user_id = await _create_test_user(async_session)

    await async_session.execute(
        text(
            """
            INSERT INTO focused_focus_sessions (
                user_id, google_event_id, google_calendar_id,
                google_ical_uid, google_updated_at,
                start_time, end_time,
                sha256_content_hash, status, version
            ) VALUES (
                :user_id, 'tz_test', 'primary',
                'ical_tz', now(),
                '2025-01-01 09:00:00+00', '2025-01-01 10:00:00+00',
                repeat('f', 64), 'active', 1
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    result = await async_session.execute(
        text(
            """
            SELECT
                pg_typeof(start_time)::text AS type_start,
                pg_typeof(end_time)::text   AS type_end
            FROM focused_focus_sessions
            WHERE google_event_id = 'tz_test'
            """
        )
    )
    row = result.first()
    assert row.type_start == "timestamp with time zone"
    assert row.type_end == "timestamp with time zone"


# ---------------------------------------------------------------------------
# 6. Foreign key behavior (CASCADE / RESTRICT)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_core_connections_fk_cascade_on_user_delete(async_session: AsyncSession):
    """
    core_connections.user_id -> core_users.id must CASCADE on delete.
    """
    user_id = await _create_test_user(async_session)

    await async_session.execute(
        text(
            """
            INSERT INTO core_connections (
                user_id, provider, encrypted_access_token,
                token_expires_at, scopes
            ) VALUES (
                :user_id, 'google', 'token',
                now() + interval '1 hour',
                ARRAY['scope1']::text[]
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    # Delete user
    await async_session.execute(
        text("DELETE FROM core_users WHERE id = :id"),
        {"id": user_id},
    )
    await async_session.commit()

    # Connection must be gone
    result = await async_session.execute(
        text(
            """
            SELECT COUNT(*) FROM core_connections
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    count = result.scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_focused_user_keywords_fk_cascade(async_session: AsyncSession):
    """
    focused_user_keywords.user_id -> core_users.id must CASCADE on delete.
    """
    user_id = await _create_test_user(async_session)

    await async_session.execute(
        text(
            """
            INSERT INTO focused_user_keywords (user_id, keyword, created_at)
            VALUES (:user_id, 'deep work', now())
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    await async_session.execute(
        text("DELETE FROM core_users WHERE id = :id"),
        {"id": user_id},
    )
    await async_session.commit()

    result = await async_session.execute(
        text(
            """
            SELECT COUNT(*) FROM focused_user_keywords
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    count = result.scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_focus_sessions_fk_restrict_on_user_delete(async_session: AsyncSession):
    """
    focused_focus_sessions.user_id -> core_users.id must RESTRICT on delete.
    """
    user_id = await _create_test_user(async_session)

    await async_session.execute(
        text(
            """
            INSERT INTO focused_focus_sessions (
                user_id, google_event_id, google_calendar_id,
                google_ical_uid, google_updated_at,
                start_time, end_time,
                sha256_content_hash, status, version
            ) VALUES (
                :user_id, 'restrict_test', 'primary',
                'ical_restrict', now(),
                '2025-01-01 09:00:00+00', '2025-01-01 10:00:00+00',
                repeat('g', 64), 'active', 1
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    with pytest.raises(IntegrityError):
        await async_session.execute(
            text("DELETE FROM core_users WHERE id = :id"),
            {"id": user_id},
        )
        await async_session.commit()

    await async_session.rollback()


# ---------------------------------------------------------------------------
# 7. Webhook and provider_metadata fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_core_connections_webhook_fields(async_session: AsyncSession):
    """
    google_channel_* fields must accept values and persist.
    """
    user_id = await _create_test_user(async_session)

    await async_session.execute(
        text(
            """
            INSERT INTO core_connections (
                user_id, provider, encrypted_access_token,
                token_expires_at, scopes,
                google_channel_id, google_resource_id, google_channel_expires_at
            ) VALUES (
                :user_id, 'google', 'token',
                now() + interval '1 hour',
                ARRAY['scope1']::text[],
                'channel_abc', 'resource_xyz', now() + interval '7 days'
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    result = await async_session.execute(
        text(
            """
            SELECT google_channel_id, google_resource_id, google_channel_expires_at
            FROM core_connections
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    row = result.first()
    assert row.google_channel_id == "channel_abc"
    assert row.google_resource_id == "resource_xyz"
    assert row.google_channel_expires_at is not None


@pytest.mark.asyncio
async def test_core_connections_provider_metadata_json(async_session: AsyncSession):
    """
    provider_metadata must store JSON and be queryable.
    """
    user_id = await _create_test_user(async_session)

    await async_session.execute(
        text(
            """
            INSERT INTO core_connections (
                user_id, provider, encrypted_access_token,
                token_expires_at, scopes, provider_metadata
            ) VALUES (
                :user_id, 'google', 'token',
                now() + interval '1 hour',
                ARRAY['scope1']::text[],
                '{"calendar_id": "primary", "sync_enabled": true}'::jsonb
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    result = await async_session.execute(
        text(
            """
            SELECT provider_metadata->>'calendar_id' AS cal_id,
                   (provider_metadata->>'sync_enabled')::boolean AS sync_enabled
            FROM core_connections
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    row = result.first()
    assert row.cal_id == "primary"
    assert row.sync_enabled is True


# ---------------------------------------------------------------------------
# 8. Soft delete pattern & last_synced_at
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_focus_sessions_soft_delete_pattern(async_session: AsyncSession):
    """
    Soft delete = status='deleted' + deleted_at NOT NULL.
    """
    user_id = await _create_test_user(async_session)

    await async_session.execute(
        text(
            """
            INSERT INTO focused_focus_sessions (
                user_id, google_event_id, google_calendar_id,
                google_ical_uid, google_updated_at,
                start_time, end_time,
                sha256_content_hash, status, version
            ) VALUES (
                :user_id, 'soft_delete', 'primary',
                'ical_soft', now(),
                '2025-01-01 09:00:00+00', '2025-01-01 10:00:00+00',
                repeat('h', 64), 'active', 1
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    await async_session.execute(
        text(
            """
            UPDATE focused_focus_sessions
            SET status = 'deleted', deleted_at = now()
            WHERE google_event_id = 'soft_delete'
            """
        )
    )
    await async_session.commit()

    result = await async_session.execute(
        text(
            """
            SELECT status, deleted_at
            FROM focused_focus_sessions
            WHERE google_event_id = 'soft_delete'
            """
        )
    )
    row = result.first()
    assert row.status == "deleted"
    assert row.deleted_at is not None


@pytest.mark.asyncio
async def test_focus_sessions_last_synced_at_nullable_and_settable(async_session: AsyncSession):
    """
    last_synced_at must be NULL by default and manually settable.
    """
    user_id = await _create_test_user(async_session)

    await async_session.execute(
        text(
            """
            INSERT INTO focused_focus_sessions (
                user_id, google_event_id, google_calendar_id,
                google_ical_uid, google_updated_at,
                start_time, end_time,
                sha256_content_hash, status, version
            ) VALUES (
                :user_id, 'sync_test', 'primary',
                'ical_sync', now(),
                '2025-01-01 09:00:00+00', '2025-01-01 10:00:00+00',
                repeat('i', 64), 'active', 1
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    # Initially NULL
    result = await async_session.execute(
        text(
            """
            SELECT last_synced_at FROM focused_focus_sessions
            WHERE google_event_id = 'sync_test'
            """
        )
    )
    assert result.scalar_one() is None

    # Set explicitly
    await async_session.execute(
        text(
            """
            UPDATE focused_focus_sessions
            SET last_synced_at = now()
            WHERE google_event_id = 'sync_test'
            """
        )
    )
    await async_session.commit()

    result = await async_session.execute(
        text(
            """
            SELECT last_synced_at FROM focused_focus_sessions
            WHERE google_event_id = 'sync_test'
            """
        )
    )
    assert result.scalar_one() is not None


# ---------------------------------------------------------------------------
# 9. Edge cases: scopes array, NULL vs empty description, oauth_state defaults
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_core_connections_empty_scopes_array(async_session: AsyncSession):
    """
    scopes array must accept empty array (even if semantically odd).
    """
    user_id = await _create_test_user(async_session)

    await async_session.execute(
        text(
            """
            INSERT INTO core_connections (
                user_id, provider, encrypted_access_token,
                token_expires_at, scopes
            ) VALUES (
                :user_id, 'google', 'token',
                now() + interval '1 hour',
                ARRAY[]::text[]
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    result = await async_session.execute(
        text(
            """
            SELECT array_length(scopes, 1) AS len
            FROM core_connections
            WHERE user_id = :user_id
            """
        ),
        {"user_id": user_id},
    )
    length = result.scalar_one()
    # array_length returns NULL for empty array
    assert length is None


@pytest.mark.asyncio
async def test_focus_sessions_null_vs_empty_description(async_session: AsyncSession):
    """
    Both NULL and empty string descriptions must be allowed and distinct.
    """
    user_id = await _create_test_user(async_session)

    # NULL description
    await async_session.execute(
        text(
            """
            INSERT INTO focused_focus_sessions (
                user_id, google_event_id, google_calendar_id,
                google_ical_uid, google_updated_at,
                start_time, end_time, event_description,
                sha256_content_hash, status, version
            ) VALUES (
                :user_id, 'null_desc', 'primary',
                'ical_null', now(),
                '2025-01-01 09:00:00+00', '2025-01-01 10:00:00+00',
                NULL,
                repeat('j', 64), 'active', 1
            )
            """
        ),
        {"user_id": user_id},
    )

    # Empty string description
    await async_session.execute(
        text(
            """
            INSERT INTO focused_focus_sessions (
                user_id, google_event_id, google_calendar_id,
                google_ical_uid, google_updated_at,
                start_time, end_time, event_description,
                sha256_content_hash, status, version
            ) VALUES (
                :user_id, 'empty_desc', 'primary',
                'ical_empty', now(),
                '2025-01-01 09:00:00+00', '2025-01-01 10:00:00+00',
                '',
                repeat('k', 64), 'active', 1
            )
            """
        ),
        {"user_id": user_id},
    )
    await async_session.commit()

    result = await async_session.execute(
        text(
            """
            SELECT 
                google_event_id,
                event_description,
                event_description IS NULL AS is_null,
                length(event_description) AS len
            FROM focused_focus_sessions
            WHERE user_id = :user_id
            ORDER BY google_event_id
            """
        ),
        {"user_id": user_id},
    )
    rows = result.fetchall()

    null_row = next(r for r in rows if r.google_event_id == "null_desc")
    empty_row = next(r for r in rows if r.google_event_id == "empty_desc")

    assert null_row.is_null is True
    assert null_row.len is None

    assert empty_row.is_null is False
    assert empty_row.len == 0


@pytest.mark.asyncio
async def test_oauth_state_defaults_created_and_expires(async_session: AsyncSession):
    """
    oauth_state must set created_at = now()
    and expires_at ~ now() + 10 minutes (server-side default).
    """
    state_value = f"state_{uuid4()}"
    await async_session.execute(
        text(
            """
            INSERT INTO oauth_state (state)
            VALUES (:state)
            """
        ),
        {"state": state_value},
    )
    await async_session.commit()

    result = await async_session.execute(
        text(
            """
            SELECT created_at, expires_at
            FROM oauth_state
            WHERE state = :state
            """
        ),
        {"state": state_value},
    )
    row = result.first()
    assert row.created_at is not None
    assert row.expires_at is not None

    # Sanity check: expires_at should be after created_at
    assert row.expires_at > row.created_at
