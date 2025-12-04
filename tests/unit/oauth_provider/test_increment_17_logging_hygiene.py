"""
Increment 17: OAuth Provider Hardening - Logging Hygiene Tests.

Tests to verify no sensitive data (tokens, secrets) is logged.

These tests verify:
1. Static analysis of source files for dangerous logging patterns
2. Runtime verification that modules with loggers don't log sensitive data

Note: Some modules (jwt/utils.py, encryption.py) don't have loggers at all,
so we only do static analysis for those. Modules with loggers (consent_service.py,
token_service.py, etc.) get runtime tests with patched loggers.
"""

import io
import pathlib
import pytest
from unittest.mock import patch

import structlog

# Project root relative to this test file
# File: tests/unit/oauth_provider/test_increment_17_logging_hygiene.py
# parents[0] = oauth_provider/
# parents[1] = unit/
# parents[2] = tests/
# parents[3] = project root
PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
OAUTH_PROVIDER_PATH = PROJECT_ROOT / "backend" / "core" / "oauth_provider"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def isolated_structlog():
    """
    Isolate structlog configuration changes to prevent test pollution.

    Resets structlog to defaults after each test to clear all global state,
    including cached loggers from cache_logger_on_first_use.
    """
    yield
    structlog.reset_defaults()


@pytest.fixture
def capturing_logger(isolated_structlog):
    """
    Create a structlog logger that captures output to a StringIO buffer.

    Returns a tuple of (logger, buffer) where buffer.getvalue() contains
    all log output.

    Depends on isolated_structlog to ensure config is restored after test.
    """
    _ = isolated_structlog  # Ensure fixture runs for cleanup

    buffer = io.StringIO()

    # Create a logger that writes to our buffer
    logger = structlog.wrap_logger(
        structlog.PrintLogger(file=buffer),
        processors=[
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
    )

    return logger, buffer


# =============================================================================
# Test 1: Consent Service Logging Hygiene (has logger)
# =============================================================================

class TestConsentServiceLoggingHygiene:
    """Verify consent_service.py doesn't log authorization codes."""

    @pytest.mark.asyncio
    async def test_authorization_code_not_logged(self, async_session, capturing_logger):
        """
        Authorization codes should never appear in logs.

        consent_service.py has a logger and logs on code creation.
        We patch it to capture output and verify the code isn't logged.
        """
        from backend.core.models import CoreUser

        logger, buffer = capturing_logger

        # Create test user
        user = CoreUser()
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Patch the module's logger to capture output
        with patch(
            "backend.core.oauth_provider.services.consent_service.logger",
            logger
        ):
            from backend.core.oauth_provider.services.consent_service import create_authorization_code

            auth_code = await create_authorization_code(
                db=async_session,
                user_id=str(user.id),
                client_id="test-client",
                code_challenge="test_challenge",
                code_challenge_method="S256",
                redirect_uri="https://example.com/callback",
                scope="focused.read",
                correlation_id="test-correlation"
            )

        log_output = buffer.getvalue()

        # Verify logging actually happened (test validity check)
        assert len(log_output) > 0, "Expected some log output from consent_service"

        # Auth code should NOT appear in logs
        assert auth_code not in log_output, \
            f"Authorization code should never be logged. Found in: {log_output}"

        # Check partial code (first 20 chars)
        if len(auth_code) > 20:
            assert auth_code[:20] not in log_output, \
                f"Partial auth code should not be logged. Found in: {log_output}"


# =============================================================================
# Test 2: Token Service Logging Hygiene (has logger)
# =============================================================================

class TestTokenServiceLoggingHygiene:
    """Verify token_service.py doesn't log tokens."""

    @pytest.mark.asyncio
    async def test_token_exchange_doesnt_log_tokens(self, async_session, capturing_logger):
        """
        Token exchange should not log access_token or refresh_token values.

        token_service.py has a logger. We verify tokens aren't logged
        during the exchange_authorization_code flow.
        """
        from backend.core.models import CoreUser
        from backend.core.oauth_provider.models import OAuthAuthorizationCode
        from datetime import datetime, timedelta, timezone
        import secrets
        import hashlib
        import base64

        logger, buffer = capturing_logger

        # Create test user
        user = CoreUser()
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Create a valid PKCE pair
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode("ascii")
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")

        # Create authorization code in DB
        auth_code_value = secrets.token_urlsafe(32)
        auth_code = OAuthAuthorizationCode(
            code=auth_code_value,
            user_id=user.id,
            client_id="test-client",
            code_challenge=code_challenge,
            code_challenge_method="S256",
            redirect_uri="https://example.com/callback",
            scope=["focused.read"],
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            used=False
        )
        async_session.add(auth_code)
        await async_session.commit()

        # Patch the module's logger
        with patch(
            "backend.core.oauth_provider.services.token_service.logger",
            logger
        ):
            from backend.core.oauth_provider.services.token_service import exchange_authorization_code

            result = await exchange_authorization_code(
                db=async_session,
                code=auth_code_value,
                client_id="test-client",
                code_verifier=code_verifier,
                redirect_uri="https://example.com/callback",
                correlation_id="test-correlation"
            )

        log_output = buffer.getvalue()

        # Verify we got tokens back (test validity check)
        assert result is not None, "Expected token response"
        access_token = result.get("access_token")
        refresh_token = result.get("refresh_token")

        # access_token MUST be present for this test to be meaningful
        assert access_token is not None, \
            "access_token missing from response — token_service changed behavior"

        # refresh_token MUST be present for this test to be meaningful
        # Note: refresh_token is optional per OAuth 2.1, but our current implementation
        # always returns one. If this changes, update the test accordingly.
        assert refresh_token is not None, \
            "refresh_token missing from response — token_service changed behavior"

        # Tokens should NOT appear in logs
        assert access_token not in log_output, \
            f"Access token should never be logged. Found in: {log_output}"
        assert refresh_token not in log_output, \
            f"Refresh token should never be logged. Found in: {log_output}"


# =============================================================================
# Test 3: Source Code Static Analysis
# =============================================================================

def _scan_file_for_logging_violations(filepath: str, dangerous_patterns: list) -> list:
    """
    Scan a Python file for dangerous logging patterns.

    Uses a state machine to track docstring context, avoiding false positives
    from multi-line docstrings.

    Args:
        filepath: Path to the Python file to scan
        dangerous_patterns: List of regex patterns to match

    Returns:
        List of violation strings in format "filepath:line: content"
    """
    import re

    DOCSTRING_DELIMS = ('"""', "'''")

    violations = []

    with open(filepath, 'r') as f:
        lines = f.readlines()

    inside_docstring = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Track docstring state (toggle on delimiter)
        # Count occurrences to handle single-line docstrings like """foo"""
        for delim in DOCSTRING_DELIMS:
            count = stripped.count(delim)
            if count == 1:
                # Single delimiter toggles state
                inside_docstring = not inside_docstring
            elif count >= 2:
                # Two delimiters on same line (e.g., """foo""") - stays outside
                pass

        # Skip lines inside docstrings
        if inside_docstring:
            continue

        # Skip if no logger call
        if 'logger.' not in line:
            continue

        # Skip other false positives
        if _is_false_positive(line):
            continue

        # Check for dangerous patterns
        for pattern in dangerous_patterns:
            if re.search(pattern, line):
                violations.append(f"{filepath}:{i}: {stripped}")

    return violations


def _is_false_positive(line: str) -> bool:
    """
    Check if a matched line is a false positive.

    Returns True for lines that should be skipped.

    Note: Docstring handling is done by the scanner's state machine.
    This function handles other false positive cases.
    """
    stripped = line.strip()

    # Comments
    if stripped.startswith('#'):
        return True

    # Descriptive text about not logging (in comments or strings)
    if 'never' in line.lower() and 'log' in line.lower():
        return True

    # Token type references (e.g., "token_type": "access_token")
    # These are string literals, not variable values
    if '"access_token"' in stripped or "'access_token'" in stripped:
        return True
    if '"refresh_token"' in stripped or "'refresh_token'" in stripped:
        return True

    return False


class TestSourceCodeLoggingPatterns:
    """
    Static analysis of source files for dangerous logging patterns.

    This is a compile-time check that scans actual source files.
    Excludes docstrings, comments, string literals, and other false positives.
    """

    def test_no_access_token_in_log_statements(self):
        """
        Scan oauth_provider source files for dangerous logging patterns.

        Patterns to detect:
        - logger.info(..., access_token=token_value, ...)
        - logger.debug(..., token=some_var, ...)

        Does NOT flag:
        - Comments and docstrings
        - String literals like "token_type": "access_token"
        """
        import os

        oauth_provider_path = OAUTH_PROVIDER_PATH

        # Only match logger calls where sensitive variable is passed as a keyword arg
        # Uses \b word boundary to avoid matching inside strings like "client_secret docs"
        # Pattern: logger.xxx(..., access_token=some_var, ...) where some_var is not quoted
        dangerous_patterns = [
            # Keyword argument: access_token=some_var (not in quotes)
            r'logger\.\w+\([^)]*\baccess_token=[^\s"\'][^,)]*',
            # Keyword argument: refresh_token=some_var
            r'logger\.\w+\([^)]*\brefresh_token=[^\s"\'][^,)]*',
            # Keyword argument: code_verifier=some_var
            r'logger\.\w+\([^)]*\bcode_verifier=[^\s"\'][^,)]*',
            # Keyword argument: client_secret=some_var
            r'logger\.\w+\([^)]*\bclient_secret=[^\s"\'][^,)]*',
        ]

        violations = []

        for root, dirs, files in os.walk(oauth_provider_path):
            # Skip __pycache__
            dirs[:] = [d for d in dirs if d != '__pycache__']

            for filename in files:
                if not filename.endswith('.py'):
                    continue

                filepath = os.path.join(root, filename)
                violations.extend(_scan_file_for_logging_violations(filepath, dangerous_patterns))

        if violations:
            violation_report = "\n".join(violations)
            pytest.fail(f"Found potential token logging violations:\n{violation_report}")

    def test_no_authorization_header_logging(self):
        """
        Ensure Authorization headers are never logged in full.
        """
        import os

        oauth_provider_path = OAUTH_PROVIDER_PATH

        # Patterns for logging Authorization header values
        # Covers multiple access patterns:
        # 1. Direct keyword arg: Authorization=some_var
        # 2. Dict access: headers["Authorization"] or headers['Authorization']
        # 3. Dict get: headers.get("Authorization") or headers.get('Authorization')
        dangerous_patterns = [
            # Keyword argument: Authorization=some_var
            r'logger\.\w+\([^)]*\b[Aa]uthorization=[^\s"\'][^,)]*',
            # Dict bracket access: headers["Authorization"] or headers['Authorization']
            r'logger\.\w+\([^)]*headers\[["\'][Aa]uthorization["\']\]',
            # Dict .get() access: headers.get("Authorization") or headers.get('Authorization')
            r'logger\.\w+\([^)]*headers\.get\(["\'][Aa]uthorization["\']\)',
            # request.headers variants
            r'logger\.\w+\([^)]*request\.headers\[["\'][Aa]uthorization["\']\]',
            r'logger\.\w+\([^)]*request\.headers\.get\(["\'][Aa]uthorization["\']\)',
        ]

        violations = []

        for root, dirs, files in os.walk(oauth_provider_path):
            dirs[:] = [d for d in dirs if d != '__pycache__']

            for filename in files:
                if not filename.endswith('.py'):
                    continue

                filepath = os.path.join(root, filename)
                violations.extend(_scan_file_for_logging_violations(filepath, dangerous_patterns))

        if violations:
            violation_report = "\n".join(violations)
            pytest.fail(f"Found potential Authorization header logging:\n{violation_report}")


# =============================================================================
# Test 4: Revoke Service Logging Hygiene (has logger)
# =============================================================================

class TestRevokeServiceLoggingHygiene:
    """Verify revoke service and endpoint don't log the token being revoked."""

    @pytest.mark.asyncio
    async def test_revoke_service_doesnt_log_token_value(
        self,
        async_session,
        capturing_logger,
    ):
        """
        revoke_token() should not log the token value.

        revoke_service.py has a logger. We patch it to capture output
        and verify the token being revoked isn't logged.
        """
        from datetime import datetime, timedelta, timezone
        from backend.core.models import CoreUser, CoreConnection
        from backend.core.oauth_provider.models import OAuthAccessToken
        from backend.core.oauth_provider.jwt.utils import create_access_token
        from backend.core.encryption import encrypt_token
        import secrets

        logger, buffer = capturing_logger

        # Create test user and client
        user = CoreUser()
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        oauth_client = CoreConnection(
            user_id=None,
            provider="Test",
            connection_type="oauth_provider",
            client_id="test-revoke-logging",
            client_secret_enc=encrypt_token("secret"),
            redirect_uris=["https://example.com/callback"],
            encrypted_access_token="",
            scopes=["focused.read"],
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
        )
        async_session.add(oauth_client)
        await async_session.commit()

        # Create an access token and store in DB
        access_token, jti = create_access_token(
            user_id=user.id,
            client_id="test-revoke-logging",
            scope="focused.read"
        )

        # Store token in database so revoke can find it
        # Note: OAuthAccessToken uses refresh_token_enc (encrypted) and refresh_token_hash
        from backend.core.encryption import encrypt_token as encrypt_refresh, hash_refresh_token
        refresh_token_plain = secrets.token_urlsafe(32)

        token_record = OAuthAccessToken(
            jti=jti,
            user_id=user.id,
            client_id="test-revoke-logging",
            scope=["focused.read"],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            refresh_token_enc=encrypt_refresh(refresh_token_plain),
            refresh_token_hash=hash_refresh_token(refresh_token_plain),
            refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        async_session.add(token_record)
        await async_session.commit()

        # Patch the revoke service logger
        with patch(
            "backend.core.oauth_provider.services.revoke_service.logger",
            logger
        ):
            from backend.core.oauth_provider.services.revoke_service import revoke_token

            await revoke_token(
                db=async_session,
                token=access_token,
                client_id="test-revoke-logging",
                correlation_id="test-correlation"
            )

        log_output = buffer.getvalue()

        # Verify logging actually happened (test validity check)
        assert len(log_output) > 0, "Expected some log output from revoke_service"

        # Token should NOT appear in logs
        assert access_token not in log_output, \
            f"Token being revoked should not be logged. Found in: {log_output}"

        # First 20 chars of token should not appear either
        if len(access_token) > 20:
            assert access_token[:20] not in log_output, \
                f"Partial token should not be logged. Found in: {log_output}"

    @pytest.mark.asyncio
    async def test_revoke_endpoint_doesnt_log_token_value(
        self,
        client,
        async_session,
        capturing_logger,
    ):
        """
        POST /oauth/focused/revoke should not log the token value.

        Both revoke.py (endpoint) and revoke_service.py have loggers.
        We patch both to capture all output and verify the token isn't logged.
        """
        from datetime import datetime, timedelta, timezone
        from backend.core.models import CoreUser, CoreConnection
        from backend.core.oauth_provider.models import OAuthAccessToken
        from backend.core.oauth_provider.jwt.utils import create_access_token
        from backend.core.encryption import encrypt_token
        import secrets

        logger, buffer = capturing_logger

        # Create test user and client
        user = CoreUser()
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        oauth_client = CoreConnection(
            user_id=None,
            provider="Test",
            connection_type="oauth_provider",
            client_id="test-revoke-endpoint-logging",
            client_secret_enc=encrypt_token("secret"),
            redirect_uris=["https://example.com/callback"],
            encrypted_access_token="",
            scopes=["focused.read"],
            token_expires_at=datetime.now(timezone.utc) + timedelta(days=365)
        )
        async_session.add(oauth_client)
        await async_session.commit()

        # Create an access token and store in DB
        access_token, jti = create_access_token(
            user_id=user.id,
            client_id="test-revoke-endpoint-logging",
            scope="focused.read"
        )

        # Store token in database so revoke can find it
        # Note: OAuthAccessToken uses refresh_token_enc (encrypted) and refresh_token_hash
        from backend.core.encryption import encrypt_token as encrypt_refresh, hash_refresh_token
        refresh_token_plain = secrets.token_urlsafe(32)

        token_record = OAuthAccessToken(
            jti=jti,
            user_id=user.id,
            client_id="test-revoke-endpoint-logging",
            scope=["focused.read"],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            refresh_token_enc=encrypt_refresh(refresh_token_plain),
            refresh_token_hash=hash_refresh_token(refresh_token_plain),
            refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        async_session.add(token_record)
        await async_session.commit()

        # Patch BOTH loggers: endpoint (revoke.py) and service (revoke_service.py)
        with patch(
            "backend.core.oauth_provider.revoke.logger",
            logger
        ), patch(
            "backend.core.oauth_provider.services.revoke_service.logger",
            logger
        ):
            await client.post(
                "/oauth/focused/revoke",
                data={
                    "token": access_token,
                    "client_id": "test-revoke-endpoint-logging"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

        log_output = buffer.getvalue()

        # Verify logging actually happened (test validity check)
        assert len(log_output) > 0, "Expected some log output from revoke endpoint"

        # Token should NOT appear in logs
        assert access_token not in log_output, \
            f"Token being revoked should not be logged. Found in: {log_output}"

        # First 20 chars of token should not appear either
        if len(access_token) > 20:
            assert access_token[:20] not in log_output, \
                f"Partial token should not be logged. Found in: {log_output}"
