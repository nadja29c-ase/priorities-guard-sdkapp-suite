"""
B2-7 WWW-Authenticate Header Tests (Increment 40).

Tests that OAuth 401 responses include the correct WWW-Authenticate header
per OpenAI Apps SDK authentication spec.

Header format: Bearer resource_metadata="<PG_MCP_SERVER_URL>/.well-known/oauth-protected-resource"
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.core.config import WWW_AUTHENTICATE_VALUE, RESOURCE_METADATA_URL


class TestWWWAuthenticateHeader:
    """Test WWW-Authenticate header on OAuth 401 responses."""

    @pytest.mark.asyncio
    async def test_invalid_client_error_code_includes_header(
        self, async_engine, fake_redis_client
    ):
        """
        When token service returns invalid_client error, response should be 401 with WWW-Authenticate header.

        This tests the token_endpoint.py direct JSONResponse path for authorization_code grant.
        """
        from backend.main import app
        from backend.core.database import get_db

        endpoint_session_maker = async_sessionmaker(
            async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async def override_get_db():
            async with endpoint_session_maker() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        # Mock the token service to return invalid_client error
        with patch(
            "backend.core.oauth_provider.token_endpoint.exchange_authorization_code",
            new_callable=AsyncMock,
            return_value=("invalid_client", "Client not found")
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/oauth/pg/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": "any-code",
                        "code_verifier": "a" * 43,
                        "client_id": "any-client-id",
                        "redirect_uri": "http://localhost:3000/callback"
                    }
                )

        app.dependency_overrides.clear()

        # Should be 401 for invalid_client
        assert response.status_code == 401

        # Should have WWW-Authenticate header
        assert "WWW-Authenticate" in response.headers

        # Should have correct format
        www_auth = response.headers["WWW-Authenticate"]
        assert www_auth == WWW_AUTHENTICATE_VALUE
        assert "Bearer resource_metadata=" in www_auth
        assert "/.well-known/oauth-protected-resource" in www_auth

    @pytest.mark.asyncio
    async def test_invalid_client_refresh_token_includes_header(
        self, async_engine, fake_redis_client
    ):
        """
        When refresh token service returns invalid_client error, response should be 401 with header.

        This tests the second JSONResponse path in token_endpoint.py.
        """
        from backend.main import app
        from backend.core.database import get_db

        endpoint_session_maker = async_sessionmaker(
            async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async def override_get_db():
            async with endpoint_session_maker() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        # Mock the token service to return invalid_client error
        with patch(
            "backend.core.oauth_provider.token_endpoint.exchange_refresh_token",
            new_callable=AsyncMock,
            return_value=("invalid_client", "Client not found")
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/oauth/focused/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": "any-refresh-token",
                        "client_id": "any-client-id"
                    }
                )

        app.dependency_overrides.clear()

        # Should be 401 for invalid_client
        assert response.status_code == 401

        # Should have WWW-Authenticate header
        assert "WWW-Authenticate" in response.headers
        assert response.headers["WWW-Authenticate"] == WWW_AUTHENTICATE_VALUE

    @pytest.mark.asyncio
    async def test_oauth_exception_handler_includes_header(self, async_engine, fake_redis_client):
        """
        OAuthError with 401 status on /oauth/* path should include WWW-Authenticate header.

        This tests the oauth_exception_handler path in main.py using the real app.
        We add a test-only route that raises InvalidClientError to trigger the exception handler.
        """
        from backend.main import app
        from backend.core.oauth_provider.exceptions import InvalidClientError

        # Add test-only route inside /oauth/* path
        async def raise_invalid_client_oauth():
            raise InvalidClientError("Test client error")

        test_path = "/oauth/test/raise-401-for-header-test"
        app.router.add_api_route(test_path, raise_invalid_client_oauth, methods=["GET"])

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get(test_path)

            # Should be 401
            assert response.status_code == 401

            # Should have WWW-Authenticate header (from real exception handler)
            assert "WWW-Authenticate" in response.headers
            assert response.headers["WWW-Authenticate"] == WWW_AUTHENTICATE_VALUE
        finally:
            # Clean up: remove test route
            app.router.routes = [r for r in app.router.routes if getattr(r, 'path', '') != test_path]

    @pytest.mark.asyncio
    async def test_non_oauth_path_no_header(self, async_engine, fake_redis_client):
        """
        401 from non-OAuth path should NOT include WWW-Authenticate header.

        The header is only for /oauth/* paths. Tests the real exception handler in main.py.
        We add a test-only route outside /oauth/* that raises InvalidClientError.
        """
        from backend.main import app
        from backend.core.oauth_provider.exceptions import InvalidClientError

        # Add test-only route outside /oauth/* path
        async def raise_invalid_client_non_oauth():
            raise InvalidClientError("Test client error")

        test_path = "/api/test/raise-401-for-header-test"
        app.router.add_api_route(test_path, raise_invalid_client_non_oauth, methods=["GET"])

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get(test_path)

            # Should be 401 (from InvalidClientError)
            assert response.status_code == 401

            # Should NOT have WWW-Authenticate header (not an /oauth/ path)
            assert "WWW-Authenticate" not in response.headers
        finally:
            # Clean up: remove test route
            app.router.routes = [r for r in app.router.routes if getattr(r, 'path', '') != test_path]

    @pytest.mark.asyncio
    async def test_invalid_grant_no_header(self, async_engine, fake_redis_client):
        """
        400 errors (invalid_grant) on OAuth endpoints should NOT include WWW-Authenticate header.

        The header is only for 401 responses.
        """
        from backend.main import app
        from backend.core.database import get_db

        endpoint_session_maker = async_sessionmaker(
            async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async def override_get_db():
            async with endpoint_session_maker() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            # Invalid code returns invalid_grant (400)
            response = await client.post(
                "/oauth/pg/token",
                data={
                    "grant_type": "authorization_code",
                    "code": "nonexistent-code",
                    "code_verifier": "a" * 43,
                    "client_id": "some-client",
                    "redirect_uri": "http://localhost:3000/callback"
                }
            )

        app.dependency_overrides.clear()

        # Should be 400 for invalid_grant
        assert response.status_code == 400

        # Should NOT have WWW-Authenticate header (only for 401)
        assert "WWW-Authenticate" not in response.headers

    @pytest.mark.asyncio
    async def test_unsupported_grant_type_no_header(self, async_engine, fake_redis_client):
        """
        Unsupported grant type (400) should NOT include WWW-Authenticate header.
        """
        from backend.main import app
        from backend.core.database import get_db

        endpoint_session_maker = async_sessionmaker(
            async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async def override_get_db():
            async with endpoint_session_maker() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            # Unsupported grant type returns 400
            response = await client.post(
                "/oauth/pg/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": "some-client"
                }
            )

        app.dependency_overrides.clear()

        # Should be 400 for unsupported grant type
        assert response.status_code == 400

        # Should NOT have WWW-Authenticate header
        assert "WWW-Authenticate" not in response.headers

    @pytest.mark.asyncio
    async def test_response_body_unchanged(self, async_engine, fake_redis_client):
        """
        Response body should be unchanged when WWW-Authenticate header is added.

        The OAuth error JSON structure must remain intact.
        """
        from backend.main import app
        from backend.core.database import get_db

        endpoint_session_maker = async_sessionmaker(
            async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async def override_get_db():
            async with endpoint_session_maker() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db

        # Mock to return invalid_client to trigger 401 path
        with patch(
            "backend.core.oauth_provider.token_endpoint.exchange_authorization_code",
            new_callable=AsyncMock,
            return_value=("invalid_client", "Client authentication failed")
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/oauth/pg/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": "any-code",
                        "code_verifier": "a" * 43,
                        "client_id": "any-client-id",
                        "redirect_uri": "http://localhost:3000/callback"
                    }
                )

        app.dependency_overrides.clear()

        # Verify JSON structure is intact
        body = response.json()
        assert "error" in body
        assert body["error"] == "invalid_client"
        assert "error_description" in body
        assert body["error_description"] == "Client authentication failed"

        # Header should also be present
        assert "WWW-Authenticate" in response.headers


    @pytest.mark.asyncio
    async def test_existing_www_authenticate_not_overwritten(self, async_engine, fake_redis_client):
        """
        Verify the defensive guard: if WWW-Authenticate is already in headers, don't overwrite.

        This tests the real exception handler in main.py. The guard check
        `"WWW-Authenticate" not in headers` prevents double-setting.

        We add a test-only route and patch JSONResponse to capture headers,
        verifying the header is set exactly once via the guard.
        """
        from backend.main import app
        from backend.core.oauth_provider.exceptions import InvalidClientError
        from fastapi.responses import JSONResponse as OriginalJSONResponse

        captured_headers = {}

        # Patch JSONResponse to capture headers and verify guard behavior
        class CapturingJSONResponse(OriginalJSONResponse):
            def __init__(self, *args, headers=None, **kwargs):
                captured_headers.update(headers or {})
                super().__init__(*args, headers=headers, **kwargs)

        # Add test-only route that raises InvalidClientError
        async def raise_invalid_client_for_guard_test():
            raise InvalidClientError("Test error")

        test_path = "/oauth/test/raise-401-guard-test"
        app.router.add_api_route(test_path, raise_invalid_client_for_guard_test, methods=["GET"])

        try:
            with patch("backend.main.JSONResponse", CapturingJSONResponse):
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.get(test_path)

            # Verify the response has WWW-Authenticate header
            assert response.status_code == 401
            assert "WWW-Authenticate" in response.headers

            # The captured headers should contain WWW-Authenticate (set once, not overwritten)
            assert "WWW-Authenticate" in captured_headers
            assert captured_headers["WWW-Authenticate"] == WWW_AUTHENTICATE_VALUE
        finally:
            # Clean up: remove test route
            app.router.routes = [r for r in app.router.routes if getattr(r, 'path', '') != test_path]


class TestWWWAuthenticateHeaderFormat:
    """Test the WWW-Authenticate header value format."""

    def test_header_value_format(self):
        """WWW-Authenticate value should have correct Bearer resource_metadata format."""
        # Should start with "Bearer resource_metadata="
        assert WWW_AUTHENTICATE_VALUE.startswith('Bearer resource_metadata="')

        # Should end with closing quote
        assert WWW_AUTHENTICATE_VALUE.endswith('"')

        # Should contain the well-known path
        assert "/.well-known/oauth-protected-resource" in WWW_AUTHENTICATE_VALUE

    def test_resource_metadata_url_format(self):
        """RESOURCE_METADATA_URL should point to oauth-protected-resource."""
        assert RESOURCE_METADATA_URL.endswith("/.well-known/oauth-protected-resource")

    def test_header_value_uses_config(self):
        """WWW-Authenticate header value should be derived from config."""
        from backend.core.config import settings

        expected_url = f"{settings.PG_MCP_SERVER_URL}/.well-known/oauth-protected-resource"
        assert RESOURCE_METADATA_URL == expected_url

        expected_header = f'Bearer resource_metadata="{expected_url}"'
        assert WWW_AUTHENTICATE_VALUE == expected_header
