"""
Manual test script for database and encryption functionality.

Tests:
- Encryption/decryption round-trip
- Database insert and retrieve
- Token security (never prints token values)
"""

import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from backend.core.database import AsyncSessionLocal
from backend.core.models import CoreConnection
from backend.core.encryption import encrypt_token, decrypt_token


async def test_database_and_encryption():
    """Test database operations with encrypted tokens."""
    print("Starting database and encryption test...")

    # Test token (example only)
    test_access_token = "test_access_token_12345"
    test_refresh_token = "test_refresh_token_67890"
    test_user_id = "test_user_123"
    test_provider = "google"

    try:
        # Test encryption/decryption
        print("Testing encryption/decryption...")
        encrypted_access = encrypt_token(test_access_token)
        encrypted_refresh = encrypt_token(test_refresh_token)

        decrypted_access = decrypt_token(encrypted_access)
        decrypted_refresh = decrypt_token(encrypted_refresh)

        assert decrypted_access == test_access_token, "Access token decryption failed"
        assert decrypted_refresh == test_refresh_token, "Refresh token decryption failed"
        print("✓ Encryption/decryption working correctly")

        # Test database operations
        print("Testing database operations...")
        async with AsyncSessionLocal() as session:
            # Create test connection
            connection = CoreConnection(
                user_id=test_user_id,
                provider=test_provider,
                encrypted_access_token=encrypted_access,
                encrypted_refresh_token=encrypted_refresh,
                token_expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                scopes=["https://www.googleapis.com/auth/calendar.readonly"],
            )

            session.add(connection)
            await session.commit()
            print("✓ Record inserted successfully")

            # Retrieve and verify
            result = await session.execute(
                select(CoreConnection).where(
                    CoreConnection.user_id == test_user_id,
                    CoreConnection.provider == test_provider,
                )
            )
            retrieved = result.scalar_one()

            # Decrypt and verify
            retrieved_access = decrypt_token(retrieved.encrypted_access_token)
            retrieved_refresh = decrypt_token(retrieved.encrypted_refresh_token)

            assert retrieved_access == test_access_token, "Retrieved access token mismatch"
            assert retrieved_refresh == test_refresh_token, "Retrieved refresh token mismatch"
            assert retrieved.user_id == test_user_id, "User ID mismatch"
            assert retrieved.provider == test_provider, "Provider mismatch"
            print("✓ Record retrieved and decrypted successfully")

            # Clean up
            await session.delete(retrieved)
            await session.commit()
            print("✓ Test record deleted")

        print("\n✅ All tests passed successfully!")
        print("Database and encryption are working correctly.")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(test_database_and_encryption())
