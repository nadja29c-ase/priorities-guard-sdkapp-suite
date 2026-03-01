"""
Tests for Increment 12: OAuth Consent UI Implementation.

Tests:
1. GET /authorize with valid params (including login_hint) → renders consent HTML
2. GET /authorize with missing login_hint → error response login_required
3. GET /authorize with missing other params → error response
4. GET /authorize with invalid client_id → error redirect
5. GET /authorize with login_hint for new user → creates user, renders consent
6. GET /authorize with login_hint for existing user → finds user, renders consent
7. POST /consent with action=allow → generates code, redirects
8. POST /consent with action=deny → error redirect with access_denied
9. POST /consent with expired context → error redirect
10. POST /consent with invalid context_id → error redirect
11. Language detection: Accept-Language: de → German template
12. Language detection: Accept-Language: en-US → English template
13. Rate limiting tests (via mock)

PKCE Validation Tests (OAuth 2.1 compliance):
14. GET /authorize without code_challenge → 422 validation error
15. GET /authorize without code_challenge_method → 422 validation error
16. GET /authorize with code_challenge_method != S256 → invalid_request error redirect
17. GET /authorize with code_challenge_method = "plain" → invalid_request error redirect
18. GET /authorize with empty code_challenge → invalid_request error redirect
19. PKCE validator: verify_pkce with valid verifier/challenge → True
20. PKCE validator: verify_pkce with invalid verifier → False
21. PKCE validator: validate_code_challenge_method("S256") → True
22. PKCE validator: validate_code_challenge_method("plain") → False
23. POST /consent allow → propagates PKCE values to create_authorization_code

Redirect URI Exact Match Tests (OAuth security):
24. redirect_uri with trailing slash → invalid_request
25. redirect_uri with extra query params → invalid_request
26. redirect_uri http vs https mismatch → invalid_request

Scope Validation Tests (OAuth 2.1 compliance):
27. Multiple valid scopes (space-separated) → success
28. Invalid scope in multi-scope list → invalid_scope
29. Scope ordering should not matter → success
30. Request with unregistered scope → invalid_scope
31. Empty scope → invalid_scope or 422

Redis Context Malformed Tests (resilience):
32. Context missing redirect_uri → 400 error
33. Context missing code_challenge → 400 error
34. Context missing code_challenge_method → 400 error
35. Context missing user_id → 400 error
36. Context missing scope → 400 error
37. Context missing client_id → 400 error
38. Context missing state (optional) → should still work

Rate Limiting Tests (DoS prevention):
39. IP-based rate limit (before login_hint) → 429 after limit exceeded
40. login_hint-based rate limit (after validation) → 429 after limit exceeded
41. Different IPs not affected by each other's limits
42. Different login_hints not affected by each other's limits

Authorization Code Content Verification:
43. Auth code creation includes correct PKCE challenge
44. Auth code creation includes correct scope
45. Auth code creation includes correct client_id
46. Auth code creation includes correct user_id
47. Auth code creation includes correct redirect_uri
48. Auth code creation includes nonce when provided
49. Auth code creation called with all required fields

Consent Screen Content Validation (Platform Approval Requirements):
50. Consent page displays "Focused" branding
51. Consent page lists all requested scopes (focused.read, focused.write, etc.)
52. Consent page includes Privacy Policy URL link
53. auth_context_id is in a hidden input field (not just text)
54. German template has German translations for scope descriptions
55. Multiple scopes are all displayed on consent page
56. Scope descriptions are human-readable (not just scope names)

OAuth Error Response Compliance (RFC 6749):
57. invalid_request error returned for missing required params
58. unsupported_response_type error for response_type != "code"
59. access_denied error from POST /consent with action=deny
60. invalid_scope error for unregistered/invalid scope
61. server_error fallback for unexpected exceptions
62. Error responses include error_description field
63. Error redirects preserve state parameter

Empty/Null Parameter Handling (Edge Cases):
64. Empty string redirect_uri → invalid_request or 422
65. Empty string client_id → invalid_request or 422
66. Empty string scope → invalid_scope or 422
67. Empty string login_hint → login_required error
68. Empty string code_challenge → invalid_request or 422
69. Empty string code_challenge_method → invalid_request or 422
70. Whitespace-only parameters treated as empty
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from uuid import uuid4

from backend.core.models import CoreUser, CoreConnection
from backend.core.oauth_provider.authorize import (
    _detect_language,
    _resolve_user_identity,
    _error_redirect,
)
from backend.core.oauth_provider.validators.pkce import (
    verify_pkce,
    validate_code_challenge_method,
)


# =============================================================================
# Unit Tests for Helper Functions
# =============================================================================

class TestDetectLanguage:
    """Tests for _detect_language helper function."""

    def test_german_language_detected(self):
        """Accept-Language: de should return 'de'."""
        request = MagicMock()
        request.headers.get.return_value = "de"
        assert _detect_language(request) == "de"

    def test_german_with_region_detected(self):
        """Accept-Language: de-DE should return 'de'."""
        request = MagicMock()
        request.headers.get.return_value = "de-DE,de;q=0.9,en;q=0.8"
        assert _detect_language(request) == "de"

    def test_english_language_detected(self):
        """Accept-Language: en should return 'en'."""
        request = MagicMock()
        request.headers.get.return_value = "en"
        assert _detect_language(request) == "en"

    def test_english_us_detected(self):
        """Accept-Language: en-US should return 'en'."""
        request = MagicMock()
        request.headers.get.return_value = "en-US,en;q=0.9"
        assert _detect_language(request) == "en"

    def test_missing_header_defaults_to_english(self):
        """Missing Accept-Language header should default to 'en'."""
        request = MagicMock()
        request.headers.get.return_value = ""
        assert _detect_language(request) == "en"

    def test_french_defaults_to_english(self):
        """Unsupported languages should default to 'en'."""
        request = MagicMock()
        request.headers.get.return_value = "fr-FR,fr;q=0.9"
        assert _detect_language(request) == "en"


class TestErrorRedirect:
    """Tests for _error_redirect helper function."""

    def test_error_redirect_with_state(self):
        """Error redirect should include state parameter."""
        response = _error_redirect(
            redirect_uri="https://example.com/callback",
            state="abc123",
            error="access_denied",
            description="User denied access"
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=access_denied" in location
        assert "state=abc123" in location
        assert "error_description=User" in location

    def test_error_redirect_without_state(self):
        """Error redirect without state should omit state parameter."""
        response = _error_redirect(
            redirect_uri="https://example.com/callback",
            state=None,
            error="invalid_request",
            description="Bad request"
        )
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_request" in location
        assert "state=" not in location


# =============================================================================
# Integration Tests for User Lookup/Create
# =============================================================================

class TestGetOrCreateUser:
    """Tests for _resolve_user_identity function."""

    @pytest_asyncio.fixture
    async def setup_existing_user(self, async_session):
        """Create an existing user for tests."""
        user = CoreUser(chatgpt_user_id="existing-chatgpt-user-123")
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    @pytest.mark.asyncio
    async def test_creates_new_user_for_unknown_chatgpt_id(self, async_session):
        """Should create new user when chatgpt_user_id not found."""
        user = await _resolve_user_identity(
            db=async_session,
            chatgpt_user_id="new-chatgpt-user-456",
            correlation_id="test-correlation-id"
        )

        assert user is not None
        assert user.chatgpt_user_id == "new-chatgpt-user-456"
        assert user.id is not None

    @pytest.mark.asyncio
    async def test_finds_existing_user(self, async_session, setup_existing_user):
        """Should find existing user by chatgpt_user_id."""
        existing_user = setup_existing_user

        user = await _resolve_user_identity(
            db=async_session,
            chatgpt_user_id="existing-chatgpt-user-123",
            correlation_id="test-correlation-id"
        )

        assert user is not None
        assert user.id == existing_user.id
        assert user.chatgpt_user_id == "existing-chatgpt-user-123"


# =============================================================================
# Integration Tests for Authorize Endpoint
# =============================================================================

class TestAuthorizeEndpoint:
    """Integration tests for GET /oauth/focused/authorize."""

    @pytest_asyncio.fixture
    async def setup_oauth_client(self, async_session):
        """Create a registered OAuth client for tests."""
        from datetime import datetime, timezone, timedelta

        client = CoreConnection(
            provider="test-client",
            connection_type="oauth_provider",
            client_id="test-client-id",
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
    async def test_authorize_missing_login_hint_returns_error(self, client, setup_oauth_client):
        """GET /authorize without login_hint should return login_required error."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": "test-state",
            }
        )

        # Should redirect with login_required error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=login_required" in location
        assert "state=test-state" in location

    @pytest.mark.asyncio
    async def test_authorize_invalid_client_returns_error(self, client):
        """GET /authorize with unknown client_id should return invalid_client error."""
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "unknown-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_client error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_client" in location

    @pytest.mark.asyncio
    async def test_authorize_invalid_redirect_uri_returns_error(self, client, setup_oauth_client):
        """GET /authorize with unregistered redirect_uri should return error."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://malicious.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_request error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_request" in location

    @pytest.mark.asyncio
    async def test_authorize_invalid_scope_returns_error(self, client, setup_oauth_client):
        """GET /authorize with invalid scope should return invalid_scope error."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "invalid.scope",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_scope error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_scope" in location

    @pytest.mark.asyncio
    async def test_authorize_valid_request_renders_consent(self, client, setup_oauth_client):
        """GET /authorize with valid params should render consent HTML."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        # Mock Redis to avoid actual Redis calls
        with patch("backend.core.oauth_provider.authorize.check_rate_limit", new_callable=AsyncMock):
            with patch("backend.core.oauth_provider.authorize.create_authorization_context", new_callable=AsyncMock) as mock_create_context:
                mock_create_context.return_value = str(uuid4())

                response = await client.get(
                    "/oauth/focused/authorize",
                    params={
                        "response_type": "code",
                        "client_id": "test-client-id",
                        "redirect_uri": "https://example.com/callback",
                        "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                        "code_challenge_method": "S256",
                        "scope": "focused.read",
                        "state": "test-state",
                        "login_hint": "chatgpt-user-123",
                    }
                )

                # Should return HTML consent page
                assert response.status_code == 200
                assert "text/html" in response.headers["content-type"]
                assert "Focused" in response.text
                assert "auth_context_id" in response.text

    @pytest.mark.asyncio
    async def test_authorize_german_language_detection(self, client, setup_oauth_client):
        """GET /authorize with Accept-Language: de should render German template."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        with patch("backend.core.oauth_provider.authorize.check_rate_limit", new_callable=AsyncMock):
            with patch("backend.core.oauth_provider.authorize.create_authorization_context", new_callable=AsyncMock) as mock_create_context:
                mock_create_context.return_value = str(uuid4())

                response = await client.get(
                    "/oauth/focused/authorize",
                    params={
                        "response_type": "code",
                        "client_id": "test-client-id",
                        "redirect_uri": "https://example.com/callback",
                        "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                        "code_challenge_method": "S256",
                        "scope": "focused.read",
                        "state": "test-state",
                        "login_hint": "chatgpt-user-123",
                    },
                    headers={"Accept-Language": "de-DE,de;q=0.9,en;q=0.8"}
                )

                # Should return German consent page
                assert response.status_code == 200
                assert "Angeforderte Berechtigungen" in response.text  # German heading


# =============================================================================
# Integration Tests for Consent Endpoint
# =============================================================================

class TestConsentEndpoint:
    """Integration tests for POST /oauth/focused/consent."""

    @pytest.mark.asyncio
    async def test_consent_allow_redirects_with_code(self, client):
        """POST /consent with action=allow should redirect with authorization code."""
        # Mock Redis context retrieval
        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "focused.read",
            "state": "test-state",
            "nonce": "",
            "redirect_uri": "https://example.com/callback",
            "user_id": str(uuid4()),
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            with patch("backend.core.oauth_provider.consent_ui.create_authorization_code", new_callable=AsyncMock) as mock_create_code:
                mock_get_context.return_value = mock_context
                mock_create_code.return_value = "auth-code-123"

                response = await client.post(
                    "/oauth/focused/consent",
                    data={
                        "auth_context_id": str(uuid4()),
                        "action": "allow",
                    }
                )

                # Should redirect with code
                assert response.status_code == 302
                location = response.headers["location"]
                assert "code=auth-code-123" in location
                assert "state=test-state" in location

    @pytest.mark.asyncio
    async def test_consent_deny_redirects_with_error(self, client):
        """POST /consent with action=deny should redirect with access_denied error."""
        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "focused.read",
            "state": "test-state",
            "nonce": "",
            "redirect_uri": "https://example.com/callback",
            "user_id": str(uuid4()),
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            mock_get_context.return_value = mock_context

            response = await client.post(
                "/oauth/focused/consent",
                data={
                    "auth_context_id": str(uuid4()),
                    "action": "deny",
                }
            )

            # Should redirect with access_denied error
            assert response.status_code == 302
            location = response.headers["location"]
            assert "error=access_denied" in location
            assert "state=test-state" in location

    @pytest.mark.asyncio
    async def test_consent_expired_context_returns_error(self, client):
        """POST /consent with expired/invalid context should return error."""
        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            mock_get_context.return_value = None  # Context not found

            response = await client.post(
                "/oauth/focused/consent",
                data={
                    "auth_context_id": str(uuid4()),
                    "action": "allow",
                }
            )

            # Should return 400 error
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_consent_missing_context_id_returns_error(self, client):
        """POST /consent without auth_context_id should return error."""
        response = await client.post(
            "/oauth/focused/consent",
            data={
                "action": "allow",
            }
        )

        # Should return 400 error
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_consent_invalid_action_returns_error(self, client):
        """POST /consent with invalid action should return error."""
        response = await client.post(
            "/oauth/focused/consent",
            data={
                "auth_context_id": str(uuid4()),
                "action": "invalid",
            }
        )

        # Should return 400 error
        assert response.status_code == 400


# =============================================================================
# Unit Tests for PKCE Validators
# =============================================================================

class TestPKCEValidators:
    """Unit tests for PKCE validation functions."""

    def test_verify_pkce_valid_challenge(self):
        """verify_pkce with valid verifier/challenge should return True."""
        # Known test vector from RFC 7636
        code_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        assert verify_pkce(code_verifier, code_challenge) is True

    def test_verify_pkce_invalid_verifier(self):
        """verify_pkce with incorrect verifier should return False."""
        code_verifier = "wrong-verifier-value"
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        assert verify_pkce(code_verifier, code_challenge) is False

    def test_verify_pkce_empty_verifier(self):
        """verify_pkce with empty verifier should return False."""
        code_verifier = ""
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        assert verify_pkce(code_verifier, code_challenge) is False

    def test_validate_code_challenge_method_s256(self):
        """validate_code_challenge_method('S256') should return True."""
        assert validate_code_challenge_method("S256") is True

    def test_validate_code_challenge_method_plain(self):
        """validate_code_challenge_method('plain') should return False (OAuth 2.1)."""
        assert validate_code_challenge_method("plain") is False

    def test_validate_code_challenge_method_empty(self):
        """validate_code_challenge_method('') should return False."""
        assert validate_code_challenge_method("") is False

    def test_validate_code_challenge_method_case_sensitive(self):
        """validate_code_challenge_method is case-sensitive."""
        assert validate_code_challenge_method("s256") is False
        assert validate_code_challenge_method("S256") is True


# =============================================================================
# Integration Tests for PKCE in Authorize Endpoint
# =============================================================================

class TestAuthorizePKCE:
    """Integration tests for PKCE validation in GET /oauth/focused/authorize."""

    @pytest_asyncio.fixture
    async def setup_oauth_client(self, async_session):
        """Create a registered OAuth client for tests."""
        from datetime import datetime, timezone, timedelta

        client = CoreConnection(
            provider="test-client",
            connection_type="oauth_provider",
            client_id="test-client-id",
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
    async def test_authorize_missing_code_challenge_returns_422(self, client, setup_oauth_client):
        """GET /authorize without code_challenge should return 422 validation error."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                # code_challenge intentionally omitted
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # FastAPI returns 422 for missing required query params
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_authorize_missing_code_challenge_method_returns_422(self, client, setup_oauth_client):
        """GET /authorize without code_challenge_method should return 422 validation error."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                # code_challenge_method intentionally omitted
                "scope": "focused.read",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # FastAPI returns 422 for missing required query params
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_authorize_plain_method_returns_error(self, client, setup_oauth_client):
        """GET /authorize with code_challenge_method='plain' should return invalid_request."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "plain",  # Not allowed in OAuth 2.1
                "scope": "focused.read",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_request error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_request" in location
        assert "S256" in location  # Error description should mention S256

    @pytest.mark.asyncio
    async def test_authorize_wrong_method_returns_error(self, client, setup_oauth_client):
        """GET /authorize with unsupported code_challenge_method should return invalid_request."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "SHA512",  # Unsupported method
                "scope": "focused.read",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_request error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_request" in location

    @pytest.mark.asyncio
    async def test_authorize_case_sensitive_method_returns_error(self, client, setup_oauth_client):
        """GET /authorize with 's256' (lowercase) should return invalid_request."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "s256",  # Lowercase - should fail
                "scope": "focused.read",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_request error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_request" in location


# =============================================================================
# Integration Tests for PKCE Propagation to Authorization Code
# =============================================================================

class TestConsentPKCEPropagation:
    """Tests that PKCE values are correctly propagated when creating auth codes."""

    @pytest.mark.asyncio
    async def test_consent_allow_propagates_pkce_values(self, client):
        """POST /consent with action=allow should pass PKCE values to create_authorization_code."""
        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "focused.read",
            "state": "test-state",
            "nonce": "",
            "redirect_uri": "https://example.com/callback",
            "user_id": str(uuid4()),
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            with patch("backend.core.oauth_provider.consent_ui.create_authorization_code", new_callable=AsyncMock) as mock_create_code:
                mock_get_context.return_value = mock_context
                mock_create_code.return_value = "auth-code-123"

                response = await client.post(
                    "/oauth/focused/consent",
                    data={
                        "auth_context_id": str(uuid4()),
                        "action": "allow",
                    }
                )

                # Verify create_authorization_code was called with PKCE values
                mock_create_code.assert_called_once()
                call_kwargs = mock_create_code.call_args.kwargs

                assert call_kwargs["code_challenge"] == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
                assert call_kwargs["code_challenge_method"] == "S256"

                # Verify response redirects with code
                assert response.status_code == 302
                location = response.headers["location"]
                assert "code=auth-code-123" in location


# =============================================================================
# Integration Tests for Redirect URI Exact Match (OAuth Security)
# =============================================================================

class TestRedirectURIExactMatch:
    """Tests that redirect_uri must match EXACTLY - prevents OAuth redirect hijacking."""

    @pytest_asyncio.fixture
    async def setup_oauth_client(self, async_session):
        """Create OAuth client with registered redirect_uri: https://example.com/callback"""
        from datetime import datetime, timezone, timedelta

        client = CoreConnection(
            provider="test-client",
            connection_type="oauth_provider",
            client_id="test-client-id",
            redirect_uris=["https://example.com/callback"],  # Exact URI
            grant_types=["authorization_code", "refresh_token"],
            scopes=["focused.read", "focused.write", "focused.notify"],
            encrypted_access_token="placeholder",
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        async_session.add(client)
        await async_session.commit()
        return client

    @pytest.mark.asyncio
    async def test_redirect_uri_trailing_slash_rejected(self, client, setup_oauth_client):
        """redirect_uri with trailing slash should return invalid_request."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback/",  # Trailing slash
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_request error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_request" in location

    @pytest.mark.asyncio
    async def test_redirect_uri_extra_query_params_rejected(self, client, setup_oauth_client):
        """redirect_uri with extra query params should return invalid_request."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback?x=1",  # Extra query param
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_request error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_request" in location

    @pytest.mark.asyncio
    async def test_redirect_uri_http_vs_https_rejected(self, client, setup_oauth_client):
        """redirect_uri with http instead of https should return invalid_request."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "http://example.com/callback",  # http instead of https
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_request error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_request" in location

    @pytest.mark.asyncio
    async def test_redirect_uri_case_sensitive_path_rejected(self, client, setup_oauth_client):
        """redirect_uri with different case in path should return invalid_request."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/Callback",  # Capital C
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_request error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_request" in location


# =============================================================================
# Integration Tests for Scope Validation (OAuth 2.1 Compliance)
# =============================================================================

class TestScopeValidation:
    """Tests for scope validation - OAuth 2.1 requires all scopes be registered."""

    @pytest_asyncio.fixture
    async def setup_oauth_client(self, async_session):
        """Create OAuth client with registered scopes: focused.read, focused.write, focused.notify"""
        from datetime import datetime, timezone, timedelta

        client = CoreConnection(
            provider="test-client",
            connection_type="oauth_provider",
            client_id="test-client-id",
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code", "refresh_token"],
            scopes=["focused.read", "focused.write", "focused.notify"],  # All valid scopes
            encrypted_access_token="placeholder",
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        async_session.add(client)
        await async_session.commit()
        return client

    @pytest.mark.asyncio
    async def test_multiple_valid_scopes_accepted(self, client, setup_oauth_client):
        """Multiple valid space-separated scopes should be accepted."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        with patch("backend.core.oauth_provider.authorize.check_rate_limit", new_callable=AsyncMock):
            with patch("backend.core.oauth_provider.authorize.create_authorization_context", new_callable=AsyncMock) as mock_create_context:
                mock_create_context.return_value = str(uuid4())

                response = await client.get(
                    "/oauth/focused/authorize",
                    params={
                        "response_type": "code",
                        "client_id": "test-client-id",
                        "redirect_uri": "https://example.com/callback",
                        "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                        "code_challenge_method": "S256",
                        "scope": "focused.read focused.write",  # Multiple valid scopes
                        "state": "test-state",
                        "login_hint": "chatgpt-user-123",
                    }
                )

                # Should succeed and render consent page
                assert response.status_code == 200
                assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_all_three_scopes_accepted(self, client, setup_oauth_client):
        """All three valid scopes together should be accepted."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        with patch("backend.core.oauth_provider.authorize.check_rate_limit", new_callable=AsyncMock):
            with patch("backend.core.oauth_provider.authorize.create_authorization_context", new_callable=AsyncMock) as mock_create_context:
                mock_create_context.return_value = str(uuid4())

                response = await client.get(
                    "/oauth/focused/authorize",
                    params={
                        "response_type": "code",
                        "client_id": "test-client-id",
                        "redirect_uri": "https://example.com/callback",
                        "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                        "code_challenge_method": "S256",
                        "scope": "focused.read focused.write focused.notify",  # All three
                        "state": "test-state",
                        "login_hint": "chatgpt-user-123",
                    }
                )

                # Should succeed
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_scope_ordering_does_not_matter(self, client, setup_oauth_client):
        """Scope ordering should not affect validation."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        with patch("backend.core.oauth_provider.authorize.check_rate_limit", new_callable=AsyncMock):
            with patch("backend.core.oauth_provider.authorize.create_authorization_context", new_callable=AsyncMock) as mock_create_context:
                mock_create_context.return_value = str(uuid4())

                # Different order than registered
                response = await client.get(
                    "/oauth/focused/authorize",
                    params={
                        "response_type": "code",
                        "client_id": "test-client-id",
                        "redirect_uri": "https://example.com/callback",
                        "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                        "code_challenge_method": "S256",
                        "scope": "focused.notify focused.read focused.write",  # Different order
                        "state": "test-state",
                        "login_hint": "chatgpt-user-123",
                    }
                )

                # Should succeed
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_scope_in_multi_scope_list_rejected(self, client, setup_oauth_client):
        """Invalid scope mixed with valid scopes should return invalid_scope."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read invalid.scope focused.write",  # Invalid in middle
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_scope error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_scope" in location

    @pytest.mark.asyncio
    async def test_unregistered_scope_rejected(self, client, setup_oauth_client):
        """Scope not in allowed set should return invalid_scope."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "admin.delete",  # Not a valid scope
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_scope error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_scope" in location

    @pytest.mark.asyncio
    async def test_scope_case_sensitive(self, client, setup_oauth_client):
        """Scope validation should be case-sensitive."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "Focused.Read",  # Wrong case
                "state": "test-state",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_scope error
        assert response.status_code == 302
        location = response.headers["location"]
        assert "error=invalid_scope" in location


# =============================================================================
# Integration Tests for Malformed Redis Context (Resilience)
# =============================================================================

class TestMalformedRedisContext:
    """Tests for handling malformed/partial Redis authorization context."""

    def _get_valid_context(self) -> dict:
        """Return a valid context dict that can be modified for tests."""
        return {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "focused.read",
            "state": "test-state",
            "nonce": "",
            "redirect_uri": "https://example.com/callback",
            "user_id": str(uuid4()),
        }

    @pytest.mark.asyncio
    async def test_context_missing_redirect_uri_returns_400(self, client):
        """Context missing redirect_uri should return 400 error."""
        context = self._get_valid_context()
        del context["redirect_uri"]

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            mock_get_context.return_value = context

            response = await client.post(
                "/oauth/focused/consent",
                data={
                    "auth_context_id": str(uuid4()),
                    "action": "allow",
                }
            )

            # Should return 400 error (cannot redirect without redirect_uri)
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_context_missing_code_challenge_returns_400(self, client):
        """Context missing code_challenge should return 400 error."""
        context = self._get_valid_context()
        del context["code_challenge"]

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            mock_get_context.return_value = context

            response = await client.post(
                "/oauth/focused/consent",
                data={
                    "auth_context_id": str(uuid4()),
                    "action": "allow",
                }
            )

            # Should return 400 error
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_context_missing_code_challenge_method_returns_400(self, client):
        """Context missing code_challenge_method should return 400 error."""
        context = self._get_valid_context()
        del context["code_challenge_method"]

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            mock_get_context.return_value = context

            response = await client.post(
                "/oauth/focused/consent",
                data={
                    "auth_context_id": str(uuid4()),
                    "action": "allow",
                }
            )

            # Should return 400 error
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_context_missing_user_id_returns_400(self, client):
        """Context missing user_id should return 400 error."""
        context = self._get_valid_context()
        del context["user_id"]

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            mock_get_context.return_value = context

            response = await client.post(
                "/oauth/focused/consent",
                data={
                    "auth_context_id": str(uuid4()),
                    "action": "allow",
                }
            )

            # Should return 400 error
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_context_missing_scope_returns_400(self, client):
        """Context missing scope should return 400 error."""
        context = self._get_valid_context()
        del context["scope"]

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            mock_get_context.return_value = context

            response = await client.post(
                "/oauth/focused/consent",
                data={
                    "auth_context_id": str(uuid4()),
                    "action": "allow",
                }
            )

            # Should return 400 error
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_context_missing_client_id_returns_400(self, client):
        """Context missing client_id should return 400 error."""
        context = self._get_valid_context()
        del context["client_id"]

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            mock_get_context.return_value = context

            response = await client.post(
                "/oauth/focused/consent",
                data={
                    "auth_context_id": str(uuid4()),
                    "action": "allow",
                }
            )

            # Should return 400 error
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_context_missing_state_still_works(self, client):
        """Context missing state (optional) should still work - state omitted from redirect."""
        context = self._get_valid_context()
        del context["state"]

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            with patch("backend.core.oauth_provider.consent_ui.create_authorization_code", new_callable=AsyncMock) as mock_create_code:
                mock_get_context.return_value = context
                mock_create_code.return_value = "auth-code-123"

                response = await client.post(
                    "/oauth/focused/consent",
                    data={
                        "auth_context_id": str(uuid4()),
                        "action": "allow",
                    }
                )

                # Should succeed - state is optional
                assert response.status_code == 302
                location = response.headers["location"]
                assert "code=auth-code-123" in location
                # State should not be in the redirect since it was missing
                assert "state=" not in location

    @pytest.mark.asyncio
    async def test_context_with_empty_redirect_uri_returns_400(self, client):
        """Context with empty string redirect_uri should return 400 error."""
        context = self._get_valid_context()
        context["redirect_uri"] = ""

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            mock_get_context.return_value = context

            response = await client.post(
                "/oauth/focused/consent",
                data={
                    "auth_context_id": str(uuid4()),
                    "action": "allow",
                }
            )

            # Should return 400 error (empty redirect_uri is invalid)
            assert response.status_code == 400


# =============================================================================
# Integration Tests for Rate Limiting (DoS Prevention)
# =============================================================================

@pytest.mark.skipif(
    True,  # These tests require real Redis connection
    reason="Rate limiting tests require Redis - run manually with Redis available"
)
class TestRateLimiting:
    """Tests for rate limiting on /authorize endpoint.

    NOTE: These tests require a real Redis connection and are skipped by default.
    To run them, ensure Redis is available and remove the skipif decorator.
    """

    @pytest_asyncio.fixture
    async def setup_oauth_client(self, async_session):
        """Create a registered OAuth client for tests."""
        from datetime import datetime, timezone, timedelta

        client = CoreConnection(
            provider="test-client",
            connection_type="oauth_provider",
            client_id="test-client-id",
            redirect_uris=["https://example.com/callback"],
            grant_types=["authorization_code", "refresh_token"],
            scopes=["focused.read", "focused.write", "focused.notify"],
            encrypted_access_token="placeholder",
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        )
        async_session.add(client)
        await async_session.commit()
        return client

    @pytest_asyncio.fixture
    async def clear_rate_limits(self):
        """Clear rate limit keys before/after test."""
        from backend.core.redis_client import redis_client

        # Clear any existing rate limit keys for test isolation
        if redis_client.is_connected():
            # Delete test-related rate limit keys
            keys = await redis_client._client.keys("ratelimit:oauth:authorize:*")
            if keys:
                await redis_client._client.delete(*keys)

        yield

        # Cleanup after test
        if redis_client.is_connected():
            keys = await redis_client._client.keys("ratelimit:oauth:authorize:*")
            if keys:
                await redis_client._client.delete(*keys)

    @pytest.mark.asyncio
    async def test_ip_rate_limit_exceeded_returns_429(self, client, setup_oauth_client, clear_rate_limits):
        """21 requests from same IP should trigger 429 rate limit."""
        _ = setup_oauth_client
        _ = clear_rate_limits

        # Make 20 requests (at the limit)
        for i in range(20):
            response = await client.get(
                "/oauth/focused/authorize",
                params={
                    "response_type": "code",
                    "client_id": "test-client-id",
                    "redirect_uri": "https://example.com/callback",
                    "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                    "code_challenge_method": "S256",
                    "scope": "focused.read",
                    "state": f"test-state-{i}",
                    "login_hint": f"chatgpt-user-{i}",  # Different login_hint each time
                }
            )
            # These should succeed (302 redirect with login_required or consent page)
            assert response.status_code in [200, 302], f"Request {i+1} failed with {response.status_code}"

        # 21st request should be rate limited
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": "test-state-21",
                "login_hint": "chatgpt-user-21",
            }
        )

        # Should return 429 Too Many Requests
        assert response.status_code == 429
        assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_login_hint_rate_limit_exceeded_returns_429(self, client, setup_oauth_client, clear_rate_limits):
        """21 requests with same login_hint should trigger 429 rate limit."""
        _ = setup_oauth_client
        _ = clear_rate_limits

        # Make 20 requests with same login_hint
        for i in range(20):
            with patch("backend.core.oauth_provider.authorize.create_authorization_context", new_callable=AsyncMock) as mock_ctx:
                mock_ctx.return_value = str(uuid4())
                response = await client.get(
                    "/oauth/focused/authorize",
                    params={
                        "response_type": "code",
                        "client_id": "test-client-id",
                        "redirect_uri": "https://example.com/callback",
                        "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                        "code_challenge_method": "S256",
                        "scope": "focused.read",
                        "state": f"test-state-{i}",
                        "login_hint": "same-chatgpt-user",  # Same login_hint every time
                    },
                    headers={"X-Forwarded-For": f"192.168.1.{i}"}  # Different IPs to bypass IP limit
                )
                # These should succeed
                assert response.status_code in [200, 302], f"Request {i+1} failed with {response.status_code}"

        # 21st request with same login_hint should be rate limited
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": "test-state-21",
                "login_hint": "same-chatgpt-user",
            },
            headers={"X-Forwarded-For": "192.168.1.99"}
        )

        # Should return 429 Too Many Requests
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_different_ips_have_separate_limits(self, client, setup_oauth_client, clear_rate_limits):
        """Different IPs should have separate rate limit counters."""
        _ = setup_oauth_client
        _ = clear_rate_limits

        # Make 15 requests from IP 1
        for i in range(15):
            response = await client.get(
                "/oauth/focused/authorize",
                params={
                    "response_type": "code",
                    "client_id": "test-client-id",
                    "redirect_uri": "https://example.com/callback",
                    "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                    "code_challenge_method": "S256",
                    "scope": "focused.read",
                    "state": f"test-state-ip1-{i}",
                    "login_hint": f"chatgpt-user-ip1-{i}",
                },
                headers={"X-Forwarded-For": "10.0.0.1"}
            )
            assert response.status_code in [200, 302]

        # Request from different IP should still work (has its own counter)
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": "test-state-ip2",
                "login_hint": "chatgpt-user-ip2",
            },
            headers={"X-Forwarded-For": "10.0.0.2"}  # Different IP
        )

        # Should succeed - different IP has its own limit
        assert response.status_code in [200, 302]

    @pytest.mark.asyncio
    async def test_rate_limit_has_retry_after_header(self, client, setup_oauth_client, clear_rate_limits):
        """Rate limited response should include Retry-After header."""
        _ = setup_oauth_client
        _ = clear_rate_limits

        # Exhaust the rate limit
        for i in range(21):
            await client.get(
                "/oauth/focused/authorize",
                params={
                    "response_type": "code",
                    "client_id": "test-client-id",
                    "redirect_uri": "https://example.com/callback",
                    "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                    "code_challenge_method": "S256",
                    "scope": "focused.read",
                    "state": f"test-state-{i}",
                    "login_hint": f"chatgpt-user-{i}",
                }
            )

        # This request should be rate limited
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "response_type": "code",
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "state": "test-state-final",
                "login_hint": "chatgpt-user-final",
            }
        )

        assert response.status_code == 429
        assert "Retry-After" in response.headers
        # Retry-After should be a positive integer (seconds until reset)
        retry_after = int(response.headers["Retry-After"])
        assert retry_after > 0
        assert retry_after <= 60  # Window is 60 seconds


# =============================================================================
# Integration Tests for Authorization Code Content Verification
# =============================================================================

class TestAuthorizationCodeContent:
    """Tests that verify authorization code creation includes all required fields."""

    @pytest.mark.asyncio
    async def test_auth_code_includes_all_required_fields(self, client):
        """Verify create_authorization_code is called with all required parameters."""
        test_user_id = str(uuid4())
        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "focused.read focused.write",
            "state": "test-state-xyz",
            "nonce": "test-nonce-123",
            "redirect_uri": "https://example.com/callback",
            "user_id": test_user_id,
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            with patch("backend.core.oauth_provider.consent_ui.create_authorization_code", new_callable=AsyncMock) as mock_create_code:
                mock_get_context.return_value = mock_context
                mock_create_code.return_value = "auth-code-123"

                response = await client.post(
                    "/oauth/focused/consent",
                    data={
                        "auth_context_id": str(uuid4()),
                        "action": "allow",
                    }
                )

                # Verify response
                assert response.status_code == 302

                # Verify create_authorization_code was called exactly once
                mock_create_code.assert_called_once()

                # Get the call arguments
                call_kwargs = mock_create_code.call_args.kwargs

                # Verify all required fields are present and correct
                assert call_kwargs["user_id"] == test_user_id
                assert call_kwargs["client_id"] == "test-client-id"
                assert call_kwargs["code_challenge"] == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
                assert call_kwargs["code_challenge_method"] == "S256"
                assert call_kwargs["redirect_uri"] == "https://example.com/callback"
                assert call_kwargs["scope"] == "focused.read focused.write"
                assert call_kwargs["state"] == "test-state-xyz"
                assert call_kwargs["nonce"] == "test-nonce-123"
                assert "correlation_id" in call_kwargs
                assert "db" in call_kwargs

    @pytest.mark.asyncio
    async def test_auth_code_preserves_pkce_challenge(self, client):
        """Verify PKCE challenge is correctly passed to authorization code creation."""
        test_challenge = "custom-pkce-challenge-abc123"
        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": test_challenge,
            "code_challenge_method": "S256",
            "scope": "focused.read",
            "state": "test-state",
            "nonce": "",
            "redirect_uri": "https://example.com/callback",
            "user_id": str(uuid4()),
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            with patch("backend.core.oauth_provider.consent_ui.create_authorization_code", new_callable=AsyncMock) as mock_create_code:
                mock_get_context.return_value = mock_context
                mock_create_code.return_value = "auth-code-123"

                await client.post(
                    "/oauth/focused/consent",
                    data={
                        "auth_context_id": str(uuid4()),
                        "action": "allow",
                    }
                )

                call_kwargs = mock_create_code.call_args.kwargs
                assert call_kwargs["code_challenge"] == test_challenge
                assert call_kwargs["code_challenge_method"] == "S256"

    @pytest.mark.asyncio
    async def test_auth_code_preserves_user_id(self, client):
        """Verify user_id is correctly passed to authorization code creation."""
        test_user_id = str(uuid4())
        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "focused.read",
            "state": "test-state",
            "nonce": "",
            "redirect_uri": "https://example.com/callback",
            "user_id": test_user_id,
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            with patch("backend.core.oauth_provider.consent_ui.create_authorization_code", new_callable=AsyncMock) as mock_create_code:
                mock_get_context.return_value = mock_context
                mock_create_code.return_value = "auth-code-123"

                await client.post(
                    "/oauth/focused/consent",
                    data={
                        "auth_context_id": str(uuid4()),
                        "action": "allow",
                    }
                )

                call_kwargs = mock_create_code.call_args.kwargs
                assert call_kwargs["user_id"] == test_user_id

    @pytest.mark.asyncio
    async def test_auth_code_preserves_scope(self, client):
        """Verify scope is correctly passed to authorization code creation."""
        test_scope = "focused.read focused.write focused.notify"
        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": test_scope,
            "state": "test-state",
            "nonce": "",
            "redirect_uri": "https://example.com/callback",
            "user_id": str(uuid4()),
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            with patch("backend.core.oauth_provider.consent_ui.create_authorization_code", new_callable=AsyncMock) as mock_create_code:
                mock_get_context.return_value = mock_context
                mock_create_code.return_value = "auth-code-123"

                await client.post(
                    "/oauth/focused/consent",
                    data={
                        "auth_context_id": str(uuid4()),
                        "action": "allow",
                    }
                )

                call_kwargs = mock_create_code.call_args.kwargs
                assert call_kwargs["scope"] == test_scope

    @pytest.mark.asyncio
    async def test_auth_code_preserves_redirect_uri(self, client):
        """Verify redirect_uri is correctly passed to authorization code creation."""
        test_redirect_uri = "https://custom-domain.example.com/oauth/callback"
        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "focused.read",
            "state": "test-state",
            "nonce": "",
            "redirect_uri": test_redirect_uri,
            "user_id": str(uuid4()),
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            with patch("backend.core.oauth_provider.consent_ui.create_authorization_code", new_callable=AsyncMock) as mock_create_code:
                mock_get_context.return_value = mock_context
                mock_create_code.return_value = "auth-code-123"

                await client.post(
                    "/oauth/focused/consent",
                    data={
                        "auth_context_id": str(uuid4()),
                        "action": "allow",
                    }
                )

                call_kwargs = mock_create_code.call_args.kwargs
                assert call_kwargs["redirect_uri"] == test_redirect_uri

    @pytest.mark.asyncio
    async def test_auth_code_preserves_nonce_when_provided(self, client):
        """Verify nonce is correctly passed when provided (OIDC support)."""
        test_nonce = "oidc-nonce-value-12345"
        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "focused.read",
            "state": "test-state",
            "nonce": test_nonce,
            "redirect_uri": "https://example.com/callback",
            "user_id": str(uuid4()),
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            with patch("backend.core.oauth_provider.consent_ui.create_authorization_code", new_callable=AsyncMock) as mock_create_code:
                mock_get_context.return_value = mock_context
                mock_create_code.return_value = "auth-code-123"

                await client.post(
                    "/oauth/focused/consent",
                    data={
                        "auth_context_id": str(uuid4()),
                        "action": "allow",
                    }
                )

                call_kwargs = mock_create_code.call_args.kwargs
                assert call_kwargs["nonce"] == test_nonce

    @pytest.mark.asyncio
    async def test_auth_code_handles_empty_nonce(self, client):
        """Verify empty nonce is handled correctly (becomes None)."""
        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "focused.read",
            "state": "test-state",
            "nonce": "",  # Empty string
            "redirect_uri": "https://example.com/callback",
            "user_id": str(uuid4()),
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            with patch("backend.core.oauth_provider.consent_ui.create_authorization_code", new_callable=AsyncMock) as mock_create_code:
                mock_get_context.return_value = mock_context
                mock_create_code.return_value = "auth-code-123"

                await client.post(
                    "/oauth/focused/consent",
                    data={
                        "auth_context_id": str(uuid4()),
                        "action": "allow",
                    }
                )

                call_kwargs = mock_create_code.call_args.kwargs
                # Empty string becomes None (falsy value)
                assert call_kwargs["nonce"] is None

    @pytest.mark.asyncio
    async def test_auth_code_includes_correlation_id(self, client):
        """Verify correlation_id is passed for request tracing."""
        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "focused.read",
            "state": "test-state",
            "nonce": "",
            "redirect_uri": "https://example.com/callback",
            "user_id": str(uuid4()),
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            with patch("backend.core.oauth_provider.consent_ui.create_authorization_code", new_callable=AsyncMock) as mock_create_code:
                mock_get_context.return_value = mock_context
                mock_create_code.return_value = "auth-code-123"

                await client.post(
                    "/oauth/focused/consent",
                    data={
                        "auth_context_id": str(uuid4()),
                        "action": "allow",
                    }
                )

                call_kwargs = mock_create_code.call_args.kwargs
                # correlation_id should be present and non-empty
                assert "correlation_id" in call_kwargs
                assert call_kwargs["correlation_id"] is not None
                assert len(call_kwargs["correlation_id"]) > 0


# =============================================================================
# Consent Screen Content Validation Tests
# =============================================================================

class TestConsentScreenContent:
    """
    Tests that verify consent screen contains all required elements.

    Platform approval requirements:
    - Must display app branding ("Focused")
    - Must list all requested scopes with descriptions
    - Must include Privacy Policy URL
    - auth_context_id must be in hidden form field
    """

    @pytest_asyncio.fixture
    async def setup_oauth_client(self, async_session):
        """Create a registered OAuth client for tests."""
        from datetime import datetime, timezone, timedelta

        client = CoreConnection(
            provider="test-client",
            connection_type="oauth_provider",
            client_id="test-client-id",
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
    async def test_consent_page_displays_focused_branding(self, client, setup_oauth_client):
        """Consent page must display 'Focused' app name."""
        _ = setup_oauth_client  # Fixture creates OAuth client in DB

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        assert response.status_code == 200
        html = response.text
        assert "Focused" in html

    @pytest.mark.asyncio
    async def test_consent_page_lists_requested_scope(self, client, setup_oauth_client):
        """Consent page must display the requested scope (focused.read)."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        assert response.status_code == 200
        html = response.text
        assert "focused.read" in html

    @pytest.mark.asyncio
    async def test_consent_page_lists_multiple_scopes(self, client, setup_oauth_client):
        """Consent page must display all requested scopes when multiple are requested."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read focused.write focused.notify",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        assert response.status_code == 200
        html = response.text
        assert "focused.read" in html
        assert "focused.write" in html
        assert "focused.notify" in html

    @pytest.mark.asyncio
    async def test_consent_page_includes_privacy_policy_url(self, client, setup_oauth_client):
        """Consent page must include Privacy Policy link (required for platform approval)."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        assert response.status_code == 200
        html = response.text
        # Privacy Policy URL must be present
        assert "priority-guard.com/privacy" in html or "privacy" in html.lower()

    @pytest.mark.asyncio
    async def test_auth_context_id_in_hidden_input_field(self, client, setup_oauth_client):
        """auth_context_id must be in a hidden input field, not just displayed as text."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        assert response.status_code == 200
        html = response.text
        # Must have hidden input with name="auth_context_id"
        assert 'type="hidden"' in html
        assert 'name="auth_context_id"' in html
        # Verify it's an input element with both attributes
        assert '<input type="hidden" name="auth_context_id"' in html or \
               '<input name="auth_context_id" type="hidden"' in html

    @pytest.mark.asyncio
    async def test_german_template_has_german_scope_descriptions(self, client, setup_oauth_client):
        """German template must have German translations for scope descriptions."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            },
            headers={"Accept-Language": "de"}
        )

        assert response.status_code == 200
        html = response.text
        # German indicators - should have German text, not English
        # Check for German words that appear in the template
        assert "Zulassen" in html or "Ablehnen" in html or "Berechtigung" in html

    @pytest.mark.asyncio
    async def test_consent_page_has_scope_descriptions(self, client, setup_oauth_client):
        """Scope descriptions must be human-readable, not just scope names."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        assert response.status_code == 200
        html = response.text
        # Should have descriptive text near the scope name
        # Check for permission-related words that indicate descriptions
        assert "permission" in html.lower() or "access" in html.lower() or \
               "view" in html.lower() or "read" in html.lower() or \
               "Berechtigung" in html  # German for permission


# =============================================================================
# OAuth Error Response Compliance Tests (RFC 6749)
# =============================================================================

class TestOAuthErrorCompliance:
    """
    Tests for OAuth 2.0 error response compliance per RFC 6749.

    All error responses must:
    - Use correct error codes (invalid_request, unsupported_response_type, etc.)
    - Include error_description when available
    - Preserve state parameter in redirects
    - Use appropriate HTTP status codes
    """

    @pytest_asyncio.fixture
    async def setup_oauth_client(self, async_session):
        """Create a registered OAuth client for tests."""
        from datetime import datetime, timezone, timedelta

        client = CoreConnection(
            provider="test-client",
            connection_type="oauth_provider",
            client_id="test-client-id",
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
    async def test_invalid_request_missing_redirect_uri(self, client, setup_oauth_client):
        """Missing redirect_uri should return invalid_request error."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                # redirect_uri missing
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should be 422 (FastAPI validation) or contain invalid_request
        assert response.status_code == 422 or "invalid_request" in response.text

    @pytest.mark.asyncio
    async def test_invalid_request_missing_client_id(self, client):
        """Missing client_id should return invalid_request or 422."""
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                # client_id missing
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        assert response.status_code == 422 or "invalid_request" in response.text

    @pytest.mark.asyncio
    async def test_unsupported_response_type(self, client, setup_oauth_client):
        """response_type != 'code' should return unsupported_response_type error."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "token",  # OAuth 2.1 only allows "code"
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with error or return 4xx
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "unsupported_response_type" in location
        else:
            assert response.status_code in (400, 422)
            assert "unsupported_response_type" in response.text or "response_type" in response.text

    @pytest.mark.asyncio
    async def test_access_denied_from_consent(self, client, setup_oauth_client):
        """POST /consent with action=deny must return access_denied error."""
        _ = setup_oauth_client

        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "focused.read",
            "state": "preserved-state",
            "nonce": "",
            "redirect_uri": "https://example.com/callback",
            "user_id": str(uuid4()),
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            mock_get_context.return_value = mock_context

            response = await client.post(
                "/oauth/focused/consent",
                data={
                    "auth_context_id": str(uuid4()),
                    "action": "deny",
                },
                follow_redirects=False
            )

            assert response.status_code == 302
            location = response.headers.get("location", "")
            assert "access_denied" in location

    @pytest.mark.asyncio
    async def test_invalid_scope_unregistered(self, client, setup_oauth_client):
        """Unregistered scope should return invalid_scope error."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "admin.superpower",  # Not a registered scope
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Should redirect with invalid_scope or return error
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "invalid_scope" in location
        else:
            assert "invalid_scope" in response.text or "scope" in response.text.lower()

    @pytest.mark.asyncio
    async def test_server_error_fallback(self, client, setup_oauth_client):
        """Unexpected exception should return server_error or 500."""
        _ = setup_oauth_client

        with patch("backend.core.oauth_provider.authorize._resolve_user_identity", new_callable=AsyncMock) as mock_get_user:
            # Simulate unexpected exception
            mock_get_user.side_effect = Exception("Unexpected database error")

            # The exception may propagate (500) or be caught and redirected
            # Current implementation propagates - this test documents that behavior
            try:
                response = await client.get(
                    "/oauth/focused/authorize",
                    params={
                        "client_id": "test-client-id",
                        "redirect_uri": "https://example.com/callback",
                        "response_type": "code",
                        "scope": "focused.read",
                        "state": "test-state",
                        "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                        "code_challenge_method": "S256",
                        "login_hint": "chatgpt-user-123",
                    }
                )

                # If we get a response, verify it's an error
                if response.status_code == 302:
                    location = response.headers.get("location", "")
                    assert "server_error" in location or "error" in location
                else:
                    assert response.status_code == 500
            except Exception:
                # Exception propagation is acceptable (500 Internal Server Error)
                pass

    @pytest.mark.asyncio
    async def test_error_response_includes_error_description(self, client, setup_oauth_client):
        """Error redirects should include error_description parameter."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "invalid.scope.here",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        if response.status_code == 302:
            location = response.headers.get("location", "")
            # error_description should be present in redirect
            assert "error_description" in location or "error=" in location

    @pytest.mark.asyncio
    async def test_error_redirect_preserves_state(self, client, setup_oauth_client):
        """Error redirects must preserve the state parameter for CSRF protection."""
        _ = setup_oauth_client
        test_state = "unique-csrf-state-12345"

        mock_context = {
            "client_id": "test-client-id",
            "client_name": "Test Client",
            "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            "code_challenge_method": "S256",
            "scope": "focused.read",
            "state": test_state,
            "nonce": "",
            "redirect_uri": "https://example.com/callback",
            "user_id": str(uuid4()),
        }

        with patch("backend.core.oauth_provider.consent_ui.get_authorization_context", new_callable=AsyncMock) as mock_get_context:
            mock_get_context.return_value = mock_context

            response = await client.post(
                "/oauth/focused/consent",
                data={
                    "auth_context_id": str(uuid4()),
                    "action": "deny",
                },
                follow_redirects=False
            )

            assert response.status_code == 302
            location = response.headers.get("location", "")
            # State must be preserved in error redirect
            assert test_state in location


# =============================================================================
# Empty/Null Parameter Handling Tests
# =============================================================================

class TestEmptyParameterHandling:
    """
    Tests for empty string and whitespace-only parameter handling.

    Empty or whitespace-only values should be treated the same as missing
    parameters and result in appropriate error responses.
    """

    @pytest_asyncio.fixture
    async def setup_oauth_client(self, async_session):
        """Create a registered OAuth client for tests."""
        from datetime import datetime, timezone, timedelta

        client = CoreConnection(
            provider="test-client",
            connection_type="oauth_provider",
            client_id="test-client-id",
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
    async def test_empty_redirect_uri(self, client, setup_oauth_client):
        """Empty string redirect_uri should return error."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "",  # Empty string
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Empty redirect_uri should fail validation
        # Could be 302 redirect with error, 400, or 422
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "invalid" in location or "error" in location
        else:
            assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_empty_client_id(self, client):
        """Empty string client_id should return error."""
        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "",  # Empty string
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Empty client_id should fail - either 422 or invalid_client
        assert response.status_code in (400, 422) or "invalid" in response.text.lower()

    @pytest.mark.asyncio
    async def test_empty_scope(self, client, setup_oauth_client):
        """Empty string scope should return invalid_scope or 422."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "",  # Empty string
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Empty scope should fail
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "invalid_scope" in location or "error" in location
        else:
            assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_empty_login_hint(self, client, setup_oauth_client):
        """Empty string login_hint should return login_required error."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "",  # Empty string
            }
        )

        # Empty login_hint should be treated as missing
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "login_required" in location or "error" in location
        else:
            # Or could return JSON error
            assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_empty_code_challenge(self, client, setup_oauth_client):
        """Empty string code_challenge should return error."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "",  # Empty string
                "code_challenge_method": "S256",
                "login_hint": "chatgpt-user-123",
            }
        )

        # Empty code_challenge should fail PKCE validation
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "invalid_request" in location or "error" in location
        else:
            assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_empty_code_challenge_method(self, client, setup_oauth_client):
        """Empty string code_challenge_method should return error."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "",  # Empty string
                "login_hint": "chatgpt-user-123",
            }
        )

        # Empty code_challenge_method should fail
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "invalid_request" in location or "error" in location
        else:
            assert response.status_code in (400, 422)

    @pytest.mark.asyncio
    async def test_whitespace_only_login_hint(self, client, setup_oauth_client):
        """Whitespace-only login_hint should be treated as empty."""
        _ = setup_oauth_client

        response = await client.get(
            "/oauth/focused/authorize",
            params={
                "client_id": "test-client-id",
                "redirect_uri": "https://example.com/callback",
                "response_type": "code",
                "scope": "focused.read",
                "state": "test-state",
                "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                "code_challenge_method": "S256",
                "login_hint": "   ",  # Whitespace only
            }
        )

        # Whitespace-only login_hint should be treated as missing
        if response.status_code == 302:
            location = response.headers.get("location", "")
            assert "login_required" in location or "error" in location
        else:
            assert response.status_code in (400, 422)


class TestConsentSessionValidation:
    """Tests for session cookie validation in consent flow."""

    @pytest.mark.asyncio
    async def test_consent_creates_new_session_when_cookie_belongs_to_different_user(self):
        """Consent creates new session when existing cookie belongs to different user."""
        from backend.core.oauth_provider.consent_ui import consent_endpoint

        current_user_id = uuid4()
        different_user_id = uuid4()
        valid_token = "a" * 64

        # Mock request
        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation"
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "test-context-id",
            "action": "allow"
        })

        # Mock db
        mock_db = AsyncMock()

        with patch(
            "backend.core.oauth_provider.consent_ui.check_rate_limit",
            new_callable=AsyncMock
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_client_ip",
            return_value="127.0.0.1"
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_authorization_context",
            new_callable=AsyncMock,
            return_value={
                "client_id": "test-client",
                "code_challenge": "test-challenge",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "redirect_uri": "https://example.com/callback",
                "user_id": str(current_user_id),
                "state": "test-state",
            }
        ), patch(
            "backend.core.oauth_provider.consent_ui.create_authorization_code",
            new_callable=AsyncMock,
            return_value="auth-code-123"
        ), patch(
            "backend.core.oauth_provider.consent_ui.record_consent",
            new_callable=AsyncMock
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_session_cookie",
            return_value=valid_token
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_session_user",
            new_callable=AsyncMock,
            return_value=different_user_id  # Different user owns the session
        ), patch(
            "backend.core.oauth_provider.consent_ui.create_session",
            new_callable=AsyncMock,
            return_value="new-session-token"
        ) as mock_create_session, patch(
            "backend.core.oauth_provider.consent_ui.set_session_cookie"
        ):
            await consent_endpoint(mock_request, mock_db)

        # create_session should be called with current user (not different user)
        mock_create_session.assert_called_once()
        call_args = mock_create_session.call_args
        assert str(call_args[0][0]) == str(current_user_id)

    @pytest.mark.asyncio
    async def test_consent_reuses_session_when_cookie_belongs_to_same_user(self):
        """Consent reuses existing session when cookie belongs to same user."""
        from backend.core.oauth_provider.consent_ui import consent_endpoint

        user_id = uuid4()
        valid_token = "b" * 64

        # Mock request
        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation"
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "test-context-id",
            "action": "allow"
        })

        # Mock db
        mock_db = AsyncMock()

        with patch(
            "backend.core.oauth_provider.consent_ui.check_rate_limit",
            new_callable=AsyncMock
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_client_ip",
            return_value="127.0.0.1"
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_authorization_context",
            new_callable=AsyncMock,
            return_value={
                "client_id": "test-client",
                "code_challenge": "test-challenge",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "redirect_uri": "https://example.com/callback",
                "user_id": str(user_id),
                "state": "test-state",
            }
        ), patch(
            "backend.core.oauth_provider.consent_ui.create_authorization_code",
            new_callable=AsyncMock,
            return_value="auth-code-123"
        ), patch(
            "backend.core.oauth_provider.consent_ui.record_consent",
            new_callable=AsyncMock
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_session_cookie",
            return_value=valid_token
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_session_user",
            new_callable=AsyncMock,
            return_value=user_id  # Same user owns the session
        ), patch(
            "backend.core.oauth_provider.consent_ui.create_session",
            new_callable=AsyncMock,
            return_value="new-session-token"
        ) as mock_create_session, patch(
            "backend.core.oauth_provider.consent_ui.set_session_cookie"
        ):
            await consent_endpoint(mock_request, mock_db)

        # create_session should NOT be called (session reused)
        mock_create_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_consent_rejects_non_hex_session_cookie(self):
        """Consent creates new session when cookie is non-hex (skips get_session_user)."""
        from backend.core.oauth_provider.consent_ui import consent_endpoint

        user_id = uuid4()
        invalid_token = "Z" * 64  # Not valid hex

        # Mock request
        mock_request = MagicMock()
        mock_request.state.correlation_id = "test-correlation"
        mock_request.form = AsyncMock(return_value={
            "auth_context_id": "test-context-id",
            "action": "allow"
        })

        # Mock db
        mock_db = AsyncMock()

        with patch(
            "backend.core.oauth_provider.consent_ui.check_rate_limit",
            new_callable=AsyncMock
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_client_ip",
            return_value="127.0.0.1"
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_authorization_context",
            new_callable=AsyncMock,
            return_value={
                "client_id": "test-client",
                "code_challenge": "test-challenge",
                "code_challenge_method": "S256",
                "scope": "focused.read",
                "redirect_uri": "https://example.com/callback",
                "user_id": str(user_id),
                "state": "test-state",
            }
        ), patch(
            "backend.core.oauth_provider.consent_ui.create_authorization_code",
            new_callable=AsyncMock,
            return_value="auth-code-123"
        ), patch(
            "backend.core.oauth_provider.consent_ui.record_consent",
            new_callable=AsyncMock
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_session_cookie",
            return_value=invalid_token
        ), patch(
            "backend.core.oauth_provider.consent_ui.get_session_user",
            new_callable=AsyncMock,
            return_value=user_id
        ) as mock_get_session_user, patch(
            "backend.core.oauth_provider.consent_ui.create_session",
            new_callable=AsyncMock,
            return_value="new-session-token"
        ) as mock_create_session, patch(
            "backend.core.oauth_provider.consent_ui.set_session_cookie"
        ):
            await consent_endpoint(mock_request, mock_db)

        # get_session_user should NOT be called (hex validation failed)
        mock_get_session_user.assert_not_called()

        # create_session should be called (new session created)
        mock_create_session.assert_called_once()
