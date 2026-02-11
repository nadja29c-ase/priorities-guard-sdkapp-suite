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

# Canonical User-Agent for all Google API calls
# Google recommends including UA string for API requests
GOOGLE_USER_AGENT = "Focused/1.0 (+https://www.priority-guard.com)"


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
        "User-Agent": GOOGLE_USER_AGENT
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
        "User-Agent": GOOGLE_USER_AGENT,
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
        "User-Agent": GOOGLE_USER_AGENT,
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


async def list_events(
    http_client: httpx.AsyncClient,
    access_token: str,
    time_min: str,
    time_max: str,
    max_results_per_page: int = 250,
    max_pages: int = 10
) -> tuple[list[dict[str, Any]], int]:
    """
    Fetch events from Google Calendar API with pagination support.

    Used by Increment 6B sync pipeline to fetch all events in a time window.
    Handles pagination automatically via nextPageToken.

    Args:
        http_client: Shared httpx AsyncClient
        access_token: Decrypted Google access token
        time_min: Start time in ISO8601 format (e.g., "2024-01-15T00:00:00Z")
        time_max: End time in ISO8601 format
        max_results_per_page: Maximum events per page (default 250, max allowed by Google)
        max_pages: Maximum number of pages to fetch (default 10 = 2500 events max)

    Returns:
        Tuple of (events, pages_failed):
        - events: List of all events fetched from successful pages
        - pages_failed: Number of pages that failed after retries

    Raises:
        ValueError: Invalid token (401), quota exceeded (403), or validation error
        httpx.HTTPStatusError: Other HTTP errors after retries (only if ALL pages fail)

    Note:
        - Continues fetching remaining pages even if some pages fail
        - Stops after max_pages even if more pages exist (protection against infinite loops)
        - Adds 100ms delay between pages if fetching more than 3 pages (rate limiting)
        - Returns all successfully fetched events even if some pages failed
        - Only raises if NO pages succeeded (complete failure)
    """
    # Validate max_results_per_page
    if not (1 <= max_results_per_page <= 250):
        raise ValueError(f"max_results_per_page must be between 1 and 250, got {max_results_per_page}")

    url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": GOOGLE_USER_AGENT,
    }

    base_params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "maxResults": max_results_per_page,
        "singleEvents": "true",
        "orderBy": "startTime",
    }

    all_events = []
    pages_failed = 0
    page_count = 0
    next_page_token = None

    max_retries = 3
    base_delay = 1.0

    while page_count < max_pages:
        page_count += 1
        page_succeeded = False

        # Add pagination token if present
        params = base_params.copy()
        if next_page_token:
            params["pageToken"] = next_page_token

        # Retry logic for this page
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"Fetching events page {page_count}/{max_pages} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )

                response = await http_client.get(url, headers=headers, params=params)

                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])
                    all_events.extend(items)

                    logger.info(
                        f"Page {page_count}: fetched {len(items)} events "
                        f"(total so far: {len(all_events)})"
                    )

                    # Check for next page
                    next_page_token = data.get("nextPageToken")

                    # Mark this page as succeeded
                    page_succeeded = True

                    if not next_page_token:
                        # No more pages
                        logger.info(
                            f"No more pages. Total events fetched: {len(all_events)}, "
                            f"pages failed: {pages_failed}"
                        )
                        return all_events, pages_failed

                    # Add delay between pages if fetching many pages (rate limiting)
                    if page_count >= 3:
                        await asyncio.sleep(0.1)  # 100ms delay

                    # Break retry loop, move to next page
                    break

                elif response.status_code == 429:
                    # Rate limit - respect Retry-After header
                    retry_after = int(
                        response.headers.get("Retry-After", base_delay * (2**attempt))
                    )
                    delay = retry_after + random.uniform(0, 1)
                    logger.warning(
                        f"Rate limited (429), retrying after {delay:.2f}s "
                        f"(page {page_count}, attempt {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay)
                        continue
                    else:
                        # Rate limit exhausted - treat as page failure
                        logger.error(
                            f"Page {page_count} failed: API rate limit exceeded after retries"
                        )
                        break  # Exit retry loop, mark page as failed

                elif response.status_code == 401:
                    # Invalid token - fatal error, don't continue
                    logger.error("Invalid access token (401)")
                    if len(all_events) == 0:
                        # No events fetched yet, raise
                        raise ValueError("Invalid access token")
                    else:
                        # Some events fetched, return what we have
                        logger.warning("Returning partial results due to auth error")
                        return all_events, pages_failed + 1

                elif response.status_code == 403:
                    # Quota exceeded - fatal error, don't continue
                    logger.error("API daily quota exceeded (403)")
                    if len(all_events) == 0:
                        # No events fetched yet, raise
                        raise ValueError("API daily quota exceeded")
                    else:
                        # Some events fetched, return what we have
                        logger.warning("Returning partial results due to quota error")
                        return all_events, pages_failed + 1

                else:
                    # Other HTTP errors
                    logger.warning(
                        f"HTTP {response.status_code} from Google Calendar "
                        f"(page {page_count}, attempt {attempt + 1}/{max_retries})"
                    )
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt) + random.uniform(0, 1)
                        await asyncio.sleep(delay)
                        continue
                    else:
                        # Other HTTP error exhausted - treat as page failure
                        logger.error(
                            f"Page {page_count} failed: HTTP {response.status_code} after retries"
                        )
                        break  # Exit retry loop, mark page as failed

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                logger.warning(
                    f"Network/timeout error (page {page_count}, attempt {attempt + 1}/{max_retries}): "
                    f"{type(e).__name__}"
                )
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt) + random.uniform(0, 1)
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Network error exhausted - treat as page failure
                    logger.error(
                        f"Page {page_count} failed: {type(e).__name__} after retries"
                    )
                    break  # Exit retry loop, mark page as failed

        # After retry loop: check if page succeeded
        if not page_succeeded:
            pages_failed += 1
            logger.warning(
                f"Page {page_count} failed after {max_retries} attempts. "
                f"Continuing with remaining pages."
            )
            # Continue to next page (if pagination allowed continuation)
            # For now, we can't continue without next_page_token, so we break
            if not next_page_token:
                break

    # Reached max_pages limit or ran out of pages
    if page_count >= max_pages:
        logger.warning(
            f"Reached max_pages limit ({max_pages}). "
            f"Total events fetched: {len(all_events)}, pages failed: {pages_failed}. "
            f"More pages may exist but were not fetched."
        )
    else:
        logger.info(
            f"Completed pagination. Total events fetched: {len(all_events)}, "
            f"pages failed: {pages_failed}"
        )

    # If NO events fetched and pages failed, raise error
    if len(all_events) == 0 and pages_failed > 0:
        raise ValueError(f"All {pages_failed} page(s) failed")

    return all_events, pages_failed


# ============================================================================
# Webhook Channel Management (Increment 10)
# ============================================================================


async def stop_webhook_channel(
    http_client: httpx.AsyncClient,
    access_token: str,
    channel_id: str,
    resource_id: str,
) -> dict[str, Any]:
    """
    Stop a Google Calendar webhook channel.

    Sends a request to Google to stop receiving push notifications
    for this channel. Should be called during user disconnect/offboarding.

    Per Google docs:
    https://developers.google.com/calendar/api/guides/push#stopping-notifications

    Args:
        http_client: Shared httpx AsyncClient
        access_token: Valid Google access token
        channel_id: The webhook channel ID to stop
        resource_id: The resource ID associated with the channel

    Returns:
        Dictionary with:
        - success: bool
        - error: str | None (if failed)

    Note:
        - Returns success=True even if channel was already stopped or expired
        - Logs warning on failure but does not raise (non-blocking)
    """
    stop_url = "https://www.googleapis.com/calendar/v3/channels/stop"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": GOOGLE_USER_AGENT,
    }

    body = {
        "id": channel_id,
        "resourceId": resource_id,
    }

    try:
        response = await http_client.post(stop_url, headers=headers, json=body)

        # 200 OK or 204 No Content = success
        if response.status_code in (200, 204):
            logger.info(f"Webhook channel stopped: channel_id={channel_id}")
            return {"success": True, "error": None}

        # 404 = channel not found (already stopped or expired) - still success
        if response.status_code == 404:
            logger.info(
                f"Webhook channel not found (already stopped/expired): "
                f"channel_id={channel_id}"
            )
            return {"success": True, "error": None}

        # 401 = invalid token - log warning, non-blocking
        if response.status_code == 401:
            logger.warning(
                f"Cannot stop webhook channel (invalid token): "
                f"channel_id={channel_id}"
            )
            return {"success": False, "error": "invalid_token"}

        # Other errors
        error_text = response.text if response.content else f"HTTP {response.status_code}"
        logger.warning(
            f"Failed to stop webhook channel: channel_id={channel_id}, "
            f"status={response.status_code}, error={error_text}"
        )
        return {"success": False, "error": error_text}

    except Exception as e:
        logger.error(f"Error stopping webhook channel: channel_id={channel_id}, error={e}")
        return {"success": False, "error": str(e)}


# ============================================================================
# Calendar Settings (Increment 05 - Time Allocation Pipeline)
# ============================================================================


async def get_user_timezone(
    http_client: httpx.AsyncClient,
    access_token: str,
    correlation_id: str | None = None,
) -> str:
    """
    Fetch user's timezone from Google Calendar Settings API.

    Args:
        http_client: Shared httpx AsyncClient
        access_token: Decrypted Google access token
        correlation_id: Optional correlation ID for logging

    Returns:
        IANA timezone string (e.g., "Europe/Berlin", "America/New_York")
        Falls back to "UTC" on any error

    Note:
        This function never raises. On any failure (401, 403, network error,
        timeout, unexpected response), it logs a warning and returns "UTC".
        The calendar endpoint continues with UTC rather than failing entirely.
    """
    url = "https://www.googleapis.com/calendar/v3/users/me/settings/timezone"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": GOOGLE_USER_AGENT,
    }

    log_context = {"correlation_id": correlation_id} if correlation_id else {}

    try:
        response = await http_client.get(url, headers=headers, timeout=10.0)

        if response.status_code == 200:
            data = response.json()
            timezone_value = data.get("value")

            if timezone_value and isinstance(timezone_value, str):
                logger.info(
                    f"User timezone fetched: {timezone_value}",
                    **log_context
                )
                return timezone_value
            else:
                logger.warning(
                    f"Unexpected timezone response shape: {data}. Falling back to UTC.",
                    **log_context
                )
                return "UTC"

        elif response.status_code == 401:
            logger.warning(
                f"Invalid access token (401) fetching timezone. Falling back to UTC.",
                **log_context
            )
            return "UTC"

        elif response.status_code == 403:
            logger.warning(
                f"Insufficient scopes (403) fetching timezone. Falling back to UTC.",
                **log_context
            )
            return "UTC"

        else:
            logger.warning(
                f"HTTP {response.status_code} fetching timezone. Falling back to UTC.",
                **log_context
            )
            return "UTC"

    except httpx.TimeoutException:
        logger.warning(
            "Timeout fetching user timezone. Falling back to UTC.",
            **log_context
        )
        return "UTC"

    except httpx.NetworkError as e:
        logger.warning(
            f"Network error fetching timezone: {type(e).__name__}. Falling back to UTC.",
            **log_context
        )
        return "UTC"

    except Exception as e:
        logger.error(
            f"Unexpected error fetching timezone: {e}. Falling back to UTC.",
            **log_context
        )
        return "UTC"
