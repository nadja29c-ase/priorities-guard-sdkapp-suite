#!/usr/bin/env python3
"""
Manual Production Testing Script for Priority Guardian OAuth Flows.

This script helps you manually test the deployed PG backend by:
1. Providing step-by-step instructions
2. Generating test URLs
3. Verifying database state after each step

Usage:
    python scripts/manual_test_production.py --prod-url https://your-backend.com

    # Or with database connection string
    python scripts/manual_test_production.py \
        --prod-url https://your-backend.com \
        --db-url postgresql+asyncpg://user:pass@host:5432/db
"""

import argparse
import asyncio
import sys
import os
from uuid import uuid4

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_box(title: str, content: list[str]):
    """Print a nice box with content."""
    width = max(len(title), max(len(line) for line in content)) + 4
    print()
    print("┌" + "─" * width + "┐")
    print("│ " + title.center(width - 2) + " │")
    print("├" + "─" * width + "┤")
    for line in content:
        print("│ " + line.ljust(width - 2) + " │")
    print("└" + "─" * width + "┘")
    print()


def print_step(num: int, title: str):
    """Print a step header."""
    print(f"\n{'='*60}")
    print(f"  STEP {num}: {title}")
    print(f"{'='*60}\n")


def wait_for_enter(prompt: str = "Press Enter when done..."):
    """Wait for user to press Enter."""
    input(f"\n  >>> {prompt}")


async def verify_db_connection(db_url: str, user_id: str) -> dict | None:
    """Query the production database to verify OAuth state."""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select, text

        engine = create_async_engine(db_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # Check for Google connection
            result = await session.execute(
                text("""
                    SELECT
                        id,
                        user_id,
                        provider,
                        connection_type,
                        scopes,
                        encrypted_access_token IS NOT NULL as has_access_token,
                        encrypted_refresh_token IS NOT NULL as has_refresh_token,
                        token_expires_at,
                        revoked_at,
                        created_at
                    FROM core_connections
                    WHERE user_id = :user_id
                    AND provider = 'google'
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"user_id": user_id}
            )
            row = result.fetchone()

            if row:
                return {
                    "id": str(row[0]),
                    "user_id": row[1],
                    "provider": row[2],
                    "connection_type": row[3],
                    "scopes": row[4],
                    "has_access_token": row[5],
                    "has_refresh_token": row[6],
                    "token_expires_at": str(row[7]) if row[7] else None,
                    "revoked_at": str(row[8]) if row[8] else None,
                    "created_at": str(row[9]) if row[9] else None,
                }
            return None

    except Exception as e:
        print(f"  ✗ Database error: {e}")
        return None


async def verify_user_exists(db_url: str, user_id: str) -> bool:
    """Check if user exists in database."""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import text

        engine = create_async_engine(db_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            result = await session.execute(
                text("SELECT id FROM core_users WHERE id = :user_id"),
                {"user_id": user_id}
            )
            return result.fetchone() is not None

    except Exception as e:
        print(f"  ✗ Database error: {e}")
        return False


def run_chatgpt_oauth_test(prod_url: str):
    """Guide through ChatGPT OAuth testing."""
    print_step(1, "ChatGPT OAuth Flow Test")

    print("  This tests user authentication via ChatGPT.")
    print()
    print("  The flow is:")
    print("  1. ChatGPT calls /oauth/authorize")
    print("  2. User is redirected to Google Sign-In")
    print("  3. After sign-in, user is redirected back to ChatGPT")
    print("  4. ChatGPT exchanges code for tokens via /oauth/token")
    print()

    # Generate test URLs
    state = f"test-state-{uuid4().hex[:8]}"

    authorize_url = (
        f"{prod_url}/oauth/authorize"
        f"?client_id=chatgpt"
        f"&redirect_uri=https://chat.openai.com/aip/g-xxx/oauth/callback"
        f"&response_type=code"
        f"&state={state}"
        f"&scope=openid%20profile"
    )

    print_box("TEST URL", [
        "Open this URL in your browser:",
        "",
        authorize_url[:80],
        authorize_url[80:160] if len(authorize_url) > 80 else "",
        authorize_url[160:] if len(authorize_url) > 160 else "",
    ])

    print("  Expected behavior:")
    print("  ✓ Should redirect to Google Sign-In")
    print("  ✓ After sign-in, redirects to ChatGPT callback")
    print("  ✓ ChatGPT receives authorization code")
    print()
    print("  What to verify:")
    print("  • Google Sign-In page appears")
    print("  • After sign-in, you're redirected (may show error if callback URL invalid)")
    print("  • Check browser URL contains 'code=' parameter")

    wait_for_enter()


def run_google_oauth_test(prod_url: str, db_url: str | None):
    """Guide through Google OAuth (calendar connection) testing."""
    print_step(2, "Google OAuth Flow Test (Calendar Connection)")

    print("  This tests connecting Google Calendar to Priority Guardian.")
    print()
    print("  The flow is:")
    print("  1. MCP calls /api/pg/google/initiate-connection")
    print("  2. Returns a connect_url with opaque token")
    print("  3. User opens connect_url in browser")
    print("  4. User authorizes calendar.events.readonly scope")
    print("  5. Callback stores encrypted tokens in database")
    print()

    # We need to call the API to get a real token
    print("  To test this flow, you need to:")
    print()
    print("  Option A: Use curl to initiate connection")
    print("  ─────────────────────────────────────────")

    test_user_id = str(uuid4())

    print(f"""
  Run this curl command:

  curl -X POST "{prod_url}/api/pg/google/initiate-connection" \\
       -H "X-User-ID: {test_user_id}" \\
       -H "Content-Type: application/json"

  This will return:
  {{
    "token": "abc123...",
    "connect_url": "{prod_url}/auth/google/start?token=abc123...",
    "expires_in": 600
  }}

  Then open the connect_url in your browser.
""")

    print("  Option B: Use the MCP tool directly")
    print("  ────────────────────────────────────")
    print("  Ask ChatGPT: 'Connect my Google Calendar'")
    print("  The MCP will call the API and show you the connect_url")
    print()

    print_box("EXPECTED SCOPE", [
        "The Google consent screen should request:",
        "",
        "  'See your Google Calendar events'",
        "  (calendar.events.readonly)",
        "",
        "NOT 'See and download your calendar' (calendar.readonly)",
    ])

    print("  What to verify:")
    print("  ✓ Consent screen shows 'calendar events' not 'full calendar'")
    print("  ✓ After authorization, redirected to success page")
    print("  ✓ No error messages")

    wait_for_enter("Press Enter after completing OAuth flow...")

    # Verify database if connection string provided
    if db_url:
        print("\n  Verifying database state...")

        user_id_input = input(f"\n  Enter the User ID used (or press Enter for {test_user_id[:8]}...): ").strip()
        if not user_id_input:
            user_id_input = test_user_id

        connection = asyncio.run(verify_db_connection(db_url, user_id_input))

        if connection:
            print("\n  ✓ Google connection found in database!")
            print()
            print(f"    User ID:          {connection['user_id']}")
            print(f"    Provider:         {connection['provider']}")
            print(f"    Scopes:           {connection['scopes']}")
            print(f"    Has Access Token: {connection['has_access_token']}")
            print(f"    Has Refresh Token:{connection['has_refresh_token']}")
            print(f"    Token Expires:    {connection['token_expires_at']}")
            print(f"    Revoked:          {connection['revoked_at']}")
            print(f"    Created:          {connection['created_at']}")
            print()

            # Verify scope
            expected_scope = "https://www.googleapis.com/auth/calendar.events.readonly"
            if expected_scope in (connection['scopes'] or []):
                print("  ✓ Correct scope stored (calendar.events.readonly)")
            else:
                print(f"  ✗ Wrong scope! Got: {connection['scopes']}")
                print(f"    Expected: {expected_scope}")
        else:
            print("\n  ✗ No Google connection found for this user.")
            print("    Make sure you used the correct User ID.")
    else:
        print("\n  (Skipping database verification - no --db-url provided)")


def run_disconnect_test(prod_url: str, db_url: str | None):
    """Guide through disconnect/revoke testing."""
    print_step(3, "Disconnect Flow Test")

    print("  This tests revoking the Google Calendar connection.")
    print()

    test_user_id = input("  Enter User ID to disconnect: ").strip()

    if not test_user_id:
        print("  Skipping disconnect test (no user ID provided)")
        return

    print(f"""
  Run this curl command:

  curl -X POST "{prod_url}/api/pg/google/disconnect" \\
       -H "X-User-ID: {test_user_id}" \\
       -H "Content-Type: application/json"

  Expected response:
  {{"status": "disconnected"}}
""")

    wait_for_enter("Press Enter after running disconnect...")

    if db_url:
        print("\n  Verifying disconnection...")

        connection = asyncio.run(verify_db_connection(db_url, test_user_id))

        if connection:
            if connection['revoked_at']:
                print(f"\n  ✓ Connection revoked at: {connection['revoked_at']}")
            else:
                print("\n  ✗ Connection not revoked (revoked_at is null)")
        else:
            print("\n  ✗ Connection not found")


def run_connection_status_test(prod_url: str):
    """Test connection status endpoint."""
    print_step(4, "Connection Status Test")

    test_user_id = input("  Enter User ID to check status: ").strip()

    if not test_user_id:
        print("  Skipping status test (no user ID provided)")
        return

    print(f"""
  Run this curl command:

  curl -X GET "{prod_url}/api/pg/google/connection-status" \\
       -H "X-User-ID: {test_user_id}"

  Expected response (connected):
  {{
    "connected": true,
    "connected_at": "2025-01-15T10:30:00Z",
    "scopes": ["https://www.googleapis.com/auth/calendar.events.readonly"]
  }}

  Expected response (not connected):
  {{"connected": false}}
""")

    wait_for_enter()


def print_summary():
    """Print test summary checklist."""
    print_step(5, "Test Summary Checklist")

    print("""
  ChatGPT OAuth Flow:
  [ ] /oauth/authorize redirects to Google Sign-In
  [ ] After sign-in, redirects to ChatGPT with code
  [ ] User appears in database after first sign-in

  Google Calendar Connection:
  [ ] /api/pg/google/initiate-connection returns token and URL
  [ ] connect_url redirects to Google consent screen
  [ ] Consent screen shows "calendar.events.readonly" scope
  [ ] After authorization, shows success page
  [ ] Database has connection with correct scope
  [ ] Access token and refresh token are stored (encrypted)

  Disconnect:
  [ ] /api/pg/google/disconnect revokes connection
  [ ] Database shows revoked_at timestamp
  [ ] Google token is revoked (check Google account permissions)

  Connection Status:
  [ ] Returns connected: true when connected
  [ ] Returns connected: false when disconnected
  [ ] Scopes array matches what was granted
""")


def main():
    parser = argparse.ArgumentParser(
        description="Manual Production Testing Script for PG OAuth",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic test (no database verification)
  python scripts/manual_test_production.py --prod-url https://api.priority-guard.com

  # With database verification
  python scripts/manual_test_production.py \\
      --prod-url https://api.priority-guard.com \\
      --db-url "postgresql+asyncpg://user:pass@host:5432/dbname"
        """
    )
    parser.add_argument(
        "--prod-url",
        required=True,
        help="Production backend URL (e.g., https://api.priority-guard.com)"
    )
    parser.add_argument(
        "--db-url",
        help="Database connection string for verification (optional)"
    )
    parser.add_argument(
        "--skip-chatgpt",
        action="store_true",
        help="Skip ChatGPT OAuth test"
    )
    parser.add_argument(
        "--skip-google",
        action="store_true",
        help="Skip Google OAuth test"
    )

    args = parser.parse_args()

    print("\n" + "="*60)
    print("  PRIORITY GUARDIAN - PRODUCTION OAUTH TESTING")
    print("="*60)
    print(f"\n  Production URL: {args.prod_url}")
    print(f"  Database URL:   {'Provided' if args.db_url else 'Not provided (skip DB checks)'}")
    print()

    if not args.skip_chatgpt:
        run_chatgpt_oauth_test(args.prod_url)

    if not args.skip_google:
        run_google_oauth_test(args.prod_url, args.db_url)
        run_disconnect_test(args.prod_url, args.db_url)
        run_connection_status_test(args.prod_url)

    print_summary()

    print("\n  Testing complete!\n")


if __name__ == "__main__":
    main()
