#!/usr/bin/env python3
"""
Test to fetch calendar timezone from Google Calendar API.
"""

import asyncio
import httpx
from backend.core.database import AsyncSessionLocal
from backend.core.models import CoreConnection
from backend.core.encryption import decrypt_token
from sqlalchemy import select


async def test_calendar_timezone():
    """Fetch calendar metadata including timezone."""
    async with AsyncSessionLocal() as session:
        # Get connection for test_user
        stmt = select(CoreConnection).where(
            CoreConnection.user_id == "test_user",
            CoreConnection.provider == "google"
        )
        result = await session.execute(stmt)
        connection = result.scalar_one_or_none()

        if not connection:
            print("No connection found for test_user")
            return

        access_token = decrypt_token(connection.encrypted_access_token)

        # Fetch calendar metadata
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://www.googleapis.com/calendar/v3/calendars/primary",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            print("=== Calendar Metadata ===")
            print(f"Status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                print(f"\nCalendar ID: {data.get('id')}")
                print(f"Summary: {data.get('summary')}")
                print(f"Timezone: {data.get('timeZone')}")
                print(f"Description: {data.get('description', 'N/A')}")

                print(f"\nFull response:")
                import json
                print(json.dumps(data, indent=2))
            else:
                print(f"Error: {response.text}")


if __name__ == "__main__":
    asyncio.run(test_calendar_timezone())
