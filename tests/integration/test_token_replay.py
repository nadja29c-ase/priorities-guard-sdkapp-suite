"""
Integration tests for Redis idempotent token replay (Increment 43).

Tests the full token exchange flow with Redis caching.

Integration tests (4 required):
1. Full exchange -> second within 30s -> same token response
2. Full exchange -> second after 30s (TTL expired) -> invalid_grant
3. Full exchange -> second with different client_id -> invalid_grant
4. Redis down -> first succeeds, second returns invalid_grant, no 500
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4

import pytest

from backend.core.models import CoreUser
from backend.core.oauth_provider.models import OAuthAuthorizationCode


@pytest.mark.integration
class TestTokenReplayIntegration:
    """Integration tests for token replay with real database."""

    @pytest.mark.asyncio
    async def test_duplicate_exchange_within_ttl_returns_same_response(
        self, async_session_factory, fake_redis_client
    ):
        """
        Test 1: Full exchange -> second within 30s -> same token response.

        Both requests should get identical access_token and refresh_token.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        client_id = "test-client-replay"
        code = f"auth_code_{uuid4()}"

        # Create user and auth code in database
        async with async_session_factory() as setup_session:
            user = CoreUser(chatgpt_user_id=f"test-user-{uuid4()}")
            setup_session.add(user)
            await setup_session.flush()
            user_id = user.id

            auth_code = OAuthAuthorizationCode(
                code=code,
                user_id=user_id,
                client_id=client_id,
                redirect_uri="https://example.com/callback",
                scope=["pg.access"],
                code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                code_challenge_method="S256",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                used=False,
            )
            setup_session.add(auth_code)
            await setup_session.commit()

        # First exchange - should succeed
        async with async_session_factory() as session1:
            result1 = await exchange_authorization_code(
                db=session1,
                code=code,
                code_verifier="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
                client_id=client_id,
                redirect_uri="https://example.com/callback",
                correlation_id="test-1"
            )

        assert isinstance(result1, dict), f"First exchange should succeed: {result1}"
        assert "access_token" in result1
        assert "refresh_token" in result1

        # Second exchange (within TTL) - should return cached response
        async with async_session_factory() as session2:
            result2 = await exchange_authorization_code(
                db=session2,
                code=code,
                code_verifier="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
                client_id=client_id,
                redirect_uri="https://example.com/callback",
                correlation_id="test-2"
            )

        # Should return same token response
        assert isinstance(result2, dict), f"Second exchange should return cached: {result2}"
        assert result2["access_token"] == result1["access_token"]
        assert result2["refresh_token"] == result1["refresh_token"]
        assert result2["expires_in"] == result1["expires_in"]
        assert result2["scope"] == result1["scope"]

    @pytest.mark.asyncio
    async def test_duplicate_exchange_after_ttl_returns_invalid_grant(
        self, async_session_factory, fake_redis_client
    ):
        """
        Test 2: Full exchange -> second after 30s (TTL expired) -> invalid_grant.

        After Redis TTL expires, duplicate requests fail with invalid_grant.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        client_id = "test-client-ttl"
        code = f"auth_code_{uuid4()}"

        # Create user and auth code in database
        async with async_session_factory() as setup_session:
            user = CoreUser(chatgpt_user_id=f"test-user-{uuid4()}")
            setup_session.add(user)
            await setup_session.flush()
            user_id = user.id

            auth_code = OAuthAuthorizationCode(
                code=code,
                user_id=user_id,
                client_id=client_id,
                redirect_uri="https://example.com/callback",
                scope=["pg.access"],
                code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                code_challenge_method="S256",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                used=False,
            )
            setup_session.add(auth_code)
            await setup_session.commit()

        # First exchange - should succeed
        async with async_session_factory() as session1:
            result1 = await exchange_authorization_code(
                db=session1,
                code=code,
                code_verifier="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
                client_id=client_id,
                redirect_uri="https://example.com/callback",
                correlation_id="test-1"
            )

        assert isinstance(result1, dict), f"First exchange should succeed: {result1}"

        # Simulate TTL expiration by advancing fake redis time
        fake_redis_client.advance_time(31)  # 31 seconds > 30s TTL

        # Second exchange (after TTL) - should fail
        async with async_session_factory() as session2:
            result2 = await exchange_authorization_code(
                db=session2,
                code=code,
                code_verifier="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
                client_id=client_id,
                redirect_uri="https://example.com/callback",
                correlation_id="test-2"
            )

        # Should return invalid_grant
        assert isinstance(result2, tuple), f"Expected error tuple after TTL: {result2}"
        assert result2[0] == "invalid_grant"
        assert "already used" in result2[1].lower()

    @pytest.mark.asyncio
    async def test_duplicate_exchange_different_client_id_returns_invalid_grant(
        self, async_session_factory, fake_redis_client
    ):
        """
        Test 3: Full exchange -> second with different client_id -> invalid_grant.

        Security: Cross-client replay attempts must fail.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        original_client_id = "original-client"
        attacker_client_id = "attacker-client"
        code = f"auth_code_{uuid4()}"

        # Create user and auth code in database
        async with async_session_factory() as setup_session:
            user = CoreUser(chatgpt_user_id=f"test-user-{uuid4()}")
            setup_session.add(user)
            await setup_session.flush()
            user_id = user.id

            auth_code = OAuthAuthorizationCode(
                code=code,
                user_id=user_id,
                client_id=original_client_id,
                redirect_uri="https://example.com/callback",
                scope=["pg.access"],
                code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                code_challenge_method="S256",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                used=False,
            )
            setup_session.add(auth_code)
            await setup_session.commit()

        # First exchange with original client
        async with async_session_factory() as session1:
            result1 = await exchange_authorization_code(
                db=session1,
                code=code,
                code_verifier="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
                client_id=original_client_id,
                redirect_uri="https://example.com/callback",
                correlation_id="test-1"
            )

        assert isinstance(result1, dict), f"First exchange should succeed: {result1}"

        # Second exchange with different client_id (attack attempt)
        async with async_session_factory() as session2:
            result2 = await exchange_authorization_code(
                db=session2,
                code=code,
                code_verifier="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
                client_id=attacker_client_id,  # Different client_id
                redirect_uri="https://example.com/callback",
                correlation_id="test-2"
            )

        # Should return invalid_grant (not the cached response)
        assert isinstance(result2, tuple), f"Cross-client replay should fail: {result2}"
        assert result2[0] == "invalid_grant"

    @pytest.mark.asyncio
    async def test_redis_down_first_succeeds_second_fails_no_500(
        self, async_session_factory
    ):
        """
        Test 4: Redis down -> first succeeds, second returns invalid_grant, no 500.

        Redis unavailability must not crash the service.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        client_id = "test-client-redis-down"
        code = f"auth_code_{uuid4()}"

        # Create user and auth code in database
        async with async_session_factory() as setup_session:
            user = CoreUser(chatgpt_user_id=f"test-user-{uuid4()}")
            setup_session.add(user)
            await setup_session.flush()
            user_id = user.id

            auth_code = OAuthAuthorizationCode(
                code=code,
                user_id=user_id,
                client_id=client_id,
                redirect_uri="https://example.com/callback",
                scope=["pg.access"],
                code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                code_challenge_method="S256",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                used=False,
            )
            setup_session.add(auth_code)
            await setup_session.commit()

        # Mock Redis that is completely unavailable
        broken_redis = MagicMock()
        broken_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        broken_redis.set = AsyncMock(side_effect=ConnectionError("Redis down"))
        broken_redis.delete = AsyncMock(side_effect=ConnectionError("Redis down"))

        with patch(
            "backend.core.oauth_provider.services.token_service.redis_client",
            broken_redis
        ):
            # First exchange - should succeed (Redis write failure swallowed)
            async with async_session_factory() as session1:
                result1 = await exchange_authorization_code(
                    db=session1,
                    code=code,
                    code_verifier="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
                    client_id=client_id,
                    redirect_uri="https://example.com/callback",
                    correlation_id="test-1"
                )

            # Should succeed despite Redis being down
            assert isinstance(result1, dict), f"First exchange should succeed: {result1}"
            assert "access_token" in result1

            # Second exchange - should return invalid_grant (Redis read failure)
            async with async_session_factory() as session2:
                result2 = await exchange_authorization_code(
                    db=session2,
                    code=code,
                    code_verifier="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
                    client_id=client_id,
                    redirect_uri="https://example.com/callback",
                    correlation_id="test-2"
                )

            # Should return invalid_grant (not 500/exception)
            assert isinstance(result2, tuple), f"Second should be error tuple: {result2}"
            assert result2[0] == "invalid_grant"
            assert "already used" in result2[1].lower()


@pytest.mark.integration
class TestConcurrentTokenReplayIntegration:
    """Tests for concurrent duplicate requests."""

    @pytest.mark.asyncio
    async def test_concurrent_duplicates_no_500(
        self, async_session_factory, fake_redis_client
    ):
        """
        Concurrent duplicate requests: no 500, at most one fresh token issued.

        Multiple concurrent requests with same auth code should not crash.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code

        client_id = "test-client-concurrent"
        code = f"auth_code_{uuid4()}"

        # Create user and auth code in database
        async with async_session_factory() as setup_session:
            user = CoreUser(chatgpt_user_id=f"test-user-{uuid4()}")
            setup_session.add(user)
            await setup_session.flush()
            user_id = user.id

            auth_code = OAuthAuthorizationCode(
                code=code,
                user_id=user_id,
                client_id=client_id,
                redirect_uri="https://example.com/callback",
                scope=["pg.access"],
                code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                code_challenge_method="S256",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                used=False,
            )
            setup_session.add(auth_code)
            await setup_session.commit()

        async def exchange_with_new_session(session_num: int):
            """Perform exchange with a fresh session."""
            async with async_session_factory() as session:
                result = await exchange_authorization_code(
                    db=session,
                    code=code,
                    code_verifier="dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
                    client_id=client_id,
                    redirect_uri="https://example.com/callback",
                    correlation_id=f"concurrent-{session_num}"
                )
                return result

        # Run 3 concurrent exchanges
        results = await asyncio.gather(
            exchange_with_new_session(1),
            exchange_with_new_session(2),
            exchange_with_new_session(3),
            return_exceptions=True
        )

        # Assert no exceptions (no 500s)
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0, f"No exceptions expected: {exceptions}"

        # Categorize results
        successes = [r for r in results if isinstance(r, dict) and "access_token" in r]
        failures = [r for r in results if isinstance(r, tuple) and r[0] == "invalid_grant"]

        # At least one should succeed, others should be invalid_grant or replayed success
        assert len(successes) >= 1, "At least one exchange should succeed"

        # All successes should have the same access_token (either first or replayed)
        if len(successes) > 1:
            first_token = successes[0]["access_token"]
            for s in successes[1:]:
                assert s["access_token"] == first_token, "All successes should return same token"
