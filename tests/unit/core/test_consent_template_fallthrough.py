"""
Tests for Consent Template Fallthrough Guard v2 (inc_consent_template_fallthrough_guard).

v2 addresses the defects found in v1 by adversarial review:
- Mixed known+unknown bypass (v1 used any() which only required one match)
- Late rejection leaving live Redis context
- Cross-app scope hiding (scopes filtered per-app, hiding granted cross-app scopes)

v2 fix: classify scopes ONCE, BEFORE auth context creation; thread app_name through.

Each test documents "what bug would still pass this test?"
"""

import logging
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.models import CoreConnection, CoreUser, CoreConsent
from backend.core.oauth_provider.authorize import classify_scopes, APP_PREFIX_MAPPING


# =============================================================================
# Tests 1-4: Unit tests for classify_scopes function
# =============================================================================

class TestClassifyScopes:
    """Tests for the classify_scopes helper that determines app from scopes."""

    def test_single_app_clarity_resolves_to_mindsort(self):
        """
        Test 1a: clarity.* scopes → MindSort, no unknown.

        Bug that would still pass: wrong app name for clarity prefix.
        """
        app_name, unknown = classify_scopes({"clarity.write"})
        assert app_name == "mindsort"
        assert unknown == set()

    def test_single_app_pg_resolves_to_priority_guardian(self):
        """
        Test 1b: pg.* scopes → Priority Guardian, no unknown.

        Bug that would still pass: wrong app name for pg prefix.
        """
        app_name, unknown = classify_scopes({"pg.access"})
        assert app_name == "priority_guardian"
        assert unknown == set()

    def test_single_app_focused_multi_scope_resolves_to_focused(self):
        """
        Test 1c: focused.* multi-scope set → Focused, no unknown.

        CRITICAL: Focused's legitimate three-scope set is ONE app, NOT multi-app.
        This is the most important non-regression for the v2 refactor.

        Bug that would still pass: Focused multi-scope wrongly treated as multi-app.
        """
        app_name, unknown = classify_scopes({"focused.read", "focused.write", "focused.notify"})
        assert app_name == "focused"
        assert unknown == set()

    def test_unknown_scope_present_with_known(self):
        """
        Test 2: Mixed known + unknown → unknown includes the unknown scope.

        This is the v1 bypass: any(clarity.) passed, widget.read was granted but hidden.
        v2 must detect and reject.

        Bug that would still pass: the v1 mixed known+unknown bypass.
        """
        app_name, unknown = classify_scopes({"clarity.write", "widget.read"})
        assert "widget.read" in unknown
        # app_name may be "mindsort" (the known scope's app) - what matters is unknown is detected

    def test_multi_app_scopes_returns_no_single_app(self):
        """
        Test 3: Scopes spanning multiple apps → no single app (None).

        Bug that would still pass: cross-app not detected.
        """
        app_name, unknown = classify_scopes({"pg.access", "clarity.write"})
        assert app_name is None  # Spans two apps
        assert unknown == set()  # Both are known, just multi-app

    def test_pure_unknown_scope_returns_no_app(self):
        """
        Test 4a: Pure unknown scope → no app, unknown includes it.

        Bug that would still pass: unknown-vs-multiapp conflation.
        """
        app_name, unknown = classify_scopes({"widget.read"})
        assert app_name is None  # No known app
        assert "widget.read" in unknown

    def test_empty_scope_set_returns_no_app_no_unknown(self):
        """
        Test 4b: Empty scope set → no app, no unknown.

        Bug that would still pass: empty set handling.
        """
        app_name, unknown = classify_scopes(set())
        assert app_name is None
        assert unknown == set()


# =============================================================================
# Tests 5-7: Integration tests for rejection behavior (before auth context)
# =============================================================================

class TestAuthorizeRejectsBeforeContext:
    """
    Tests that invalid scopes are rejected BEFORE auth context creation.

    These are REAL integration tests with DB clients. The key assertion is that
    create_authorization_context is NOT called when rejection happens.
    """

    @pytest_asyncio.fixture
    async def setup_mixed_known_unknown_client(self, async_session: AsyncSession):
        """
        Create OAuth client with mixed known + unknown scopes (synthetic fixture).

        CRITICAL: This client is a DIRECT DB INSERT, bypassing DCR. Normal DCR
        would reject widget.read as it's not in SUPPORTED_SCOPES. This tests
        defense-in-depth: the authorize guard must hold even for a client that
        should not exist.
        """
        client = CoreConnection(
            provider="mixed-test",
            connection_type="oauth_provider",
            client_id="mixed-client-id",
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code", "refresh_token"],
            scopes=["clarity.write", "widget.read"],  # Mixed: one known, one unknown
            encrypted_access_token="placeholder",
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        async_session.add(client)
        await async_session.commit()
        return client

    @pytest_asyncio.fixture
    async def setup_multi_app_client(self, async_session: AsyncSession):
        """
        Create OAuth client with scopes from multiple apps (DCR-LEGAL).

        Both pg.access and clarity.write are known scopes, so this IS registerable
        via normal DCR. This is the genuinely reachable mixed-app case.
        """
        client = CoreConnection(
            provider="multiapp-test",
            connection_type="oauth_provider",
            client_id="multiapp-client-id",
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code", "refresh_token"],
            scopes=["pg.access", "clarity.write"],  # Two apps, both known
            encrypted_access_token="placeholder",
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        async_session.add(client)
        await async_session.commit()
        return client

    @pytest_asyncio.fixture
    async def setup_pure_unknown_client(self, async_session: AsyncSession):
        """
        Create OAuth client with pure unknown scope (synthetic fixture).

        CRITICAL: This is a DIRECT DB INSERT. widget.read is not in SUPPORTED_SCOPES,
        so this cannot be registered via DCR. This tests defense-in-depth.
        """
        client = CoreConnection(
            provider="unknown-test",
            connection_type="oauth_provider",
            client_id="unknown-client-id",
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code", "refresh_token"],
            scopes=["widget.read"],  # Pure unknown
            encrypted_access_token="placeholder",
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        async_session.add(client)
        await async_session.commit()
        return client

    @pytest.mark.asyncio
    async def test_mixed_known_unknown_rejected_no_context(
        self, client, setup_mixed_known_unknown_client, fake_redis_client
    ):
        """
        Test 5: Mixed known+unknown → invalid_scope, AND no auth context created.

        This is the main v1 bypass being fixed. The client is a synthetic DB fixture
        (widget.read is not DCR-registerable), testing defense-in-depth.

        Bug that would still pass: findings 1 AND 2 together (bypass + late rejection).
        """
        _ = setup_mixed_known_unknown_client
        _ = fake_redis_client

        with patch(
            "backend.core.oauth_provider.authorize.create_authorization_context",
            new_callable=AsyncMock
        ) as mock_create_context:
            response = await client.get(
                "/oauth/mindsort/authorize",
                params={
                    "response_type": "code",
                    "client_id": "mixed-client-id",
                    "redirect_uri": "https://example.com/callback",
                    "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                    "code_challenge_method": "S256",
                    "scope": "clarity.write widget.read",  # Mixed: known + unknown
                    "state": "test-state",
                    "login_hint": "chatgpt-user-123",
                }
            )

        # Must be a redirect (302), NOT a 200 HTML page
        assert response.status_code == 302, (
            f"Expected redirect (302), got {response.status_code}"
        )

        # Must redirect with error=invalid_scope
        location = response.headers.get("location", "")
        assert "error=invalid_scope" in location, (
            f"Expected error=invalid_scope in redirect, got: {location}"
        )
        assert "state=test-state" in location, "State should be preserved in error redirect"

        # CRITICAL: No auth context created (v2 rejects BEFORE context creation)
        mock_create_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_multi_app_rejected_no_context(
        self, client, setup_multi_app_client, fake_redis_client
    ):
        """
        Test 6: Multi-app scopes → invalid_scope, no context.

        This client is DCR-LEGAL (both pg.access and clarity.write are known scopes).
        This is the genuinely reachable mixed-app case.

        Bug that would still pass: finding 3 (cross-app not detected at gate).
        """
        _ = setup_multi_app_client
        _ = fake_redis_client

        with patch(
            "backend.core.oauth_provider.authorize.create_authorization_context",
            new_callable=AsyncMock
        ) as mock_create_context:
            response = await client.get(
                "/oauth/pg/authorize",
                params={
                    "response_type": "code",
                    "client_id": "multiapp-client-id",
                    "redirect_uri": "https://example.com/callback",
                    "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                    "code_challenge_method": "S256",
                    "scope": "pg.access clarity.write",  # Two apps
                    "state": "test-state",
                    "login_hint": "chatgpt-user-123",
                }
            )

        assert response.status_code == 302
        location = response.headers.get("location", "")
        assert "error=invalid_scope" in location
        assert "state=test-state" in location

        # CRITICAL: No auth context created
        mock_create_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_pure_unknown_rejected_no_context_warning_logged(
        self, client, setup_pure_unknown_client, fake_redis_client, caplog
    ):
        """
        Test 7: Pure unknown scope → invalid_scope, no context, warning logged.

        This client is a synthetic DB fixture (widget.read is not DCR-registerable).
        This case is defense-in-depth, not normally reachable.

        Bug that would still pass: the ordering fix + the unknown guard.
        """
        _ = setup_pure_unknown_client
        _ = fake_redis_client

        caplog.set_level(logging.WARNING)

        with patch(
            "backend.core.oauth_provider.authorize.create_authorization_context",
            new_callable=AsyncMock
        ) as mock_create_context:
            response = await client.get(
                "/oauth/focused/authorize",
                params={
                    "response_type": "code",
                    "client_id": "unknown-client-id",
                    "redirect_uri": "https://example.com/callback",
                    "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                    "code_challenge_method": "S256",
                    "scope": "widget.read",  # Pure unknown
                    "state": "test-state",
                    "login_hint": "chatgpt-user-123",
                }
            )

        assert response.status_code == 302
        location = response.headers.get("location", "")
        assert "error=invalid_scope" in location

        # CRITICAL: No auth context created
        mock_create_context.assert_not_called()

        # Warning log must be present
        assert "unknown_scope_rejected" in caplog.text, (
            f"Expected oauth.authorize.unknown_scope_rejected warning. Got: {caplog.text}"
        )


# =============================================================================
# Test 8: Single-app screens still render correctly
# =============================================================================

class TestSingleAppScreensUnchanged:
    """
    Tests that valid single-app flows are unchanged by the v2 refactor.

    These are non-regression tests proving the classification refactor didn't
    break the happy path.
    """

    @pytest_asyncio.fixture
    async def setup_clarity_client(self, async_session: AsyncSession):
        """Create OAuth client with clarity.* scopes (MindSort AI)."""
        client = CoreConnection(
            provider="mindsort-test",
            connection_type="oauth_provider",
            client_id="mindsort-client-id",
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code", "refresh_token"],
            scopes=["clarity.write"],
            encrypted_access_token="placeholder",
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        async_session.add(client)
        await async_session.commit()
        return client

    @pytest_asyncio.fixture
    async def setup_pg_client(self, async_session: AsyncSession):
        """Create OAuth client with pg.* scopes (Priority Guardian)."""
        client = CoreConnection(
            provider="pg-test",
            connection_type="oauth_provider",
            client_id="pg-client-id",
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code", "refresh_token"],
            scopes=["pg.access"],
            encrypted_access_token="placeholder",
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        async_session.add(client)
        await async_session.commit()
        return client

    @pytest_asyncio.fixture
    async def setup_focused_client(self, async_session: AsyncSession):
        """Create OAuth client with focused.* scopes (Focused - legacy)."""
        client = CoreConnection(
            provider="focused-test",
            connection_type="oauth_provider",
            client_id="focused-client-id",
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code", "refresh_token"],
            scopes=["focused.read", "focused.write", "focused.notify"],
            encrypted_access_token="placeholder",
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        async_session.add(client)
        await async_session.commit()
        return client

    @pytest.mark.asyncio
    async def test_clarity_scope_renders_mindsort_screen(
        self, client, setup_clarity_client, fake_redis_client
    ):
        """
        Test 8a: clarity.write → MindSort AI screen unchanged.

        Bug that would still pass: the refactor breaking MindSort branding.
        """
        _ = setup_clarity_client
        _ = fake_redis_client

        response = await client.get(
            "/oauth/mindsort/authorize",
            params={
                "response_type": "code",
                "client_id": "mindsort-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "clarity.write",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        assert response.status_code == 200
        html = response.text
        assert "MindSort" in html, "Expected MindSort branding in consent page"

    @pytest.mark.asyncio
    async def test_pg_scope_renders_pg_screen(
        self, client, setup_pg_client, fake_redis_client
    ):
        """
        Test 8b: pg.access → Priority Guardian screen unchanged.

        Bug that would still pass: the refactor breaking PG branding.
        """
        _ = setup_pg_client
        _ = fake_redis_client

        response = await client.get(
            "/oauth/pg/authorize",
            params={
                "response_type": "code",
                "client_id": "pg-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "pg.access",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        assert response.status_code == 200
        html = response.text
        assert "Priority Guardian" in html, "Expected Priority Guardian branding"

    @pytest.mark.asyncio
    async def test_focused_multi_scope_renders_focused_screen(
        self, client, setup_focused_client, fake_redis_client
    ):
        """
        Test 8c: focused.* multi-scope → Focused screen, NOT rejected as multi-app.

        CRITICAL: This is the most important non-regression. Focused's legitimate
        three-scope set must still render, not be rejected as multi-app.

        Bug that would still pass: Focused multi-scope wrongly rejected.
        """
        _ = setup_focused_client
        _ = fake_redis_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "focused-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read focused.write focused.notify",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Must render (200), NOT reject (302)
        assert response.status_code == 200, (
            f"Focused multi-scope should render, not reject. Got {response.status_code}"
        )
        html = response.text
        assert "focused" in html.lower(), "Expected Focused-related content"


# =============================================================================
# Tests 9-10: consent_ui.py app_name threading + fallback
# =============================================================================

class TestConsentAppNameThreading:
    """
    Tests that app_name is threaded from auth context to consent record,
    with fallback for older contexts.
    """

    @pytest.mark.asyncio
    async def test_app_name_from_context_used_for_audit(self, async_session: AsyncSession):
        """
        Test 9: app_name threaded from context is used for the audit record.

        Auth context carrying app_name="mindsort" + scope clarity.write →
        record_consent called with app_name="mindsort", NOT re-derived.

        Bug that would still pass: screen-vs-audit divergence (finding 3's recorder half).
        """
        from sqlalchemy import select
        from backend.core.oauth_provider import consent_ui

        # Create test user
        user = CoreUser()
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Auth context WITH app_name (new deploy)
        auth_context = {
            "client_id": "mindsort-client-id",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "clarity.write",
            "redirect_uri": "https://example.com/callback",
            "user_id": str(user.id),
            "state": "test-state",
            "app_name": "mindsort",  # v2: threaded from authorize
        }

        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "ctx-id",
            "action": "allow",
        })
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        with patch.object(consent_ui, "check_rate_limit", new_callable=AsyncMock), \
             patch.object(consent_ui, "get_authorization_context", new_callable=AsyncMock, return_value=auth_context), \
             patch.object(consent_ui, "create_authorization_code", new_callable=AsyncMock, return_value="auth-code-xyz"), \
             patch.object(consent_ui, "get_session_cookie", return_value=None), \
             patch.object(consent_ui, "create_session", new_callable=AsyncMock, return_value="a" * 64), \
             patch.object(consent_ui, "set_session_cookie"):

            response = await consent_ui.consent_endpoint(mock_request, async_session)

        # Consent recorded with app_name from context (not re-derived)
        result = await async_session.execute(
            select(CoreConsent).where(CoreConsent.user_id == user.id)
        )
        consents = result.scalars().all()

        assert len(consents) == 1
        assert consents[0].app_name == "mindsort", (
            f"Expected app_name='mindsort' from context, got {consents[0].app_name!r}"
        )
        assert response.status_code == 302

    @pytest.mark.asyncio
    async def test_context_app_name_wins_over_scope_derivation(self, async_session: AsyncSession):
        """
        Test 9b: context app_name is USED, not re-derived from scopes.

        This is the DISCRIMINATING test that test 9 alone cannot provide. In test 9,
        the context app_name ("mindsort") happens to equal what the scope (clarity.write)
        would derive to - so test 9 passes whether the code uses the context value OR
        re-derives. Here we deliberately make them DISAGREE: context says
        "priority_guardian" but the scope is clarity.write (which derives to "mindsort").

        - If the code correctly USES the context app_name -> records "priority_guardian".
        - If the code (incorrectly) re-derives from the scope -> records "mindsort".
        Only the correct implementation passes.

        Bug that would still pass test 9 but FAILS here: consent_ui ignoring the
        threaded context app_name and always re-deriving from scope order.
        """
        from sqlalchemy import select
        from backend.core.oauth_provider import consent_ui

        user = CoreUser()
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Context app_name deliberately DISAGREES with what the scope would derive:
        # app_name="priority_guardian" but scope clarity.write derives to "mindsort".
        auth_context = {
            "client_id": "some-client-id",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "clarity.write",          # would derive to "mindsort"
            "redirect_uri": "https://example.com/callback",
            "user_id": str(user.id),
            "state": "test-state",
            "app_name": "priority_guardian",   # context says otherwise - MUST win
        }

        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "ctx-id",
            "action": "allow",
        })
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        with patch.object(consent_ui, "check_rate_limit", new_callable=AsyncMock), \
             patch.object(consent_ui, "get_authorization_context", new_callable=AsyncMock, return_value=auth_context), \
             patch.object(consent_ui, "create_authorization_code", new_callable=AsyncMock, return_value="auth-code-xyz"), \
             patch.object(consent_ui, "get_session_cookie", return_value=None), \
             patch.object(consent_ui, "create_session", new_callable=AsyncMock, return_value="a" * 64), \
             patch.object(consent_ui, "set_session_cookie"):

            response = await consent_ui.consent_endpoint(mock_request, async_session)

        result = await async_session.execute(
            select(CoreConsent).where(CoreConsent.user_id == user.id)
        )
        consents = result.scalars().all()

        assert len(consents) == 1
        assert consents[0].app_name == "priority_guardian", (
            "Context app_name must be USED, not re-derived from scope. "
            f"Got {consents[0].app_name!r} - if 'mindsort', the code is re-deriving "
            "from clarity.write instead of using the threaded context app_name."
        )
        assert response.status_code == 302

    @pytest.mark.asyncio
    async def test_fallback_path_missing_app_name_derives_unknown(
        self, async_session: AsyncSession, caplog
    ):
        """
        Test 10: Fallback path - context with app_name=None (older deploy).

        Context without app_name + unknown scope → _derive_app_name_from_scopes
        returns "unknown", consent recorded under "unknown", warning logged,
        flow completes (302).

        Bug that would still pass: the fallback regressing to "focused" or blocking.
        """
        from sqlalchemy import select
        from backend.core.oauth_provider import consent_ui

        caplog.set_level(logging.WARNING)

        # Create test user
        user = CoreUser()
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Auth context WITHOUT app_name (old deploy during rolling update)
        auth_context = {
            "client_id": "widget-client-id",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "widget.read",  # Unknown scope
            "redirect_uri": "https://example.com/callback",
            "user_id": str(user.id),
            "state": "test-state",
            # NO app_name key - simulates old deploy
        }

        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation-id"
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "ctx-id",
            "action": "allow",
        })
        mock_request.headers = {}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        with patch.object(consent_ui, "check_rate_limit", new_callable=AsyncMock), \
             patch.object(consent_ui, "get_authorization_context", new_callable=AsyncMock, return_value=auth_context), \
             patch.object(consent_ui, "create_authorization_code", new_callable=AsyncMock, return_value="auth-code-xyz"), \
             patch.object(consent_ui, "get_session_cookie", return_value=None), \
             patch.object(consent_ui, "create_session", new_callable=AsyncMock, return_value="a" * 64), \
             patch.object(consent_ui, "set_session_cookie"):

            response = await consent_ui.consent_endpoint(mock_request, async_session)

        # Consent recorded with "unknown" (derived via fallback)
        result = await async_session.execute(
            select(CoreConsent).where(CoreConsent.user_id == user.id)
        )
        consents = result.scalars().all()

        assert len(consents) == 1
        assert consents[0].app_name == "unknown", (
            f"Expected fallback to derive 'unknown', got {consents[0].app_name!r}"
        )

        # Warning logged for unknown app
        assert "unknown_app_scope" in caplog.text, (
            f"Expected oauth.consent.unknown_app_scope warning. Got: {caplog.text}"
        )

        # Flow completes (recorder never blocks)
        assert response.status_code == 302
        assert "error=" not in response.headers.get("location", ""), (
            "Unknown app at the recorder must NOT block the flow"
        )
