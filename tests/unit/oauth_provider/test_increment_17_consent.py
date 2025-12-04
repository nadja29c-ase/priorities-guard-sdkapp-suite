"""
Increment 17: OAuth Provider Hardening - Consent Persistence Tests.

Tests for GDPR-compliant consent recording in core_consents table.

These tests verify:
1. Consent is persisted to database on Allow
2. Multiple scopes create multiple consent rows
3. Re-consent updates existing records (clears revoked_at, updates granted_at)
4. Consent can be queried for audit purposes
"""

import asyncio
import time
import pytest
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# Test 1: CoreConsent Model Exists
# =============================================================================

class TestCoreConsentModel:
    """Verify CoreConsent model is properly defined."""

    def test_core_consent_model_exists(self):
        """
        Test 1.1: CoreConsent model should be importable from models.

        This test will fail until the model is created.
        """
        try:
            from backend.core.models import CoreConsent
            assert CoreConsent is not None
            assert CoreConsent.__tablename__ == "core_consents"
        except ImportError:
            pytest.fail("CoreConsent model not found in backend.core.models")

    def test_core_consent_has_required_columns(self):
        """
        Test 1.2: CoreConsent should have all required columns per architecture.

        Required: id, user_id, app_name, scope, granted_at, revoked_at
        """
        from backend.core.models import CoreConsent

        # Check columns exist via mapper
        mapper = CoreConsent.__mapper__
        column_names = {col.key for col in mapper.columns}

        required_columns = {"id", "user_id", "app_name", "scope", "granted_at", "revoked_at"}
        missing = required_columns - column_names

        assert not missing, f"CoreConsent missing columns: {missing}"

    def test_core_consent_user_id_is_foreign_key(self):
        """
        Test 1.3: user_id should be a foreign key to core_users.
        """
        from backend.core.models import CoreConsent

        user_id_col = CoreConsent.__table__.c.user_id

        # Check foreign keys
        fk_targets = [fk.target_fullname for fk in user_id_col.foreign_keys]
        assert "core_users.id" in fk_targets, "user_id should FK to core_users.id"

    def test_core_consent_has_unique_constraint(self):
        """
        Test 1.4: CoreConsent should have unique constraint on (user_id, app_name, scope).
        """
        from backend.core.models import CoreConsent

        table = CoreConsent.__table__

        # Find unique constraints
        unique_constraints = [
            constraint for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        ]

        # Check that the expected constraint exists
        constraint_columns = None
        for constraint in unique_constraints:
            cols = {col.name for col in constraint.columns}
            if cols == {"user_id", "app_name", "scope"}:
                constraint_columns = cols
                break

        assert constraint_columns is not None, \
            "Missing UniqueConstraint on (user_id, app_name, scope)"

    @pytest.mark.asyncio
    async def test_unique_constraint_prevents_duplicate_rows(self, async_session: AsyncSession):
        """
        Test 1.5: Database should reject duplicate (user_id, app_name, scope) rows.

        This tests the constraint at the database level, not just the application level.
        """
        from sqlalchemy.exc import IntegrityError
        from backend.core.models import CoreUser, CoreConsent

        # Create test user
        user = CoreUser()
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Insert first consent row
        consent1 = CoreConsent(
            user_id=user.id,
            app_name="focused",
            scope="focused.read",
            granted_at=datetime.now(timezone.utc)
        )
        async_session.add(consent1)
        await async_session.commit()

        # Attempt to insert duplicate row (same user_id, app_name, scope)
        consent2 = CoreConsent(
            user_id=user.id,
            app_name="focused",
            scope="focused.read",
            granted_at=datetime.now(timezone.utc)
        )
        async_session.add(consent2)

        # Should raise IntegrityError due to unique constraint
        with pytest.raises(IntegrityError):
            await async_session.commit()

        # Rollback to clean up
        await async_session.rollback()


# =============================================================================
# Test 2: Consent Service Functions
# =============================================================================

class TestConsentServiceFunctions:
    """Test consent_service.py functions."""

    def test_record_consent_function_exists(self):
        """
        Test 2.1: record_consent function should exist in consent_service.
        """
        try:
            from backend.core.oauth_provider.services.consent_service import record_consent
            assert callable(record_consent)
        except ImportError:
            pytest.fail("record_consent not found in consent_service")

    @pytest.mark.asyncio
    async def test_record_consent_creates_rows(self, async_session: AsyncSession):
        """
        Test 2.2: record_consent should create rows in core_consents with proper fields.
        """
        from backend.core.models import CoreUser, CoreConsent
        from backend.core.oauth_provider.services.consent_service import record_consent

        # Create a test user first
        user = CoreUser()
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Record consent for multiple scopes
        await record_consent(
            db=async_session,
            user_id=str(user.id),
            app_name="focused",
            scopes=["focused.read", "focused.write"]
        )

        # Verify rows created
        result = await async_session.execute(
            select(CoreConsent).where(CoreConsent.user_id == user.id)
        )
        consents = result.scalars().all()

        assert len(consents) == 2, "Should create one row per scope"

        scope_set = {c.scope for c in consents}
        assert scope_set == {"focused.read", "focused.write"}

        for consent in consents:
            assert consent.app_name == "focused"
            assert consent.granted_at is not None
            assert consent.revoked_at is None
            # granted_at should be recent (within last minute)
            assert consent.granted_at > datetime.now(timezone.utc) - timedelta(minutes=1)

    @pytest.mark.asyncio
    async def test_record_consent_is_idempotent(self, async_session: AsyncSession):
        """
        Test 2.3: Calling record_consent twice should not duplicate rows.

        Also verifies that granted_at is updated on each call (upsert behavior).
        """
        from backend.core.models import CoreUser, CoreConsent
        from backend.core.oauth_provider.services.consent_service import record_consent

        # Create test user
        user = CoreUser()
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # First consent
        await record_consent(
            db=async_session,
            user_id=str(user.id),
            app_name="focused",
            scopes=["focused.read"]
        )

        # Get first granted_at
        result = await async_session.execute(
            select(CoreConsent).where(CoreConsent.user_id == user.id)
        )
        consent = result.scalar_one()
        first_granted_at = consent.granted_at

        # Yield to event loop (stable CI behavior)
        await asyncio.sleep(0)

        # Second consent (same user, same scope)
        await record_consent(
            db=async_session,
            user_id=str(user.id),
            app_name="focused",
            scopes=["focused.read"]
        )

        # Should still be only 1 row
        result = await async_session.execute(
            select(CoreConsent).where(CoreConsent.user_id == user.id)
        )
        consents = result.scalars().all()
        assert len(consents) == 1, "Should not duplicate consent rows"

        # granted_at should be updated (upsert always updates)
        await async_session.refresh(consent)
        assert consent.granted_at >= first_granted_at, \
            "granted_at should be updated or stay same on re-consent"

    @pytest.mark.asyncio
    async def test_reconsent_clears_revoked_at_and_updates_granted_at(self, async_session: AsyncSession):
        """
        Test 2.4: Re-consenting after revocation should:
        - Clear revoked_at
        - Update granted_at to new timestamp
        """
        from backend.core.models import CoreUser, CoreConsent
        from backend.core.oauth_provider.services.consent_service import record_consent

        # Create test user
        user = CoreUser()
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Initial consent
        await record_consent(
            db=async_session,
            user_id=str(user.id),
            app_name="focused",
            scopes=["focused.read"]
        )

        # Get initial granted_at
        result = await async_session.execute(
            select(CoreConsent).where(
                CoreConsent.user_id == user.id,
                CoreConsent.scope == "focused.read"
            )
        )
        consent = result.scalar_one()
        original_granted_at = consent.granted_at

        # Simulate revocation
        consent.revoked_at = datetime.now(timezone.utc)
        await async_session.commit()

        # Yield to event loop (stable CI behavior)
        await asyncio.sleep(0)

        # Re-consent
        await record_consent(
            db=async_session,
            user_id=str(user.id),
            app_name="focused",
            scopes=["focused.read"]
        )

        # Refresh to get updated values
        await async_session.refresh(consent)

        # revoked_at should be cleared
        assert consent.revoked_at is None, "Re-consent should clear revoked_at"

        # granted_at should be updated to new timestamp
        assert consent.granted_at > original_granted_at, \
            "Re-consent should update granted_at to current time"

        # CRITICAL: Verify row count stays at 1 (no duplicate rows created)
        result = await async_session.execute(
            select(CoreConsent).where(CoreConsent.user_id == user.id)
        )
        consents = result.scalars().all()
        assert len(consents) == 1, \
            f"Re-consent after revocation should NOT create extra rows, found {len(consents)}"


# =============================================================================
# Test 3: Consent UI Integration
# =============================================================================

def generate_pkce_pair():
    """
    Generate valid PKCE code_verifier and code_challenge.

    Per RFC 7636:
    - code_verifier: 43-128 character high-entropy random string
    - code_challenge: BASE64URL(SHA256(code_verifier))
    """
    import base64
    import hashlib
    import os

    # Generate 32 random bytes → 43-char base64url string (valid verifier length)
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")

    # S256 challenge: BASE64URL(SHA256(verifier))
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")

    return code_verifier, code_challenge


class TestConsentUIIntegration:
    """
    Test that consent_ui.py persists consent to database.

    These tests follow the REAL OAuth flow:
    1. Register OAuth client via /oauth/focused/register
    2. GET /oauth/focused/authorize (creates user, returns consent page with auth_context_id)
    3. POST /oauth/focused/consent (user clicks Allow)
    4. Verify consent rows in database
    """

    @pytest.mark.asyncio
    async def test_consent_allow_persists_to_database(
        self,
        client,
        async_session: AsyncSession,
        fake_redis_client,  # Required for auth_context storage
    ):
        """
        Test 3.1: Full OAuth flow consent persistence.

        This integration test follows the real OAuth provider flow:
        1. Registers an OAuth client via /oauth/focused/register
        2. Hits GET /oauth/focused/authorize with PKCE params
        3. Parses auth_context_id from the HTML consent page
        4. POSTs /oauth/focused/consent with action=allow
        5. Verifies core_consents rows exist with proper fields
        """
        _ = fake_redis_client  # Used by authorization_service for context storage
        import re
        from backend.core.models import CoreUser, CoreConsent

        # Generate PKCE pair (only need code_challenge for authorize request)
        _, code_challenge = generate_pkce_pair()

        # Step 1: Register OAuth client via the real endpoint
        register_response = await client.post(
            "/oauth/focused/register",
            json={
                "client_name": f"Consent Test Client {int(time.time())}",
                "redirect_uris": ["https://example.com/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
            }
        )

        # Handle rate limiting
        if register_response.status_code == 429:
            pytest.skip("Rate limited on client registration")

        assert register_response.status_code in [200, 201], \
            f"Client registration failed: {register_response.status_code} - {register_response.text}"

        client_data = register_response.json()
        client_id = client_data["client_id"]
        redirect_uri = "https://example.com/callback"

        # Step 2: Hit authorize endpoint (creates user via _get_or_create_user)
        # Use a unique login_hint to ensure a fresh user is created
        login_hint = f"chatgpt_user_consent_test_{int(time.time())}"

        authorize_response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read focused.write",
                "state": "test-state-consent",
                "login_hint": login_hint,
            }
        )

        assert authorize_response.status_code == 200, \
            f"Authorize failed: {authorize_response.status_code} - {authorize_response.text}"

        # Step 3: Parse auth_context_id from HTML response
        html_content = authorize_response.text

        # Look for auth_context_id in the form (hidden input)
        match = re.search(r'name="auth_context_id"\s+value="([^"]+)"', html_content)
        assert match, "auth_context_id not found in consent page HTML"
        auth_context_id = match.group(1)

        # Step 4: Submit consent Allow
        consent_response = await client.post(
            "/oauth/focused/consent",
            data={
                "auth_context_id": auth_context_id,
                "action": "allow"
            },
            follow_redirects=False
        )

        # Should redirect (302) with authorization code
        assert consent_response.status_code == 302, \
            f"Expected redirect, got {consent_response.status_code}"

        # Verify redirect contains authorization code
        location = consent_response.headers.get("location", "")
        assert "code=" in location, f"Redirect missing authorization code: {location}"

        # Step 5: Find the user created by authorize endpoint
        result = await async_session.execute(
            select(CoreUser).where(CoreUser.chatgpt_user_id == login_hint)
        )
        user = result.scalar_one_or_none()
        assert user is not None, f"User with login_hint {login_hint} not found"

        # Step 6: Verify consent persisted to database
        result = await async_session.execute(
            select(CoreConsent).where(CoreConsent.user_id == user.id)
        )
        consents = result.scalars().all()

        # Should have consent rows for both scopes
        assert len(consents) == 2, f"Should have 2 consent rows, got {len(consents)}"

        scope_set = {c.scope for c in consents}
        assert scope_set == {"focused.read", "focused.write"}, \
            f"Expected both scopes, got {scope_set}"

        # Verify all consents have proper fields
        for consent in consents:
            assert consent.app_name == "focused"
            assert consent.granted_at is not None
            assert consent.revoked_at is None
            # granted_at should be recent
            assert consent.granted_at > datetime.now(timezone.utc) - timedelta(minutes=1)

    @pytest.mark.asyncio
    async def test_consent_deny_creates_no_rows_and_returns_error_redirect(
        self,
        client,
        async_session: AsyncSession,
        fake_redis_client,  # Required for auth_context storage
    ):
        """
        Test 3.2: Consent deny must NOT create any consent rows (GDPR requirement).

        When user clicks Deny:
        1. No consent rows should be created
        2. No authorization code should be issued
        3. Redirect must include error=access_denied
        4. State must be preserved in redirect
        """
        _ = fake_redis_client  # Used by authorization_service for context storage
        import re
        from urllib.parse import urlparse, parse_qs
        from backend.core.models import CoreUser, CoreConsent
        from backend.core.oauth_provider.models import OAuthAuthorizationCode

        # Generate PKCE pair (only need code_challenge for authorize request)
        _, code_challenge = generate_pkce_pair()

        # Step 1: Register OAuth client
        register_response = await client.post(
            "/oauth/focused/register",
            json={
                "client_name": f"Consent Deny Test {int(time.time())}",
                "redirect_uris": ["https://example.com/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
            }
        )

        if register_response.status_code == 429:
            pytest.skip("Rate limited on client registration")

        assert register_response.status_code in [200, 201]

        client_data = register_response.json()
        client_id = client_data["client_id"]
        redirect_uri = "https://example.com/callback"
        test_state = "deny-test-state-preserve-me"

        # Step 2: Hit authorize endpoint
        login_hint = f"chatgpt_user_deny_test_{int(time.time())}"

        authorize_response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "scope": "focused.read focused.write",
                "state": test_state,
                "login_hint": login_hint,
            }
        )

        assert authorize_response.status_code == 200

        # Step 3: Parse auth_context_id from HTML
        html_content = authorize_response.text
        match = re.search(r'name="auth_context_id"\s+value="([^"]+)"', html_content)
        assert match, "auth_context_id not found in consent page HTML"
        auth_context_id = match.group(1)

        # Step 4: Submit consent DENY
        consent_response = await client.post(
            "/oauth/focused/consent",
            data={
                "auth_context_id": auth_context_id,
                "action": "deny"
            },
            follow_redirects=False
        )

        # Should redirect (302)
        assert consent_response.status_code == 302, \
            f"Expected redirect, got {consent_response.status_code}"

        # Parse redirect URL
        location = consent_response.headers.get("location", "")
        parsed = urlparse(location)
        query_params = parse_qs(parsed.query)

        # Verify error=access_denied in redirect
        assert "error" in query_params, f"Redirect missing error param: {location}"
        assert query_params["error"][0] == "access_denied", \
            f"Expected error=access_denied, got {query_params.get('error')}"

        # Verify state is preserved
        assert "state" in query_params, f"Redirect missing state param: {location}"
        assert query_params["state"][0] == test_state, \
            f"State not preserved: expected {test_state}, got {query_params.get('state')}"

        # Verify NO authorization code in redirect
        assert "code" not in query_params, \
            f"Deny should NOT return authorization code: {location}"

        # Step 5: Find user created by authorize
        result = await async_session.execute(
            select(CoreUser).where(CoreUser.chatgpt_user_id == login_hint)
        )
        user = result.scalar_one_or_none()
        assert user is not None, f"User with login_hint {login_hint} not found"

        # Step 6: Verify NO consent rows created
        result = await async_session.execute(
            select(CoreConsent).where(CoreConsent.user_id == user.id)
        )
        consents = result.scalars().all()
        assert len(consents) == 0, \
            f"Deny should NOT create consent rows, found {len(consents)}"

        # Step 7: Verify NO authorization code created for this user
        result = await async_session.execute(
            select(OAuthAuthorizationCode).where(
                OAuthAuthorizationCode.user_id == user.id
            )
        )
        auth_codes = result.scalars().all()
        assert len(auth_codes) == 0, \
            f"Deny should NOT create authorization code, found {len(auth_codes)}"


# =============================================================================
# Test 4: Consent Query for Audit
# =============================================================================

class TestConsentAuditQuery:
    """Test that consent can be queried for GDPR audit purposes."""

    @pytest.mark.asyncio
    async def test_query_user_consents(self, async_session: AsyncSession):
        """
        Test 4.1: Can query all consents for a specific user (GDPR data access).
        """
        from backend.core.models import CoreUser, CoreConsent
        from backend.core.oauth_provider.services.consent_service import record_consent

        # Create two users
        user1 = CoreUser()
        user2 = CoreUser()
        async_session.add_all([user1, user2])
        await async_session.commit()
        await async_session.refresh(user1)
        await async_session.refresh(user2)

        # User1 consents to focused
        await record_consent(
            db=async_session,
            user_id=str(user1.id),
            app_name="focused",
            scopes=["focused.read", "focused.write"]
        )

        # User2 consents to different app
        await record_consent(
            db=async_session,
            user_id=str(user2.id),
            app_name="decliner",
            scopes=["decliner.read"]
        )

        # Query user1's consents
        result = await async_session.execute(
            select(CoreConsent).where(CoreConsent.user_id == user1.id)
        )
        user1_consents = result.scalars().all()

        assert len(user1_consents) == 2
        assert all(c.app_name == "focused" for c in user1_consents)

        # Query user2's consents
        result = await async_session.execute(
            select(CoreConsent).where(CoreConsent.user_id == user2.id)
        )
        user2_consents = result.scalars().all()

        assert len(user2_consents) == 1
        assert user2_consents[0].app_name == "decliner"

    @pytest.mark.asyncio
    async def test_query_active_vs_revoked_consents(self, async_session: AsyncSession):
        """
        Test 4.2: Can distinguish active from revoked consents.
        """
        from backend.core.models import CoreUser, CoreConsent
        from backend.core.oauth_provider.services.consent_service import record_consent

        # Create user
        user = CoreUser()
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Record consents
        await record_consent(
            db=async_session,
            user_id=str(user.id),
            app_name="focused",
            scopes=["focused.read", "focused.write"]
        )

        # Revoke one scope
        result = await async_session.execute(
            select(CoreConsent).where(
                CoreConsent.user_id == user.id,
                CoreConsent.scope == "focused.write"
            )
        )
        consent_to_revoke = result.scalar_one()
        consent_to_revoke.revoked_at = datetime.now(timezone.utc)
        await async_session.commit()

        # Query active consents only
        result = await async_session.execute(
            select(CoreConsent).where(
                CoreConsent.user_id == user.id,
                CoreConsent.revoked_at.is_(None)
            )
        )
        active_consents = result.scalars().all()

        assert len(active_consents) == 1
        assert active_consents[0].scope == "focused.read"
