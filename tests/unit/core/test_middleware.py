"""
Increment 7C: Middleware and Error Handling Integration Tests

Comprehensive pytest tests for:
1. Correlation ID Middleware (with/without incoming header)
2. Security Headers Middleware (200 and error responses)
3. Logging Scrubber Integration
4. Rate Limiting (with Redis, Redis down)
5. OAuthError Handler

Uses FastAPI TestClient for real HTTP integration tests.
"""

import pytest
import uuid
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.core.middleware import CorrelationIDMiddleware, SecurityHeadersMiddleware
from backend.core.oauth_provider.exceptions import (
    OAuthError,
    InvalidRequestError,
    InvalidClientError,
    UnauthorizedClientError,
)
from backend.core.logging import scrub_sensitive_data, get_logger


# =============================================================================
# Test Application Setup
# =============================================================================

def create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with 7C middleware for testing."""
    app = FastAPI()

    # Add middleware in correct order (reverse of execution order)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    # Test endpoints
    @app.get("/test/success")
    async def success_endpoint(request: Request):
        """Normal 200 response."""
        return {"message": "success", "correlation_id": request.state.correlation_id}

    @app.get("/test/oauth-error")
    async def oauth_error_endpoint():
        """Raises OAuthError."""
        raise InvalidRequestError("Missing required parameter")

    @app.post("/test/token")
    async def token_endpoint(request: Request):
        """OAuth token endpoint for rate limiting tests."""
        # Import here to avoid circular imports in tests
        from backend.core.rate_limit import rate_limit_token

        # Apply rate limiting (5 requests per minute)
        await rate_limit_token(request, client_id="test-client")

        return {"access_token": "test-token"}

    # Add OAuthError exception handler
    @app.exception_handler(OAuthError)
    async def oauth_exception_handler(request: Request, exc: OAuthError):
        """Handle OAuth errors with proper JSON response."""
        correlation_id = getattr(request.state, "correlation_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error,
                "error_description": exc.description,
                "correlation_id": correlation_id,
            },
        )

    return app


@pytest.fixture
def test_app():
    """Fixture providing test FastAPI app."""
    return create_test_app()


@pytest.fixture
def client(test_app):
    """Fixture providing TestClient."""
    return TestClient(test_app)


# =============================================================================
# Test 1: Correlation ID Middleware
# =============================================================================

class TestCorrelationIDMiddleware:
    """Test correlation ID generation and propagation."""

    def test_no_incoming_correlation_id_generates_uuid(self, client):
        """
        Test 1A: When no X-Correlation-ID header is provided,
        middleware should generate a new UUID.
        """
        response = client.get("/test/success")

        # Assert response has X-Correlation-ID header
        assert "x-correlation-id" in response.headers, "Missing X-Correlation-ID in response"

        # Assert it's a valid UUID
        correlation_id = response.headers["x-correlation-id"]
        try:
            uuid.UUID(correlation_id)
        except ValueError:
            pytest.fail(f"X-Correlation-ID is not a valid UUID: {correlation_id}")

        # Assert it's also in response body
        assert response.json()["correlation_id"] == correlation_id

    def test_incoming_correlation_id_preserved(self, client):
        """
        Test 1B: When X-Correlation-ID header is provided,
        middleware should preserve and return the same value.
        """
        incoming_id = "test-correlation-123"

        response = client.get(
            "/test/success",
            headers={"X-Correlation-ID": incoming_id}
        )

        # Assert same correlation ID in response
        assert response.headers["x-correlation-id"] == incoming_id
        assert response.json()["correlation_id"] == incoming_id

    def test_correlation_id_attached_to_request_state(self, client):
        """
        Test 1C: Verify correlation_id is available in request.state
        for use in logging and error handlers.
        """
        response = client.get("/test/success")

        # The endpoint returns request.state.correlation_id
        correlation_id = response.json()["correlation_id"]
        assert correlation_id is not None
        assert len(correlation_id) > 0


# =============================================================================
# Test 2: Security Headers Middleware
# =============================================================================

class TestSecurityHeadersMiddleware:
    """Test security headers are applied to all responses."""

    EXPECTED_HEADERS = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "x-xss-protection": "1; mode=block",
        "strict-transport-security": "max-age=31536000; includeSubDomains",
        "cache-control": "no-store",
        "pragma": "no-cache",
    }

    def test_security_headers_on_success_response(self, client):
        """
        Test 2A: Security headers should be present on normal 200 responses.
        """
        response = client.get("/test/success")

        assert response.status_code == 200

        # Check all expected security headers
        for header, expected_value in self.EXPECTED_HEADERS.items():
            assert header in response.headers, f"Missing security header: {header}"
            assert response.headers[header] == expected_value, \
                f"Wrong value for {header}: {response.headers[header]}"

    def test_security_headers_on_404_response(self, client):
        """
        Test 2B: Security headers should be present on 404 responses.
        """
        response = client.get("/nonexistent-endpoint")

        assert response.status_code == 404

        # Check security headers are still present
        for header, expected_value in self.EXPECTED_HEADERS.items():
            assert header in response.headers, f"Missing security header on 404: {header}"

    def test_security_headers_on_oauth_error_response(self, client):
        """
        Test 2C: Security headers should be present on OAuthError responses.
        """
        response = client.get("/test/oauth-error")

        assert response.status_code == 400  # InvalidRequestError

        # Check security headers
        for header, expected_value in self.EXPECTED_HEADERS.items():
            assert header in response.headers, f"Missing security header on OAuth error: {header}"



# =============================================================================
# Test 3: Logging Scrubber Integration
# =============================================================================

class TestLoggingScrubber:
    """Test sensitive data scrubbing in logs."""

    def test_scrub_sensitive_data_redacts_tokens(self):
        """
        Test 3A: scrub_sensitive_data should redact sensitive fields.
        """
        event_dict = {
            "event": "oauth.token_issued",
            "access_token": "secret-access-token-123",
            "refresh_token": "secret-refresh-token-456",
            "authorization_code": "auth-code-789",
            "client_id": "valid-client-id",
            "user_id": "user-uuid",
        }

        scrubbed = scrub_sensitive_data(None, None, event_dict.copy())

        # Assert sensitive fields are redacted
        assert scrubbed["access_token"] == "[REDACTED]"
        assert scrubbed["refresh_token"] == "[REDACTED]"
        assert scrubbed["authorization_code"] == "[REDACTED]"

        # Assert non-sensitive fields are preserved
        assert scrubbed["client_id"] == "valid-client-id"
        assert scrubbed["user_id"] == "user-uuid"
        assert scrubbed["event"] == "oauth.token_issued"

    def test_scrub_sensitive_data_handles_password(self):
        """
        Test 3B: Password field should also be redacted.
        """
        event_dict = {
            "event": "user.login",
            "password": "super-secret-password",
            "username": "test-user",
        }

        scrubbed = scrub_sensitive_data(None, None, event_dict.copy())

        assert scrubbed["password"] == "[REDACTED]"
        assert scrubbed["username"] == "test-user"

    def test_scrub_sensitive_data_handles_client_secret(self):
        """
        Test 3C: client_secret should be redacted.
        """
        event_dict = {
            "event": "oauth.client_registered",
            "client_secret": "secret-client-secret",
            "client_id": "new-client",
        }

        scrubbed = scrub_sensitive_data(None, None, event_dict.copy())

        assert scrubbed["client_secret"] == "[REDACTED]"
        assert scrubbed["client_id"] == "new-client"

    def test_scrub_sensitive_data_preserves_non_sensitive_fields(self):
        """
        Test 3D: scrub_sensitive_data should preserve non-sensitive fields.
        """
        event_dict = {
            "event": "oauth.flow",
            "client_id": "valid-client",
            "user_id": "user-123",
            "scope": "focused.read",
            "timestamp": "2025-01-01T00:00:00Z",
        }

        scrubbed = scrub_sensitive_data(None, None, event_dict.copy())

        # All fields should be preserved (none are sensitive)
        assert scrubbed == event_dict


# =============================================================================
# Test 4: Rate Limiting
# =============================================================================

class TestRateLimiting:
    """Test rate limiting behavior with Redis and without."""

    @patch('backend.core.rate_limit.redis_client')
    @pytest.mark.asyncio
    async def test_rate_limit_with_redis_enforces_limit(self, mock_redis, client):
        """
        Test 4A: With Redis available, rate limiting should be enforced.
        Limit: 5 requests per 60 seconds for /token endpoint.
        """
        # Mock Redis to be connected
        mock_redis.is_connected.return_value = True

        # Mock incr to return incrementing values (async)
        call_count = [0]

        async def mock_incr(key):
            call_count[0] += 1
            return call_count[0]

        async def mock_expire(key, seconds):
            return None

        mock_redis.incr = AsyncMock(side_effect=mock_incr)
        mock_redis.expire = AsyncMock(side_effect=mock_expire)

        # Make 6 requests
        responses = []
        for i in range(6):
            response = client.post("/test/token")
            responses.append(response)

        # First 5 should succeed
        for i in range(5):
            assert responses[i].status_code == 200, f"Request {i+1} should succeed"

        # 6th should be rate limited (429)
        assert responses[5].status_code == 429
        assert "rate limit" in responses[5].json()["detail"].lower()

    @patch('backend.core.rate_limit.redis_client')
    def test_rate_limit_with_redis_down_bypasses(self, mock_redis, client):
        """
        Test 4B: With Redis down, rate limiting should be bypassed.
        """
        # Mock Redis to be disconnected
        mock_redis.is_connected.return_value = False

        # Make 10 requests (well over the limit)
        for i in range(10):
            response = client.post("/test/token")
            assert response.status_code == 200, \
                f"Request {i+1} should succeed when Redis is down (bypass mode)"

    @patch('backend.core.rate_limit.redis_client')
    @pytest.mark.asyncio
    async def test_rate_limit_logs_exceeded_event(self, mock_redis, client):
        """
        Test 4C: When rate limit is exceeded, should return 429 with proper error.
        """
        # Mock Redis to be connected and return limit exceeded
        mock_redis.is_connected.return_value = True

        async def mock_incr(key):
            return 6  # Over the limit

        async def mock_expire(key, seconds):
            return None

        mock_redis.incr = AsyncMock(side_effect=mock_incr)
        mock_redis.expire = AsyncMock(side_effect=mock_expire)

        response = client.post("/test/token")

        assert response.status_code == 429
        assert "detail" in response.json()
        assert "rate limit" in response.json()["detail"].lower()

    @patch('backend.core.rate_limit.redis_client')
    def test_rate_limit_bypassed_when_redis_down(self, mock_redis, client):
        """
        Test 4D: When Redis is down, rate limiting should be bypassed.
        """
        # Mock Redis to be disconnected
        mock_redis.is_connected.return_value = False

        # Make request and verify it succeeds (bypassed)
        response = client.post("/test/token")

        assert response.status_code == 200
        assert "access_token" in response.json()


# =============================================================================
# Test 5: OAuthError Handler
# =============================================================================

class TestOAuthErrorHandler:
    """Test OAuthError exception handler."""

    def test_oauth_error_returns_correct_status_code(self, client):
        """
        Test 5A: OAuthError handler should return correct HTTP status code.
        """
        response = client.get("/test/oauth-error")

        # InvalidRequestError has status_code 400
        assert response.status_code == 400

    def test_oauth_error_returns_json_with_error_fields(self, client):
        """
        Test 5B: OAuthError handler should return JSON with error, error_description, correlation_id.
        """
        response = client.get("/test/oauth-error")

        assert response.status_code == 400

        data = response.json()

        # Check required fields
        assert "error" in data
        assert "error_description" in data
        assert "correlation_id" in data

        # Check values
        assert data["error"] == "invalid_request"
        assert "Missing required parameter" in data["error_description"]
        assert data["correlation_id"] is not None

    def test_oauth_error_includes_security_headers(self, client):
        """
        Test 5C: OAuthError responses should include security headers.
        """
        response = client.get("/test/oauth-error")

        assert response.status_code == 400

        # Check security headers are present
        assert "x-content-type-options" in response.headers
        assert "x-frame-options" in response.headers
        assert "cache-control" in response.headers
        assert "pragma" in response.headers

    def test_oauth_error_preserves_correlation_id(self, client):
        """
        Test 5D: OAuthError handler should preserve incoming correlation ID.
        """
        incoming_id = "test-error-correlation-456"

        response = client.get(
            "/test/oauth-error",
            headers={"X-Correlation-ID": incoming_id}
        )

        assert response.status_code == 400

        # Check correlation ID in response
        assert response.headers["x-correlation-id"] == incoming_id
        assert response.json()["correlation_id"] == incoming_id

    def test_different_oauth_errors_have_correct_codes(self, test_app):
        """
        Test 5E: Different OAuthError subclasses should have correct error codes and status.
        """
        client = TestClient(test_app)

        # Add test endpoints for different OAuth errors
        @test_app.get("/test/invalid-client")
        async def invalid_client():
            raise InvalidClientError("Client authentication failed")

        @test_app.get("/test/unauthorized-client")
        async def unauthorized_client():
            raise UnauthorizedClientError("Client not authorized")

        # Test InvalidClientError (401)
        response = client.get("/test/invalid-client")
        assert response.status_code == 401
        assert response.json()["error"] == "invalid_client"

        # Test UnauthorizedClientError (400)
        response = client.get("/test/unauthorized-client")
        assert response.status_code == 400
        assert response.json()["error"] == "unauthorized_client"


# =============================================================================
# Test 6: End-to-End Integration
# =============================================================================

class TestEndToEndIntegration:
    """Test complete request flow through all middleware and handlers."""

    def test_complete_request_flow_success(self, client):
        """
        Test 6A: Complete request flow through all middleware for success case.
        """
        response = client.get("/test/success")

        # Assert success
        assert response.status_code == 200

        # Assert correlation ID present
        assert "x-correlation-id" in response.headers
        correlation_id = response.headers["x-correlation-id"]
        assert response.json()["correlation_id"] == correlation_id

        # Assert all security headers present
        assert "x-content-type-options" in response.headers
        assert "strict-transport-security" in response.headers
        assert "cache-control" in response.headers

    def test_complete_request_flow_oauth_error(self, client):
        """
        Test 6B: Complete request flow through all middleware for OAuth error case.
        """
        incoming_id = "end-to-end-test-789"

        response = client.get(
            "/test/oauth-error",
            headers={"X-Correlation-ID": incoming_id}
        )

        # Assert OAuth error handled correctly
        assert response.status_code == 400

        # Assert correlation ID preserved
        assert response.headers["x-correlation-id"] == incoming_id
        assert response.json()["correlation_id"] == incoming_id

        # Assert security headers present
        assert "x-content-type-options" in response.headers
        assert "x-frame-options" in response.headers

        # Assert correct error format
        data = response.json()
        assert data["error"] == "invalid_request"
        assert "error_description" in data
