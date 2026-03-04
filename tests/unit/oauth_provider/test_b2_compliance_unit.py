"""
B2-5 + B2-8 Compliance Unit Tests (Increment 35).

Tests RFC 9728 B2-5 (resource parameter) and B2-8 (redirect URI allowlist)
at the unit level with mocked dependencies.

B2-5 Tests:
1. resource stored correctly in auth context when provided
2. resource absent -> context has resource=None, no error
3. create_access_token() with resource provided -> JWT aud equals resource value
4. create_access_token() with resource=None -> JWT aud equals OAUTH_ISSUER
5. create_access_token() called during refresh with resource on OAuthAccessToken -> JWT aud equals that resource value
6. Token exchange: auth_code.resource set, /token omits resource -> aud = auth_code.resource
7. Token exchange: auth_code.resource set, /token sends matching resource -> aud = auth_code.resource
8. Token exchange: auth_code.resource set, /token sends different resource -> 400 invalid_request
9. Token exchange: auth_code.resource NULL, /token sends resource -> aud = token resource value, stored on OAuthAccessToken
10. Token exchange: auth_code.resource NULL, /token omits resource -> aud = OAUTH_ISSUER
11. validate_jwt() accepts token where aud = app's own MCP server URL (exact match)
12. validate_jwt() accepts token where aud = OAUTH_ISSUER (exact match, backward compat)
13. validate_jwt() rejects token where aud is neither - exact equality enforced
14. validate_jwt() rejects token where aud = a different app's MCP server URL

B2-8 Tests:
1. validate_redirect_uris() with https://chatgpt.com/connector_platform_oauth_redirect -> valid
2. validate_redirect_uris() with https://platform.openai.com/apps-manage/oauth -> valid
3. validate_redirect_uris() with both URIs in one registration -> valid
4. validate_redirect_uris() with arbitrary HTTPS URI -> rejected
5. validate_redirect_uris() with HTTP URI -> rejected
6. validate_redirect_uris() with empty list -> rejected
7. Custom allowlist passed in -> only those URIs accepted
8. Subdomain of allowed URI (e.g. https://sub.chatgpt.com/...) -> rejected
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

import jwt as pyjwt
from jose import jwt


# =============================================================================
# B2-5: Resource Parameter Unit Tests
# =============================================================================

class TestResourceInAuthContext:
    """Test resource parameter handling in authorization context."""

    @pytest.mark.asyncio
    async def test_resource_stored_in_auth_context_when_provided(self):
        """
        Test 1: resource stored correctly in auth context when provided.

        The authorization context stores resource and retrieves it correctly.
        """
        from backend.core.oauth_provider.services.authorization_service import (
            create_authorization_context,
            get_authorization_context
        )
        from uuid import uuid4

        # Create auth context with resource
        resource_url = "https://mcp.priority-guard.com"

        # Mock Redis client
        with patch("backend.core.oauth_provider.services.authorization_service.redis_client") as mock_redis:
            mock_redis.set = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)  # Will be overwritten below
            mock_redis.delete = AsyncMock()

            # Track what gets stored
            stored_data = {}

            async def mock_set(key, value, ex=None):
                stored_data[key] = value
                return True

            async def mock_get(key):
                return stored_data.get(key)

            mock_redis.set = mock_set
            mock_redis.get = mock_get

            auth_context_id = await create_authorization_context(
                client_id="test-client",
                client_name="Test Client",
                redirect_uri="https://chatgpt.com/callback",
                scope="pg.access",
                code_challenge="test-challenge",
                code_challenge_method="S256",
                user_id=str(uuid4()),
                state="test-state",
                resource=resource_url
            )

            # Retrieve context
            context = await get_authorization_context(auth_context_id, delete_after_read=False)

            assert context is not None
            assert context["resource"] == resource_url

    @pytest.mark.asyncio
    async def test_resource_absent_context_has_empty_string(self):
        """
        Test 2: resource absent -> context has resource="" (empty string), no error.
        """
        from backend.core.oauth_provider.services.authorization_service import (
            create_authorization_context,
            get_authorization_context
        )
        from uuid import uuid4

        # Mock Redis client
        with patch("backend.core.oauth_provider.services.authorization_service.redis_client") as mock_redis:
            stored_data = {}

            async def mock_set(key, value, ex=None):
                stored_data[key] = value
                return True

            async def mock_get(key):
                return stored_data.get(key)

            mock_redis.set = mock_set
            mock_redis.get = mock_get
            mock_redis.delete = AsyncMock()

            auth_context_id = await create_authorization_context(
                client_id="test-client",
                client_name="Test Client",
                redirect_uri="https://chatgpt.com/callback",
                scope="pg.access",
                code_challenge="test-challenge",
                code_challenge_method="S256",
                user_id=str(uuid4()),
                state="test-state"
                # resource not provided
            )

            # Retrieve context
            context = await get_authorization_context(auth_context_id, delete_after_read=False)

            # Should have resource key with empty string (normalized from None)
            assert context is not None
            assert "resource" in context
            assert context["resource"] == ""


class TestCreateAccessTokenAudience:
    """Test JWT audience claim based on resource parameter."""

    def test_create_access_token_with_resource_uses_resource_as_aud(self):
        """
        Test 3: create_access_token() with resource provided -> JWT aud equals resource value.
        """
        from backend.core.oauth_provider.jwt.utils import create_access_token
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        user_id = uuid4()
        client_id = "test-client"
        scope = "pg.access"
        resource_url = "https://mcp.priority-guard.com"

        # Create token with resource
        access_token, jti = create_access_token(
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            resource=resource_url
        )

        # Decode without verification to check claims
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        decoded = jwt.decode(
            access_token,
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        assert decoded["aud"] == resource_url, "aud should equal resource URL"

    def test_create_access_token_without_resource_uses_issuer_as_aud(self):
        """
        Test 4: create_access_token() with resource=None -> JWT aud equals OAUTH_ISSUER.
        """
        from backend.core.oauth_provider.jwt.utils import create_access_token
        from backend.core.config import settings
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        user_id = uuid4()
        client_id = "test-client"
        scope = "pg.access"

        # Create token without resource (None)
        access_token, jti = create_access_token(
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            resource=None  # Explicitly None
        )

        # Decode without verification to check claims
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        decoded = jwt.decode(
            access_token,
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        assert decoded["aud"] == settings.OAUTH_ISSUER, \
            f"aud should equal OAUTH_ISSUER ({settings.OAUTH_ISSUER})"


class TestTokenExchangeResourceResolution:
    """Test resource resolution rules during token exchange."""

    @pytest.mark.asyncio
    async def test_auth_code_resource_set_token_omits_uses_auth_code_resource(self):
        """
        Test 6: Token exchange: auth_code.resource set, /token omits resource -> aud = auth_code.resource.

        Rule 1: Downgrade protection - cannot remove resource.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code
        from backend.core.oauth_provider.models import OAuthAuthorizationCode
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        # Setup mock auth code WITH resource
        auth_code_resource = "https://mcp.priority-guard.com"
        user_id = uuid4()

        mock_auth_code = MagicMock(spec=OAuthAuthorizationCode)
        mock_auth_code.code = "test-code"
        mock_auth_code.user_id = user_id
        mock_auth_code.client_id = "test-client"
        mock_auth_code.redirect_uri = "https://chatgpt.com/callback"
        mock_auth_code.scope = ["pg.access"]
        mock_auth_code.code_challenge = "test-challenge"
        mock_auth_code.resource = auth_code_resource  # HAS resource
        mock_auth_code.used = False
        mock_auth_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        # Mock DB
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_auth_code
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        # Mock PKCE verification to pass
        with patch("backend.core.oauth_provider.services.token_service.verify_pkce", return_value=True):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test-code",
                code_verifier="test-verifier",
                client_id="test-client",
                redirect_uri="https://chatgpt.com/callback",
                resource=None  # /token OMITS resource
            )

        # Should succeed
        assert isinstance(result, dict), f"Expected success dict, got: {result}"
        assert "access_token" in result

        # Decode JWT to verify audience
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        decoded = jwt.decode(
            result["access_token"],
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        assert decoded["aud"] == auth_code_resource, \
            "aud should equal auth_code.resource (downgrade protection)"

    @pytest.mark.asyncio
    async def test_auth_code_resource_set_token_sends_matching_resource(self):
        """
        Test 7: Token exchange: auth_code.resource set, /token sends matching resource -> aud = auth_code.resource.

        Rule 2: Matching resource is accepted.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code
        from backend.core.oauth_provider.models import OAuthAuthorizationCode
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        # Setup mock auth code WITH resource
        auth_code_resource = "https://mcp.priority-guard.com"
        user_id = uuid4()

        mock_auth_code = MagicMock(spec=OAuthAuthorizationCode)
        mock_auth_code.code = "test-code"
        mock_auth_code.user_id = user_id
        mock_auth_code.client_id = "test-client"
        mock_auth_code.redirect_uri = "https://chatgpt.com/callback"
        mock_auth_code.scope = ["pg.access"]
        mock_auth_code.code_challenge = "test-challenge"
        mock_auth_code.resource = auth_code_resource
        mock_auth_code.used = False
        mock_auth_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        # Mock DB
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_auth_code
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        with patch("backend.core.oauth_provider.services.token_service.verify_pkce", return_value=True):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test-code",
                code_verifier="test-verifier",
                client_id="test-client",
                redirect_uri="https://chatgpt.com/callback",
                resource=auth_code_resource  # MATCHING resource
            )

        # Should succeed
        assert isinstance(result, dict), f"Expected success dict, got: {result}"

        # Decode JWT to verify audience
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        decoded = jwt.decode(
            result["access_token"],
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        assert decoded["aud"] == auth_code_resource, "aud should equal matching resource"

    @pytest.mark.asyncio
    async def test_auth_code_resource_set_token_sends_different_resource_error(self):
        """
        Test 8: Token exchange: auth_code.resource set, /token sends different resource -> 400 invalid_request.

        Rule 3: Cannot change resource.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code
        from backend.core.oauth_provider.models import OAuthAuthorizationCode

        # Setup mock auth code WITH resource
        auth_code_resource = "https://mcp.priority-guard.com"
        different_resource = "https://different.example.com"
        user_id = uuid4()

        mock_auth_code = MagicMock(spec=OAuthAuthorizationCode)
        mock_auth_code.code = "test-code"
        mock_auth_code.user_id = user_id
        mock_auth_code.client_id = "test-client"
        mock_auth_code.redirect_uri = "https://chatgpt.com/callback"
        mock_auth_code.scope = ["pg.access"]
        mock_auth_code.code_challenge = "test-challenge"
        mock_auth_code.resource = auth_code_resource
        mock_auth_code.used = False
        mock_auth_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        # Mock DB
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_auth_code
        mock_db.execute.return_value = mock_result

        with patch("backend.core.oauth_provider.services.token_service.verify_pkce", return_value=True):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test-code",
                code_verifier="test-verifier",
                client_id="test-client",
                redirect_uri="https://chatgpt.com/callback",
                resource=different_resource  # DIFFERENT resource
            )

        # Should return error tuple
        assert isinstance(result, tuple), f"Expected error tuple, got: {result}"
        assert result[0] == "invalid_request", f"Error should be invalid_request, got: {result[0]}"
        assert "mismatch" in result[1].lower(), f"Error message should mention mismatch: {result[1]}"

    @pytest.mark.asyncio
    async def test_auth_code_no_resource_token_sends_resource_accepted(self):
        """
        Test 9: Token exchange: auth_code.resource NULL, /token sends resource -> aud = token resource value.

        Rule 4: Token can introduce resource when auth code has none.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code
        from backend.core.oauth_provider.models import OAuthAuthorizationCode, OAuthAccessToken
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        # Setup mock auth code WITHOUT resource
        token_resource = "https://mcp.priority-guard.com"
        user_id = uuid4()

        mock_auth_code = MagicMock(spec=OAuthAuthorizationCode)
        mock_auth_code.code = "test-code"
        mock_auth_code.user_id = user_id
        mock_auth_code.client_id = "test-client"
        mock_auth_code.redirect_uri = "https://chatgpt.com/callback"
        mock_auth_code.scope = ["pg.access"]
        mock_auth_code.code_challenge = "test-challenge"
        mock_auth_code.resource = None  # NO resource on auth code
        mock_auth_code.used = False
        mock_auth_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        # Mock DB - capture what gets added
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_auth_code
        mock_db.execute.return_value = mock_result
        added_tokens = []
        mock_db.add = MagicMock(side_effect=lambda x: added_tokens.append(x))
        mock_db.commit = AsyncMock()

        with patch("backend.core.oauth_provider.services.token_service.verify_pkce", return_value=True):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test-code",
                code_verifier="test-verifier",
                client_id="test-client",
                redirect_uri="https://chatgpt.com/callback",
                resource=token_resource  # Token INTRODUCES resource
            )

        # Should succeed
        assert isinstance(result, dict), f"Expected success dict, got: {result}"

        # Decode JWT to verify audience
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        decoded = jwt.decode(
            result["access_token"],
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        assert decoded["aud"] == token_resource, "aud should equal token-introduced resource"

        # Verify resource stored on OAuthAccessToken
        assert len(added_tokens) == 1, "Should have added one token record"
        stored_token = added_tokens[0]
        assert isinstance(stored_token, OAuthAccessToken)
        assert stored_token.resource == token_resource, \
            "OAuthAccessToken.resource should be stored"

    @pytest.mark.asyncio
    async def test_auth_code_no_resource_token_omits_resource_fallback_to_issuer(self):
        """
        Test 10: Token exchange: auth_code.resource NULL, /token omits resource -> aud = OAUTH_ISSUER.

        Rule 5: Fall back to OAUTH_ISSUER when neither has resource.
        """
        from backend.core.oauth_provider.services.token_service import exchange_authorization_code
        from backend.core.oauth_provider.models import OAuthAuthorizationCode
        from backend.core.config import settings
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        # Setup mock auth code WITHOUT resource
        user_id = uuid4()

        mock_auth_code = MagicMock(spec=OAuthAuthorizationCode)
        mock_auth_code.code = "test-code"
        mock_auth_code.user_id = user_id
        mock_auth_code.client_id = "test-client"
        mock_auth_code.redirect_uri = "https://chatgpt.com/callback"
        mock_auth_code.scope = ["pg.access"]
        mock_auth_code.code_challenge = "test-challenge"
        mock_auth_code.resource = None  # NO resource
        mock_auth_code.used = False
        mock_auth_code.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        # Mock DB
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_auth_code
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        with patch("backend.core.oauth_provider.services.token_service.verify_pkce", return_value=True):
            result = await exchange_authorization_code(
                db=mock_db,
                code="test-code",
                code_verifier="test-verifier",
                client_id="test-client",
                redirect_uri="https://chatgpt.com/callback",
                resource=None  # /token also omits resource
            )

        # Should succeed
        assert isinstance(result, dict), f"Expected success dict, got: {result}"

        # Decode JWT to verify audience
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        decoded = jwt.decode(
            result["access_token"],
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        assert decoded["aud"] == settings.OAUTH_ISSUER, \
            f"aud should fall back to OAUTH_ISSUER ({settings.OAUTH_ISSUER})"


class TestRefreshTokenResourcePreservation:
    """Test that refresh tokens preserve resource for JWT aud claim."""

    @pytest.mark.asyncio
    async def test_refresh_token_preserves_resource_in_jwt_aud(self):
        """
        Test 5: create_access_token() called during refresh with resource on OAuthAccessToken -> JWT aud equals that resource value.
        """
        from backend.core.oauth_provider.services.token_service import exchange_refresh_token
        from backend.core.oauth_provider.models import OAuthAccessToken
        from backend.core.encryption import encrypt_token, hash_refresh_token
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization
        import secrets

        # Setup mock token record WITH resource
        original_resource = "https://mcp.priority-guard.com"
        user_id = uuid4()
        refresh_token_plain = secrets.token_urlsafe(32)

        mock_token = MagicMock(spec=OAuthAccessToken)
        mock_token.jti = str(uuid4())
        mock_token.user_id = user_id
        mock_token.client_id = "test-client"
        mock_token.scope = ["pg.access"]
        mock_token.resource = original_resource  # HAS resource
        mock_token.refresh_token_enc = encrypt_token(refresh_token_plain)
        mock_token.refresh_token_hash = hash_refresh_token(refresh_token_plain)
        mock_token.refresh_token_expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        mock_token.revoked = False
        mock_token.revoked_at = None

        # Mock DB
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        result = await exchange_refresh_token(
            db=mock_db,
            refresh_token=refresh_token_plain,
            client_id="test-client"
        )

        # Should succeed
        assert isinstance(result, dict), f"Expected success dict, got: {result}"

        # Decode JWT to verify audience preserved
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        decoded = jwt.decode(
            result["access_token"],
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}
        )

        assert decoded["aud"] == original_resource, \
            "Refresh should preserve original resource as JWT aud"


class TestMCPAuthDualAudienceValidation:
    """Test MCP auth accepts both MCP server URL and OAUTH_ISSUER as valid audiences.

    These tests patch module-level config values and use importlib.reload() to ensure
    the patched values are picked up by the module under test.
    """

    @pytest.mark.asyncio
    async def test_validate_jwt_accepts_mcp_server_url_as_aud(self):
        """
        Test 11: validate_jwt() accepts token where aud = app's own MCP server URL (exact match).
        """
        import importlib
        from backend.core.oauth_provider.jwt.utils import create_access_token
        from backend.core.config import settings
        from backend.core.crypto import get_public_key
        from mcp_server.priority_guardian.config import MCP_SERVER_URL
        import mcp_server.priority_guardian.mcp_auth as mcp_auth_module

        user_id = uuid4()
        client_id = "test-client"
        scope = "pg.access"

        # Create token with MCP_SERVER_URL as aud (via resource param)
        access_token, jti = create_access_token(
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            resource=MCP_SERVER_URL
        )

        public_key = get_public_key()
        mock_jwk = MagicMock()
        mock_jwk.key = public_key

        # Patch config values and reload module to pick up changes
        with patch.object(mcp_auth_module, 'PG_ISSUER', settings.OAUTH_ISSUER), \
             patch.object(mcp_auth_module, 'PG_AUDIENCE', settings.OAUTH_ISSUER), \
             patch.object(mcp_auth_module, 'MCP_SERVER_URL', MCP_SERVER_URL), \
             patch.object(mcp_auth_module, '_jwks_cache') as mock_cache:

            mock_cache.fetch_jwks = AsyncMock()
            mock_cache.get_signing_key = MagicMock(return_value=mock_jwk)

            result = await mcp_auth_module.validate_jwt(access_token, "test-correlation-id")

            assert result["user_id"] == str(user_id)
            assert "scopes" in result

    @pytest.mark.asyncio
    async def test_validate_jwt_accepts_oauth_issuer_as_aud_backward_compat(self):
        """
        Test 12: validate_jwt() accepts token where aud = OAUTH_ISSUER (exact match, backward compat).
        """
        from backend.core.oauth_provider.jwt.utils import create_access_token
        from backend.core.config import settings
        from backend.core.crypto import get_public_key
        import mcp_server.priority_guardian.mcp_auth as mcp_auth_module

        user_id = uuid4()
        client_id = "test-client"
        scope = "pg.access"

        # Create token with OAUTH_ISSUER as aud (legacy behavior, no resource)
        access_token, jti = create_access_token(
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            resource=None  # Falls back to OAUTH_ISSUER
        )

        public_key = get_public_key()
        mock_jwk = MagicMock()
        mock_jwk.key = public_key

        # Patch directly on the imported module object
        with patch.object(mcp_auth_module, 'PG_ISSUER', settings.OAUTH_ISSUER), \
             patch.object(mcp_auth_module, 'PG_AUDIENCE', settings.OAUTH_ISSUER), \
             patch.object(mcp_auth_module, '_jwks_cache') as mock_cache:

            mock_cache.fetch_jwks = AsyncMock()
            mock_cache.get_signing_key = MagicMock(return_value=mock_jwk)

            result = await mcp_auth_module.validate_jwt(access_token, "test-correlation-id")

            assert result["user_id"] == str(user_id)
            assert "scopes" in result

    @pytest.mark.asyncio
    async def test_validate_jwt_rejects_invalid_audience(self):
        """
        Test 13: validate_jwt() rejects token where aud is neither - exact equality enforced.
        """
        from backend.core.oauth_provider.jwt.utils import create_access_token
        from backend.core.config import settings
        from backend.core.crypto import get_public_key
        import mcp_server.priority_guardian.mcp_auth as mcp_auth_module
        import jwt as pyjwt

        user_id = uuid4()
        client_id = "test-client"
        scope = "pg.access"

        # Create token with arbitrary invalid audience
        access_token, jti = create_access_token(
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            resource="https://invalid.example.com"  # Neither MCP_SERVER_URL nor OAUTH_ISSUER
        )

        public_key = get_public_key()
        mock_jwk = MagicMock()
        mock_jwk.key = public_key

        # Patch directly on the imported module object
        with patch.object(mcp_auth_module, 'PG_ISSUER', settings.OAUTH_ISSUER), \
             patch.object(mcp_auth_module, 'PG_AUDIENCE', settings.OAUTH_ISSUER), \
             patch.object(mcp_auth_module, 'MCP_SERVER_URL', "http://localhost:8003"), \
             patch.object(mcp_auth_module, '_jwks_cache') as mock_cache:

            mock_cache.fetch_jwks = AsyncMock()
            mock_cache.get_signing_key = MagicMock(return_value=mock_jwk)

            with pytest.raises(pyjwt.InvalidAudienceError):
                await mcp_auth_module.validate_jwt(access_token, "test-correlation-id")

    @pytest.mark.asyncio
    async def test_validate_jwt_rejects_different_apps_mcp_server_url(self):
        """
        Test 14: validate_jwt() rejects token where aud = a different app's MCP server URL.
        """
        from backend.core.oauth_provider.jwt.utils import create_access_token
        from backend.core.config import settings
        from backend.core.crypto import get_public_key
        import mcp_server.priority_guardian.mcp_auth as mcp_auth_module
        import jwt as pyjwt

        user_id = uuid4()
        client_id = "test-client"
        scope = "pg.access"

        # Create token with a DIFFERENT app's MCP server URL
        # (e.g., Focused's URL instead of PG's URL)
        focused_mcp_url = "https://mcp-focused.priority-guard.com"

        access_token, jti = create_access_token(
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            resource=focused_mcp_url  # Different app's URL
        )

        public_key = get_public_key()
        mock_jwk = MagicMock()
        mock_jwk.key = public_key

        # Patch directly on the imported module object
        with patch.object(mcp_auth_module, 'PG_ISSUER', settings.OAUTH_ISSUER), \
             patch.object(mcp_auth_module, 'PG_AUDIENCE', settings.OAUTH_ISSUER), \
             patch.object(mcp_auth_module, 'MCP_SERVER_URL', "http://localhost:8003"), \
             patch.object(mcp_auth_module, '_jwks_cache') as mock_cache:

            mock_cache.fetch_jwks = AsyncMock()
            mock_cache.get_signing_key = MagicMock(return_value=mock_jwk)

            # Should reject - PG's mcp_auth only accepts PG's MCP_SERVER_URL or OAUTH_ISSUER
            with pytest.raises(pyjwt.InvalidAudienceError):
                await mcp_auth_module.validate_jwt(access_token, "test-correlation-id")


# =============================================================================
# B2-8: Redirect URI Allowlist Unit Tests
# =============================================================================

class TestRedirectURIAllowlist:
    """Test redirect URI allowlist validation per RFC 9728 B2-8."""

    # ChatGPT redirect URIs (production allowlist)
    CHATGPT_REDIRECT_URI = "https://chatgpt.com/connector_platform_oauth_redirect"
    OPENAI_PLATFORM_REDIRECT_URI = "https://platform.openai.com/apps-manage/oauth"
    ALLOWED_URIS = [CHATGPT_REDIRECT_URI, OPENAI_PLATFORM_REDIRECT_URI]

    def test_chatgpt_redirect_uri_accepted(self):
        """
        Test 1: validate_redirect_uris() with https://chatgpt.com/connector_platform_oauth_redirect -> valid.
        """
        from backend.core.oauth_provider.validators.client_metadata import validate_redirect_uris

        valid, error = validate_redirect_uris(
            redirect_uris=[self.CHATGPT_REDIRECT_URI],
            allowed_uris=self.ALLOWED_URIS
        )

        assert valid is True, f"ChatGPT redirect URI should be valid, error: {error}"
        assert error is None

    def test_openai_platform_redirect_uri_accepted(self):
        """
        Test 2: validate_redirect_uris() with https://platform.openai.com/apps-manage/oauth -> valid.
        """
        from backend.core.oauth_provider.validators.client_metadata import validate_redirect_uris

        valid, error = validate_redirect_uris(
            redirect_uris=[self.OPENAI_PLATFORM_REDIRECT_URI],
            allowed_uris=self.ALLOWED_URIS
        )

        assert valid is True, f"OpenAI platform redirect URI should be valid, error: {error}"
        assert error is None

    def test_both_allowed_uris_in_one_registration_valid(self):
        """
        Test 3: validate_redirect_uris() with both URIs in one registration -> valid.
        """
        from backend.core.oauth_provider.validators.client_metadata import validate_redirect_uris

        valid, error = validate_redirect_uris(
            redirect_uris=[self.CHATGPT_REDIRECT_URI, self.OPENAI_PLATFORM_REDIRECT_URI],
            allowed_uris=self.ALLOWED_URIS
        )

        assert valid is True, f"Both URIs should be valid, error: {error}"
        assert error is None

    def test_arbitrary_https_uri_rejected(self):
        """
        Test 4: validate_redirect_uris() with arbitrary HTTPS URI -> rejected.
        """
        from backend.core.oauth_provider.validators.client_metadata import validate_redirect_uris

        valid, error = validate_redirect_uris(
            redirect_uris=["https://evil.example.com/callback"],
            allowed_uris=self.ALLOWED_URIS
        )

        assert valid is False, "Arbitrary HTTPS URI should be rejected"
        assert error is not None
        assert "not in allowlist" in error.lower()

    def test_http_uri_rejected(self):
        """
        Test 5: validate_redirect_uris() with HTTP URI -> rejected.
        """
        from backend.core.oauth_provider.validators.client_metadata import validate_redirect_uris

        valid, error = validate_redirect_uris(
            redirect_uris=["http://example.com/callback"],
            allowed_uris=self.ALLOWED_URIS
        )

        assert valid is False, "HTTP URI should be rejected"
        assert error is not None

    def test_empty_list_rejected(self):
        """
        Test 6: validate_redirect_uris() with empty list -> rejected.
        """
        from backend.core.oauth_provider.validators.client_metadata import validate_redirect_uris

        valid, error = validate_redirect_uris(
            redirect_uris=[],
            allowed_uris=self.ALLOWED_URIS
        )

        assert valid is False, "Empty URI list should be rejected"
        assert error is not None
        assert "at least one" in error.lower()

    def test_custom_allowlist_accepted(self):
        """
        Test 7: Custom allowlist passed in -> only those URIs accepted.
        """
        from backend.core.oauth_provider.validators.client_metadata import validate_redirect_uris

        custom_allowlist = ["https://custom.example.com/callback"]

        # Custom URI should be accepted
        valid, error = validate_redirect_uris(
            redirect_uris=["https://custom.example.com/callback"],
            allowed_uris=custom_allowlist
        )

        assert valid is True, f"Custom URI should be accepted, error: {error}"

        # But ChatGPT URI should now be rejected
        valid, error = validate_redirect_uris(
            redirect_uris=[self.CHATGPT_REDIRECT_URI],
            allowed_uris=custom_allowlist
        )

        assert valid is False, "ChatGPT URI should be rejected with custom allowlist"

    def test_subdomain_of_allowed_uri_rejected(self):
        """
        Test 8: Subdomain of allowed URI (e.g. https://sub.chatgpt.com/...) -> rejected.

        Exact string match only - no subdomain acceptance.
        """
        from backend.core.oauth_provider.validators.client_metadata import validate_redirect_uris

        # Try subdomain
        subdomain_uri = "https://sub.chatgpt.com/connector_platform_oauth_redirect"

        valid, error = validate_redirect_uris(
            redirect_uris=[subdomain_uri],
            allowed_uris=self.ALLOWED_URIS
        )

        assert valid is False, "Subdomain should be rejected (exact match only)"
        assert error is not None
        assert "not in allowlist" in error.lower()

    def test_no_allowlist_falls_back_to_https_check(self):
        """
        Test legacy mode: When allowlist is None, only HTTPS check is performed.
        """
        from backend.core.oauth_provider.validators.client_metadata import validate_redirect_uris

        # HTTPS URI should pass
        valid, error = validate_redirect_uris(
            redirect_uris=["https://any.example.com/callback"],
            allowed_uris=None  # Legacy mode
        )

        assert valid is True, "HTTPS URI should pass in legacy mode"

        # HTTP URI should fail
        valid, error = validate_redirect_uris(
            redirect_uris=["http://any.example.com/callback"],
            allowed_uris=None  # Legacy mode
        )

        assert valid is False, "HTTP URI should fail even in legacy mode"

    def test_path_variation_rejected(self):
        """
        Test that path variations of allowed URIs are rejected.

        Exact string match only - no path normalization.
        """
        from backend.core.oauth_provider.validators.client_metadata import validate_redirect_uris

        # Try path variation
        path_variation = "https://chatgpt.com/connector_platform_oauth_redirect/"  # Trailing slash

        valid, error = validate_redirect_uris(
            redirect_uris=[path_variation],
            allowed_uris=self.ALLOWED_URIS
        )

        assert valid is False, "Path variation should be rejected (exact match only)"
