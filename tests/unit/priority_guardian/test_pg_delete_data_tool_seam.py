"""
End-to-end seam tests for the deletion MCP tool: tool -> backend_post -> HTTP status.

WHY THIS FILE EXISTS.

Everything else tests one layer. The integration tests call delete_user_data directly; the
unit tests mock the session; the router's behaviour is asserted in isolation. Nothing crossed
the boundary where the MCP tool meets http_client's status-code handling — and that is
exactly where a real bug lived:

    backend_post returns the parsed body for 4xx, but RAISES for 5xx.

The route signals "rolled back, retryable" with 503. 503 is 5xx. So the tool's entire
retryable branch was unreachable: the exception escaped to the dispatcher's generic handler
and the user saw "Something went wrong. Please try again." — in precisely the scenario the
atomicity design exists for, with no indication their Calendar connection was already gone.

These tests patch the HTTP client, not backend_post, so backend_post's real status-code logic
executes. Patching backend_post would re-create the blind spot this file exists to close.
"""

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from mcp_server.priority_guardian.tools.delete_my_priority_guardian_data import handle

USER_ID = "11111111-2222-3333-4444-555555555555"
CORRELATION_ID = "seam-test"
HTTP_CLIENT = "mcp_server.priority_guardian.http_client.http_client"


def _response(status: int, payload: dict) -> httpx.Response:
    """A real httpx.Response, so raise_for_status behaves exactly as in production."""
    return httpx.Response(
        status_code=status,
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        request=httpx.Request("POST", "http://backend/api/priority-guardian/delete-data"),
    )


def _client_returning(response: httpx.Response):
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)
    return patch(HTTP_CLIENT, client)


@pytest.mark.asyncio
async def test_503_retryable_reaches_the_user_as_a_retryable_message():
    """
    Bug this catches: THE ONE THIS FILE WAS WRITTEN FOR. backend_post raises on 5xx, so
    without explicit handling in the tool the 503 retryable path is dead code and the user
    gets the dispatcher's generic "Something went wrong."

    Fails if the tool stops catching httpx.HTTPStatusError, or if the route's status changes
    to something the tool does not recognise.
    """
    with _client_returning(_response(503, {
        "detail": {
            "error": "deletion_failed",
            "message": "Local deletion failed and was rolled back.",
            "retryable": True,
            "google_revocation_confirmed": True,
        }
    })):
        result = await handle(USER_ID, CORRELATION_ID, {})

    assert result.isError is True
    text = result.content[0].text

    assert "not deleted" in text.lower()
    assert "try again" in text.lower()
    assert "Something went wrong" not in text, (
        "the dispatcher's generic error reached the user — the retryable branch is unreachable"
    )

    # The whole point of separating the two outcomes: Calendar access is already gone.
    assert "google calendar" in text.lower()
    assert result.structuredContent["retryable"] is True
    assert result.structuredContent["calendar_access_revoked"] is True


@pytest.mark.asyncio
async def test_503_without_calendar_revoked_omits_the_calendar_sentence():
    """
    Bug this catches: hardcoding the Calendar sentence regardless of outcome. If revocation
    never happened, telling the user their Calendar was disconnected is false — and this is a
    message people act on.
    """
    with _client_returning(_response(503, {
        "detail": {
            "error": "deletion_failed",
            "message": "rolled back",
            "retryable": True,
            "google_revocation_confirmed": False,
        }
    })):
        result = await handle(USER_ID, CORRELATION_ID, {})

    text = result.content[0].text
    assert "not deleted" in text.lower()
    assert "google calendar" not in text.lower(), "claimed a disconnection that did not happen"
    assert result.structuredContent["calendar_access_revoked"] is False


@pytest.mark.asyncio
async def test_a_genuine_500_still_raises():
    """
    Bug this catches: OVER-catching. The handler must recognise the structured 503 and let
    everything else through — a real backend crash should still surface as an error rather
    than being reported to the user as an orderly retryable outcome.
    """
    with _client_returning(_response(500, {"detail": "Internal server error"})):
        with pytest.raises(httpx.HTTPStatusError):
            await handle(USER_ID, CORRELATION_ID, {})


@pytest.mark.asyncio
async def test_503_without_a_retryable_detail_still_raises():
    """
    Bug this catches: treating ANY 503 as the orderly rolled-back case. A 503 from a proxy or
    a cold start carries no retryable detail, and reporting it as "nothing was deleted, safe
    to retry" would be an assertion the backend never made.
    """
    with _client_returning(_response(503, {"detail": "upstream unavailable"})):
        with pytest.raises(httpx.HTTPStatusError):
            await handle(USER_ID, CORRELATION_ID, {})


@pytest.mark.asyncio
async def test_success_path_returns_categories_not_schema():
    """
    Bug this catches: leaking schema into the user-facing text (§5). Row counts, table names
    and the audit id belong in structuredContent and the audit entry, never in what the user
    reads.
    """
    with _client_returning(_response(200, {
        "success": True,
        "google_revocation_confirmed": True,
        "tables_affected": 5,
        "rows_deleted": {"pg_priorities": 3, "pg_weekly_snapshots": 120},
        "audit_log_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    })):
        result = await handle(USER_ID, CORRELATION_ID, {})

    text = result.content[0].text
    assert result.isError is not True
    assert "priorities" in text.lower()
    assert "mindsort" in text.lower(), "must state other apps are unaffected"

    for leak in ("pg_priorities", "pg_weekly_snapshots", "120", "aaaaaaaa"):
        assert leak not in text, f"schema leaked into user-facing text: {leak!r}"
