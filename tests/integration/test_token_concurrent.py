"""
Integration tests for concurrent token exchange (Increment 21).

Tests that FOR UPDATE row locking prevents concurrent refresh token
exploitation. Requires a real database that supports FOR UPDATE.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.core.encryption import encrypt_token, hash_refresh_token


@pytest.mark.integration
class TestConcurrentTokenExchange:
    """Integration tests for concurrent token exchange race conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_refresh_token_exchange_one_succeeds(
        self, async_session_factory
    ):
        """
        Concurrent refresh token exchanges: only one succeeds.

        This test validates the FOR UPDATE row locking by:
        1. Creating a valid token with a refresh token
        2. Launching two concurrent exchange_refresh_token calls
        3. Asserting exactly one succeeds and one fails

        IMPORTANT: Each call uses its own independent AsyncSession instance.
        If they share a session, they share a transaction and FOR UPDATE
        is never exercised.
        """
        from backend.core.oauth_provider.models import OAuthAccessToken
        from backend.core.oauth_provider.services.token_service import exchange_refresh_token

        # Setup: Create a valid refresh token
        user_id = uuid4()
        client_id = "test-client-concurrent"
        refresh_token_plain = "test_refresh_token_for_concurrent_" + str(uuid4())
        refresh_token_hashed = hash_refresh_token(refresh_token_plain)
        refresh_token_encrypted = encrypt_token(refresh_token_plain)

        # Create the token in the database
        async with async_session_factory() as setup_session:
            token_record = OAuthAccessToken(
                jti=str(uuid4()),
                user_id=user_id,
                client_id=client_id,
                scope=["focused.read"],
                token_type="Bearer",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                refresh_token_enc=refresh_token_encrypted,
                refresh_token_hash=refresh_token_hashed,
                refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                revoked=False,
            )
            setup_session.add(token_record)
            await setup_session.commit()
            original_token_jti = token_record.jti

        # Execute: Launch two concurrent exchange_refresh_token calls
        # CRITICAL: Each must use its own session
        async def exchange_with_new_session(session_num: int):
            """Perform exchange with a fresh session."""
            async with async_session_factory() as session:
                result = await exchange_refresh_token(
                    db=session,
                    refresh_token=refresh_token_plain,
                    client_id=client_id,
                    correlation_id=f"concurrent-test-{session_num}"
                )
                return result

        # Run both exchanges concurrently
        results = await asyncio.gather(
            exchange_with_new_session(1),
            exchange_with_new_session(2),
            return_exceptions=True
        )

        # Assert: Exactly one should succeed, one should fail
        successes = [r for r in results if isinstance(r, dict) and "access_token" in r]
        failures = [r for r in results if isinstance(r, tuple) and r[0] == "invalid_grant"]
        exceptions = [r for r in results if isinstance(r, Exception)]

        assert len(exceptions) == 0, f"Unexpected exceptions: {exceptions}"
        assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {successes}"
        assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}: {failures}"

        # The failure should be "Invalid refresh token" (because revoked=False filter excludes it)
        failure = failures[0]
        assert failure[0] == "invalid_grant"
        assert "refresh token" in failure[1].lower()

        # Verify only one new token was created
        async with async_session_factory() as verify_session:
            from sqlalchemy import select, func
            result = await verify_session.execute(
                select(func.count()).select_from(OAuthAccessToken).where(
                    OAuthAccessToken.user_id == user_id,
                    OAuthAccessToken.client_id == client_id
                )
            )
            token_count = result.scalar()

            # Should be 2: original (now revoked) + 1 new token
            assert token_count == 2, f"Expected 2 tokens (1 original + 1 new), got {token_count}"

            # Verify original is revoked
            original = await verify_session.execute(
                select(OAuthAccessToken).where(OAuthAccessToken.jti == original_token_jti)
            )
            original_token = original.scalar_one()
            assert original_token.revoked is True, "Original token should be revoked"
