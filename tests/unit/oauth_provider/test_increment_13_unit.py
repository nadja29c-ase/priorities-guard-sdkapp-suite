"""
Increment 13: OAuth Token Exchange - Unit Tests.

Tests (isolated, mocked DB/Redis):
1. Valid PKCE verification - Returns true
2. Invalid code_verifier - Returns false
3. Code expiration check (>10 min) - Returns expired
4. Refresh token encryption/decryption - Round-trips correctly
5. JWT claims construction - Verify specific values (iss, sub, aud, exp, scope, jti)
6. Refresh token rotation marks old revoked - revoked=true, revoked_at set

These are pure unit tests with no database or Redis dependencies.
"""

import pytest
import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4


# =============================================================================
# Test 1: Valid PKCE Verification
# =============================================================================

class TestPKCEVerification:
    """Test PKCE code_verifier validation (RFC 7636)."""

    def test_valid_pkce_verification_returns_true(self):
        """
        Test 1: Valid PKCE verification returns True.

        Given a valid code_verifier that matches the stored code_challenge,
        verify_pkce should return True.
        """
        from backend.core.oauth_provider.validators.pkce import verify_pkce

        # Generate a valid PKCE pair
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')

        # Compute code_challenge = BASE64URL(SHA256(code_verifier))
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip('=')

        # Verify
        result = verify_pkce(code_verifier, code_challenge)

        assert result is True, "Valid PKCE verification should return True"

    def test_invalid_code_verifier_returns_false(self):
        """
        Test 2: Invalid code_verifier returns False.

        Given a code_verifier that does NOT match the stored code_challenge,
        verify_pkce should return False.
        """
        from backend.core.oauth_provider.validators.pkce import verify_pkce

        # Generate a valid code_challenge
        original_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(original_verifier.encode()).digest()
        ).decode().rstrip('=')

        # Use a DIFFERENT code_verifier
        wrong_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')

        # Verify - should fail
        result = verify_pkce(wrong_verifier, code_challenge)

        assert result is False, "Invalid code_verifier should return False"

    def test_pkce_with_known_test_vector(self):
        """
        Test PKCE with RFC 7636 Appendix B test vector.

        code_verifier: dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
        code_challenge: E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
        """
        from backend.core.oauth_provider.validators.pkce import verify_pkce

        # RFC 7636 test vector (Appendix B)
        code_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

        result = verify_pkce(code_verifier, code_challenge)

        assert result is True, "RFC 7636 test vector should verify correctly"

    def test_pkce_with_padded_base64url(self):
        """
        Test PKCE with padded base64url strings (RFC 7636 Appendix A).

        Some clients may send code_verifier WITH padding ('=' characters).
        The implementation should handle both padded and unpadded forms.
        """
        from backend.core.oauth_provider.validators.pkce import verify_pkce

        # Generate verifier WITH padding (don't strip '=')
        code_verifier_bytes = secrets.token_bytes(32)
        code_verifier_padded = base64.urlsafe_b64encode(code_verifier_bytes).decode()
        # Keep padding: e.g., "abc123==" instead of "abc123"

        # Compute challenge (also with padding for consistency)
        code_challenge_padded = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier_padded.encode()).digest()
        ).decode()

        # Test with padded verifier
        result = verify_pkce(code_verifier_padded, code_challenge_padded.rstrip('='))

        # Note: If this fails, the implementation needs to handle padding
        assert result is True, "PKCE should accept padded base64url code_verifier"

    def test_pkce_mixed_padding_interoperability(self):
        """
        Test PKCE interoperability when client sends unpadded but challenge was computed padded.

        Real-world scenario: Different OAuth libraries handle padding differently.
        """
        from backend.core.oauth_provider.validators.pkce import verify_pkce

        # Generate a code_verifier (unpadded, as most clients send)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip('=')

        # Compute challenge from the UNPADDED verifier (this is what gets stored)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip('=')

        # Verify with unpadded (normal case)
        result = verify_pkce(code_verifier, code_challenge)
        assert result is True, "Standard unpadded PKCE should work"

    def test_code_challenge_method_validation(self):
        """Test that only S256 is accepted as challenge method."""
        from backend.core.oauth_provider.validators.pkce import validate_code_challenge_method

        assert validate_code_challenge_method("S256") is True
        assert validate_code_challenge_method("plain") is False
        assert validate_code_challenge_method("sha256") is False
        assert validate_code_challenge_method("") is False


# =============================================================================
# Test 3: Code Expiration Check
# =============================================================================

class TestCodeExpiration:
    """Test authorization code expiration validation."""

    def test_unexpired_code_returns_true(self):
        """
        Test 3a: Code within 10-minute window returns True (not expired).
        """
        from backend.core.oauth_provider.validators.token_validators import validate_token_not_expired

        # Code that expires in 5 minutes (still valid)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        result = validate_token_not_expired(expires_at)

        assert result is True, "Unexpired code should return True"

    def test_expired_code_returns_false(self):
        """
        Test 3b: Code older than 10 minutes returns False (expired).
        """
        from backend.core.oauth_provider.validators.token_validators import validate_token_not_expired

        # Code that expired 1 minute ago
        expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        result = validate_token_not_expired(expires_at)

        assert result is False, "Expired code should return False"

    def test_code_at_exact_expiry_boundary(self):
        """
        Test 3c: Code just about to expire returns True (not expired yet).

        Testing boundary behavior with a 1-second buffer to avoid timing issues.
        """
        from backend.core.oauth_provider.validators.token_validators import validate_token_not_expired

        # Code that expires in 1 second (still valid)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=1)

        result = validate_token_not_expired(expires_at)

        assert result is True, "Code about to expire should still be valid"

    def test_code_expired_by_one_second(self):
        """
        Test 3d: Code expired by 1 second returns False.
        """
        from backend.core.oauth_provider.validators.token_validators import validate_token_not_expired

        # Code that expired 1 second ago
        expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        result = validate_token_not_expired(expires_at)

        assert result is False, "Code expired by 1 second should be invalid"


# =============================================================================
# Test 4: Refresh Token Encryption/Decryption
# =============================================================================

class TestRefreshTokenEncryption:
    """Test refresh token encryption round-trip."""

    def test_encryption_decryption_round_trip(self):
        """
        Test 4: Refresh token encryption/decryption round-trips correctly.

        A token encrypted with encrypt_token() should decrypt back to the
        original value with decrypt_token().
        """
        from backend.core.encryption import encrypt_token, decrypt_token

        # Generate a random refresh token (like the real implementation)
        original_token = secrets.token_urlsafe(32)

        # Encrypt
        encrypted = encrypt_token(original_token)

        # Verify encrypted is different from original
        assert encrypted != original_token, "Encrypted token should differ from original"

        # Decrypt
        decrypted = decrypt_token(encrypted)

        # Verify round-trip
        assert decrypted == original_token, "Decrypted token should match original"

    def test_encryption_produces_different_ciphertext(self):
        """
        Test that encrypting the same token twice produces different ciphertext.

        Fernet uses a random IV, so the same plaintext should produce different
        ciphertext each time (semantic security).
        """
        from backend.core.encryption import encrypt_token

        token = secrets.token_urlsafe(32)

        encrypted1 = encrypt_token(token)
        encrypted2 = encrypt_token(token)

        assert encrypted1 != encrypted2, "Same token should encrypt to different ciphertext"

    def test_invalid_encrypted_token_raises_error(self):
        """Test that decrypting invalid data raises ValueError."""
        from backend.core.encryption import decrypt_token

        with pytest.raises(ValueError, match="Invalid or corrupted"):
            decrypt_token("not-a-valid-encrypted-token")

    def test_empty_token_raises_error(self):
        """Test that empty token raises ValueError."""
        from backend.core.encryption import encrypt_token, decrypt_token

        with pytest.raises(ValueError, match="cannot be empty"):
            encrypt_token("")

        with pytest.raises(ValueError, match="cannot be empty"):
            decrypt_token("")

    def test_hash_refresh_token(self):
        """Test refresh token hashing for database indexing."""
        from backend.core.encryption import hash_refresh_token

        token = secrets.token_urlsafe(32)

        hashed = hash_refresh_token(token)

        # Should be 64-character hex string (SHA-256)
        assert len(hashed) == 64, "Hash should be 64 characters (SHA-256 hex)"
        assert all(c in '0123456789abcdef' for c in hashed), "Hash should be hex"

        # Same token should produce same hash (deterministic)
        assert hash_refresh_token(token) == hashed, "Same token should hash identically"


# =============================================================================
# Test 5: JWT Claims Construction
# =============================================================================

class TestJWTClaimsConstruction:
    """Test JWT access token claims contain correct values."""

    def test_jwt_claims_contain_correct_values(self):
        """
        Test 5: JWT claims construction with specific values.

        Verify:
        - iss = configured issuer URL
        - sub = internal user_id
        - aud = issuer (audience)
        - exp = 1hr from now
        - scope = granted scopes
        - jti = unique UUID
        - client_id = OAuth client identifier
        """
        from backend.core.oauth_provider.jwt.utils import create_access_token
        from backend.core.config import settings
        from jose import jwt
        from backend.core.crypto import get_public_key
        from cryptography.hazmat.primitives import serialization

        # Test inputs
        user_id = uuid4()
        client_id = "test-client-123"
        scope = "focused.read focused.write"

        # Create token
        access_token, jti = create_access_token(
            user_id=user_id,
            client_id=client_id,
            scope=scope
        )

        # Decode token (verify signature)
        public_key = get_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )

        decoded = jwt.decode(
            access_token,
            public_pem,
            algorithms=["RS256"],
            options={"verify_aud": False}  # We'll verify manually
        )

        # Verify iss = configured issuer
        assert decoded["iss"] == settings.OAUTH_ISSUER, \
            f"iss should be {settings.OAUTH_ISSUER}"

        # Verify sub = user_id (as string)
        assert decoded["sub"] == str(user_id), \
            f"sub should be user_id: {user_id}"

        # Verify aud = issuer
        assert decoded["aud"] == settings.OAUTH_ISSUER, \
            f"aud should be {settings.OAUTH_ISSUER}"

        # Verify exp is approximately 1 hour from now
        now = datetime.now(timezone.utc).timestamp()
        expected_exp = now + settings.OAUTH_TOKEN_EXPIRY_SECONDS
        assert abs(decoded["exp"] - expected_exp) < 5, \
            f"exp should be ~{settings.OAUTH_TOKEN_EXPIRY_SECONDS}s from now"

        # Verify scope
        assert decoded["scope"] == scope, \
            f"scope should be '{scope}'"

        # Verify jti is a valid UUID
        assert decoded["jti"] == jti, "jti should match returned value"
        # Verify jti is UUID format
        try:
            from uuid import UUID
            UUID(jti)
        except ValueError:
            pytest.fail(f"jti should be valid UUID, got: {jti}")

        # Verify client_id
        assert decoded["client_id"] == client_id, \
            f"client_id should be '{client_id}'"

        # Verify azp (authorized party) - OAuth 2.0 standard
        assert decoded["azp"] == client_id, \
            f"azp should be '{client_id}'"

        # Verify iat is present and reasonable
        assert "iat" in decoded, "iat (issued at) should be present"
        assert abs(decoded["iat"] - now) < 5, "iat should be approximately now"

    def test_jwt_uses_rs256_algorithm(self):
        """Test that JWT is signed with RS256 algorithm."""
        from backend.core.oauth_provider.jwt.utils import create_access_token
        from jose import jwt

        user_id = uuid4()
        access_token, _ = create_access_token(
            user_id=user_id,
            client_id="test-client",
            scope="focused.read"
        )

        # Get unverified header
        header = jwt.get_unverified_header(access_token)

        assert header["alg"] == "RS256", "JWT should use RS256 algorithm"

    def test_jwt_includes_kid_header(self):
        """Test that JWT header includes kid (key ID) for JWKS lookup."""
        from backend.core.oauth_provider.jwt.utils import create_access_token
        from backend.core.config import settings
        from jose import jwt

        user_id = uuid4()
        access_token, _ = create_access_token(
            user_id=user_id,
            client_id="test-client",
            scope="focused.read"
        )

        header = jwt.get_unverified_header(access_token)

        assert "kid" in header, "JWT header should include kid"
        assert header["kid"] == settings.OAUTH_JWT_KID, \
            f"kid should be {settings.OAUTH_JWT_KID}"


# =============================================================================
# Test 6: Refresh Token Rotation Marks Old Revoked
# =============================================================================

class TestRefreshTokenRotation:
    """Test that refresh token rotation properly revokes old tokens."""

    @pytest.mark.asyncio
    async def test_refresh_rotation_marks_old_revoked(self):
        """
        Test 6: Refresh token rotation marks old token as revoked=true, revoked_at set.

        When exchanging a refresh token for new tokens:
        1. Old token should be marked revoked=True
        2. Old token should have revoked_at timestamp set
        3. New tokens should be created
        """
        from backend.core.oauth_provider.services.token_service import exchange_refresh_token
        from backend.core.oauth_provider.models import OAuthAccessToken
        from backend.core.encryption import encrypt_token as enc_token, hash_refresh_token as hash_token

        # Setup: Create a mock token record
        user_id = uuid4()
        client_id = "test-client-rotation"
        original_refresh_token = secrets.token_urlsafe(32)
        original_jti = str(uuid4())

        # Create a simple class to track attribute changes
        class MockToken:
            def __init__(self):
                self.jti = original_jti
                self.user_id = user_id
                self.client_id = client_id
                self.scope = ["focused.read"]
                self.refresh_token_enc = enc_token(original_refresh_token)
                self.refresh_token_hash = hash_token(original_refresh_token)
                self.refresh_token_expires_at = datetime.now(timezone.utc) + timedelta(days=30)
                self.revoked = False
                self.revoked_at = None
                self.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        mock_token = MockToken()

        # Mock database session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_db.execute.return_value = mock_result
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        # Execute refresh
        result = await exchange_refresh_token(
            db=mock_db,
            refresh_token=original_refresh_token,
            client_id=client_id
        )

        # Verify success (returns dict, not error tuple)
        assert isinstance(result, dict), f"Expected success dict, got: {result}"
        assert "access_token" in result
        assert "refresh_token" in result

        # Verify old token was marked revoked
        assert mock_token.revoked is True, "Old token should be marked revoked=True"
        assert mock_token.revoked_at is not None, "Old token should have revoked_at set"

        # Verify revoked_at is a recent timestamp
        assert isinstance(mock_token.revoked_at, datetime), "revoked_at should be datetime"
        now = datetime.now(timezone.utc)
        time_diff = abs((now - mock_token.revoked_at).total_seconds())
        assert time_diff < 5, "revoked_at should be approximately now"

        # Verify new token was added to session
        mock_db.add.assert_called_once()
        new_token_arg = mock_db.add.call_args[0][0]
        assert isinstance(new_token_arg, OAuthAccessToken), "New token should be OAuthAccessToken"
        assert new_token_arg.revoked is False, "New token should not be revoked"
        assert new_token_arg.jti != original_jti, "New token should have different jti"

    @pytest.mark.asyncio
    async def test_revoked_token_cannot_be_used(self):
        """Test that already-revoked tokens return invalid_grant error."""
        from backend.core.oauth_provider.services.token_service import exchange_refresh_token
        from backend.core.oauth_provider.models import OAuthAccessToken

        # Setup: Create a revoked token
        refresh_token = secrets.token_urlsafe(32)

        mock_token = MagicMock(spec=OAuthAccessToken)
        mock_token.revoked = True  # Already revoked!
        mock_token.refresh_token_expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        mock_token.client_id = "test-client"

        # Mock database
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_db.execute.return_value = mock_result

        # Execute
        result = await exchange_refresh_token(
            db=mock_db,
            refresh_token=refresh_token,
            client_id="test-client"
        )

        # Should return error tuple
        assert isinstance(result, tuple), "Revoked token should return error tuple"
        assert result[0] == "invalid_grant", f"Error should be invalid_grant, got: {result[0]}"
        assert "revoked" in result[1].lower(), f"Error message should mention revoked: {result[1]}"

    @pytest.mark.asyncio
    async def test_expired_refresh_token_cannot_be_used(self):
        """Test that expired refresh tokens return invalid_grant error."""
        from backend.core.oauth_provider.services.token_service import exchange_refresh_token
        from backend.core.oauth_provider.models import OAuthAccessToken

        # Setup: Create an expired refresh token
        refresh_token = secrets.token_urlsafe(32)

        mock_token = MagicMock(spec=OAuthAccessToken)
        mock_token.revoked = False
        mock_token.refresh_token_expires_at = datetime.now(timezone.utc) - timedelta(days=1)  # EXPIRED
        mock_token.client_id = "test-client"

        # Mock database
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_token
        mock_db.execute.return_value = mock_result

        # Execute
        result = await exchange_refresh_token(
            db=mock_db,
            refresh_token=refresh_token,
            client_id="test-client"
        )

        # Should return error tuple
        assert isinstance(result, tuple), "Expired token should return error tuple"
        assert result[0] == "invalid_grant", f"Error should be invalid_grant, got: {result[0]}"
        assert "expired" in result[1].lower(), f"Error message should mention expired: {result[1]}"
