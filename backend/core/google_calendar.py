"""
Google Calendar API client.
Reusable async client for Google Calendar API calls using httpx.
"""

import asyncio
import logging
import random
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def fetch_events(
    http_client: httpx.AsyncClient,
    access_token: str,
    time_min: str,
    time_max: str,
    max_results: int = 20
) -> dict[str, Any]:
    """
    Fetch events from Google Calendar API.

    Args:
        http_client: Shared httpx AsyncClient
        access_token: Decrypted Google access token
        time_min: Start time in ISO8601 format (e.g., "2024-01-15T00:00:00Z")
        time_max: End time in ISO8601 format
        max_results: Maximum events to return (1-50)

    Returns:
        Google Calendar API response with events

    Raises:
        ValueError: Invalid token (401), quota exceeded (403), or validation error
        httpx.HTTPStatusError: Other HTTP errors after retries
        httpx.TimeoutException: Timeout after retries
        httpx.NetworkError: Network error after retries
    """
    # Validate max_results
    if not (1 <= max_results <= 50):
        raise ValueError(f"max_results must be between 1 and 50, got {max_results}")

    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "FocusedApp/1.0 (+https://www.priority-guard.com)",
    }
    params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "maxResults": max_results,
        "singleEvents": "true",
        "orderBy": "startTime",
    }

    max_retries = 3
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            logger.info(
                f"Fetching events from Google Calendar (attempt {attempt + 1}/{max_retries})"
            )

            response = await http_client.get(url, headers=headers, params=params)

            if response.status_code == 200:
                logger.info("Events fetched successfully from Google Calendar")
                return response.json()

            elif response.status_code == 429:
                # Rate limit - respect Retry-After header
                retry_after = int(
                    response.headers.get("Retry-After", base_delay * (2**attempt))
                )
                delay = retry_after + random.uniform(0, 1)
                logger.warning(
                    f"Rate limited (429), retrying after {delay:.2f}s (attempt {attempt + 1}/{max_retries})"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise ValueError("API rate limit exceeded after retries")

            elif response.status_code == 401:
                # Invalid token - no retry
                logger.error("Invalid access token (401)")
                raise ValueError("Invalid access token")

            elif response.status_code == 403:
                # Quota exceeded - no retry
                logger.error("API daily quota exceeded (403)")
                raise ValueError("API daily quota exceeded")

            else:
                # Other HTTP errors
                logger.warning(
                    f"HTTP {response.status_code} from Google Calendar (attempt {attempt + 1}/{max_retries})"
                )
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt) + random.uniform(0, 1)
                    await asyncio.sleep(delay)
                    continue
                else:
                    response.raise_for_status()

        except (httpx.TimeoutException, httpx.NetworkError) as e:
            logger.warning(
                f"Network/timeout error (attempt {attempt + 1}/{max_retries}): {type(e).__name__}"
            )
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2**attempt) + random.uniform(0, 1)
            await asyncio.sleep(delay)

    # Should not reach here, but for safety
    raise ValueError("Failed to fetch events after maximum retries")
