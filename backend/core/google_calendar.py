"""
Google Calendar API client.
Reusable async client for Google Calendar API calls using httpx.
"""

import asyncio
import logging
import random
from typing import Any

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)


async def refresh_access_token(
    http_client: httpx.AsyncClient,
    refresh_token: str
) -> dict:
    """
    Refresh Google OAuth access token using refresh token.

    Args:
        http_client: Shared httpx AsyncClient
        refresh_token: Decrypted Google refresh token

    Returns:
        Google token response with access_token and expires_in

    Raises:
        ValueError: Invalid refresh token (400), quota exceeded (403), or after max retries
        httpx.RequestError: Network error after max retries
    """
    url = "https://oauth2.googleapis.com/token"

    data = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    headers = {
        "User-Agent": "FocusedApp/1.0 (+https://www.priority-guard.com)"
    }

    max_retries = 3
    base_delay = 1

    for attempt in range(max_retries):
        try:
            response = await http_client.post(url, data=data, headers=headers)

            if response.status_code == 200:
                logger.info("Token refresh successful")
                return response.json()

            elif response.status_code == 400:
                # invalid_grant - no retry
                logger.error("Token refresh failed: Refresh token invalid")
                raise ValueError("Refresh token invalid")

            elif response.status_code == 403:
                # quotaExceeded - no retry
                logger.error("Token refresh failed: API quota exceeded")
                raise ValueError("API quota exceeded")

            elif response.status_code == 429:
                # rateLimitExceeded - retry with Retry-After
                retry_after = int(
                    response.headers.get("Retry-After", base_delay * (2**attempt))
                )
                delay = retry_after + random.uniform(0, 1)
                logger.warning(f"Retry attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error("Token refresh failed: Rate limit exceeded after retries")
                    raise ValueError("API quota exceeded")

            elif response.status_code in (500, 503):
                # Google server error - retry
                logger.warning(f"Retry attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt) + random.uniform(0, 1)
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error("Token refresh failed: Server error after retries")
                    raise ValueError("Server error after retries")

            else:
                # Other HTTP errors - retry
                logger.warning(f"Retry attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt) + random.uniform(0, 1)
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Token refresh failed: HTTP {response.status_code}")
                    raise ValueError(f"HTTP {response.status_code} after retries")

        except httpx.RequestError as e:
            # Network failure - retry
            logger.warning(f"Retry attempt {attempt + 1}")
            if attempt == max_retries - 1:
                logger.error(f"Token refresh failed: {type(e).__name__}")
                raise
            delay = base_delay * (2**attempt) + random.uniform(0, 1)
            await asyncio.sleep(delay)

    # Should not reach here, but for safety
    raise ValueError("Token refresh failed after retries")


async def stop_webhook(
    http_client: httpx.AsyncClient,
    access_token: str,
    channel_id: str,
    resource_id: str
) -> bool:
    """
    Stop an existing Google Calendar webhook channel.

    Args:
        http_client: Shared httpx AsyncClient
        access_token: Decrypted Google access token
        channel_id: Channel ID to stop
        resource_id: Resource ID associated with the channel

    Returns:
        True if stopped successfully or channel not found, False on other errors

    Note:
        This function never raises exceptions. It logs warnings and returns False
        on failure to avoid blocking new webhook registration.
    """
    url = "https://www.googleapis.com/calendar/v3/channels/stop"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "FocusedApp/1.0 (+https://www.priority-guard.com)",
        "Content-Type": "application/json",
    }

    body = {
        "id": channel_id,
        "resourceId": resource_id,
    }

    try:
        response = await http_client.post(url, headers=headers, json=body)

        if response.status_code == 200:
            logger.info(f"Webhook channel stopped successfully: {channel_id}")
            return True

        elif response.status_code == 404:
            # Channel not found (already expired or invalid) - this is OK
            logger.info(f"Webhook channel not found (already stopped/expired): {channel_id}")
            return True

        else:
            logger.warning(
                f"Failed to stop webhook channel {channel_id}: HTTP {response.status_code}"
            )
            return False

    except Exception as e:
        logger.warning(
            f"Exception while stopping webhook channel {channel_id}: {type(e).__name__}"
        )
        return False


async def register_webhook(
    http_client: httpx.AsyncClient,
    access_token: str,
    channel_id: str,
    user_id: str
) -> dict:
    """
    Register a Google Calendar push notification webhook.

    Args:
        http_client: Shared httpx AsyncClient
        access_token: Decrypted Google access token
        channel_id: Unique channel ID (UUID hex)
        user_id: User ID for webhook URL

    Returns:
        Google API response with channel_id, resource_id, and expiration

    Raises:
        ValueError: Invalid request (400), quota exceeded (403), or after max retries
        httpx.RequestError: Network error after max retries
    """
    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events/watch"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "FocusedApp/1.0 (+https://www.priority-guard.com)",
        "Content-Type": "application/json",
    }

    body = {
        "id": channel_id,
        "type": "web_hook",
        "address": f"https://www.priority-guard.com/webhook/focused/google_calendar/{user_id}",
    }

    max_retries = 3
    base_delay = 1

    for attempt in range(max_retries):
        try:
            response = await http_client.post(url, headers=headers, json=body)

            if response.status_code == 200:
                logger.info("Webhook registered successfully")
                return response.json()

            elif response.status_code == 400:
                # Invalid request - no retry
                logger.error("Webhook registration failed: Invalid request")
                raise ValueError("Invalid webhook request")

            elif response.status_code == 403:
                # Quota exceeded - no retry
                logger.error("Webhook registration failed: API quota exceeded")
                raise ValueError("API quota exceeded")

            elif response.status_code == 429:
                # Rate limit - retry with Retry-After
                retry_after = int(
                    response.headers.get("Retry-After", base_delay * (2**attempt))
                )
                delay = retry_after + random.uniform(0, 1)
                logger.warning(f"Retry attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error("Webhook registration failed: Rate limit exceeded after retries")
                    raise ValueError("API quota exceeded")

            elif response.status_code in (500, 503):
                # Google server error - retry
                logger.warning(f"Retry attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt) + random.uniform(0, 1)
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error("Webhook registration failed: Server error after retries")
                    raise ValueError("Server error after retries")

            else:
                # Other HTTP errors - retry
                logger.warning(f"Retry attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt) + random.uniform(0, 1)
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Webhook registration failed: HTTP {response.status_code}")
                    raise ValueError(f"HTTP {response.status_code} after retries")

        except httpx.RequestError as e:
            # Network failure - retry
            logger.warning(f"Retry attempt {attempt + 1}")
            if attempt == max_retries - 1:
                logger.error(f"Webhook registration failed: {type(e).__name__}")
                raise
            delay = base_delay * (2**attempt) + random.uniform(0, 1)
            await asyncio.sleep(delay)

    # Should not reach here, but for safety
    raise ValueError("Webhook registration failed after retries")


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
