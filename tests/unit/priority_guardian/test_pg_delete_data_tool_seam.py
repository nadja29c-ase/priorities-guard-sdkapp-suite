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

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

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


EXPECTED_PATH = "/api/priority-guardian/delete-data"


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


@pytest.mark.asyncio
async def test_nothing_to_delete_does_not_read_as_a_fresh_deletion():
    """
    Bug this catches: emitting the same "has been deleted" text when the backend deleted
    ZERO rows. The backend is idempotent by design — a second call succeeds reporting zero —
    so a host retry, or a user who already deleted, would be told their data was just
    removed when nothing happened. Not false, but it reads as a fresh deletion.

    Found by adversarial review; the tool previously ignored tables_affected entirely.
    """
    with _client_returning(_response(200, {
        "success": True,
        "google_revocation_confirmed": False,
        "tables_affected": 0,
        "rows_deleted": {"pg_priorities": 0},
        "audit_log_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    })):
        result = await handle(USER_ID, CORRELATION_ID, {})

    text = result.content[0].text
    assert result.isError is not True
    assert "has been deleted" not in text, (
        "reported a deletion that did not happen"
    )
    assert "no priority guardian data to delete" in text.lower()
    assert result.structuredContent["nothing_to_delete"] is True


@pytest.mark.asyncio
async def test_real_deletion_still_reports_a_deletion():
    """
    Bug this catches: the inverse — an over-eager nothing-to-delete branch that fires when
    rows WERE removed, telling a user nothing happened while their data is gone. That is the
    worse direction of the same mistake.
    """
    with _client_returning(_response(200, {
        "success": True,
        "google_revocation_confirmed": True,
        "tables_affected": 4,
        "rows_deleted": {"pg_priorities": 2},
    })):
        result = await handle(USER_ID, CORRELATION_ID, {})

    text = result.content[0].text
    assert "has been deleted" in text
    assert result.structuredContent["nothing_to_delete"] is False


@pytest.mark.asyncio
async def test_posts_to_the_delete_data_endpoint():
    """
    Bug this catches: the tool posting to the WRONG route. The mocked client returns its
    canned response regardless of path, so every other test in this file would pass if the
    endpoint were changed to anything at all — including a route that does something else
    entirely. Found by adversarial review.
    """
    client = AsyncMock()
    client.post = AsyncMock(return_value=_response(200, {
        "success": True, "google_revocation_confirmed": True, "tables_affected": 3,
    }))

    with patch(HTTP_CLIENT, client):
        await handle(USER_ID, CORRELATION_ID, {})

    client.post.assert_awaited_once()
    url = client.post.await_args.args[0]
    assert url.endswith(EXPECTED_PATH), f"posted to {url!r}, expected …{EXPECTED_PATH}"


@pytest.mark.asyncio
async def test_router_returns_the_status_the_tool_listens_for():
    """
    THE TWO HALVES OF THIS CONTRACT WERE TESTED INDEPENDENTLY AND NEVER TOGETHER.

    The tool recognises exactly one failure signal: HTTP 503 carrying detail.retryable. The
    seam tests above FABRICATE that response, so changing the router's PgDeletionError
    mapping from 503 to anything else would break the tool in production while every test
    stayed green — the tool's handler would stop matching and the user would fall back to the
    dispatcher's generic error. Precisely the bug this file was created for, one layer down.

    This pins the router's side of the contract to the constant the tool depends on.

    Bug this catches: changing the route's status code, or dropping `retryable` /
    `google_revocation_confirmed` from its detail payload.
    """
    from fastapi import HTTPException

    from backend.apps.priority_guardian.routers import offboarding_router as router_mod
    from backend.apps.priority_guardian.services.offboarding_service import PgDeletionError

    session = AsyncMock()
    session.get = AsyncMock(return_value=object())          # user exists
    request = MagicMock()
    request.app.state.http_client = AsyncMock()

    with patch.object(
        router_mod, "delete_user_data",
        AsyncMock(side_effect=PgDeletionError("rolled back", google_revoked=True)),
    ):
        with pytest.raises(HTTPException) as exc:
            await router_mod.delete_data(
                request=request,
                x_user_id=USER_ID,
                session=session,
            )

    assert exc.value.status_code == 503, (
        "the tool only recognises 503; changing this silently breaks the retryable path"
    )
    detail = exc.value.detail
    assert detail["retryable"] is True
    assert detail["google_revocation_confirmed"] is True


# =============================================================================
# TRUTHFULNESS OF USER-FACING TEXT
#
# Four statements were false in reachable states, two of them written the same day they
# were found. On a destructive, irreversible operation a message that misstates what
# happened is a defect even when the code is correct — the user acts on the message, not
# on the code.
# =============================================================================

@pytest.mark.asyncio
async def test_success_warns_when_google_revocation_was_not_confirmed():
    """
    Bug this catches: silence about an unconfirmed revocation. The tool DESCRIPTION promises
    "The Google Calendar connection (access is revoked at Google)". Local deletion proceeds
    even when Google could not be reached (§4 — erasure must not depend on a third party),
    so a success message that says nothing leaves the user believing access was revoked when
    it may not have been.
    """
    with _client_returning(_response(200, {
        "success": True,
        "google_revocation_confirmed": False,
        "tables_affected": 4,
    })):
        result = await handle(USER_ID, CORRELATION_ID, {})

    text = result.content[0].text.lower()
    assert "could not confirm" in text, "claimed revocation it did not get"
    assert "connected apps" in text, "no actionable remedy offered"


@pytest.mark.asyncio
async def test_success_stays_clean_when_revocation_was_confirmed():
    """
    Bug this catches: the inverse — warning about Google on every success, which would train
    users to ignore a warning that matters only sometimes.
    """
    with _client_returning(_response(200, {
        "success": True, "google_revocation_confirmed": True, "tables_affected": 4,
    })):
        result = await handle(USER_ID, CORRELATION_ID, {})

    assert "could not confirm" not in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_retryable_text_does_not_contradict_itself():
    """
    Bug this catches: the message saying "nothing was removed" and then, in the same breath,
    that the Google Calendar connection was disconnected. Both channels are checked — the
    user-facing text AND assistant_guidance, which the model relays. The guidance carried the
    false claim for a full round after the visible text was fixed.
    """
    with _client_returning(_response(503, {
        "detail": {"retryable": True, "google_revocation_confirmed": True},
    })):
        result = await handle(USER_ID, CORRELATION_ID, {})

    text = result.content[0].text.lower()
    guidance = result.structuredContent["assistant_guidance"].lower()

    assert "nothing was removed" not in text
    assert "nothing was removed" not in guidance, (
        "assistant_guidance still carries the contradiction to the model"
    )
    assert "google calendar" in text, "must still say Calendar access is gone"


@pytest.mark.asyncio
async def test_nothing_to_delete_does_not_claim_nothing_changed():
    """
    Bug this catches: "Nothing was changed" on the zero-row path. delete_user_data writes a
    CoreToolAuditLog entry on EVERY call, including one that deletes nothing — so the claim
    is false, and it is a claim about a compliance record.
    """
    with _client_returning(_response(200, {
        "success": True, "google_revocation_confirmed": True, "tables_affected": 0,
    })):
        result = await handle(USER_ID, CORRELATION_ID, {})

    assert "nothing was changed" not in result.content[0].text.lower()


@pytest.mark.asyncio
async def test_timeout_does_not_assert_an_outcome_it_cannot_know():
    """
    Bug this catches: THE SHARPEST OF THE FOUR. The timeout said "Your data has NOT been
    deleted" — but it bounds the MCP call, not the backend request. The backend keeps
    running and may commit after the tool stops waiting, so the tool told the user the
    opposite of what happened.

    Same class as the unbounded Google call fixed earlier, one layer out.
    """
    from mcp_server.priority_guardian.tools.base import ToolUsageError

    client = AsyncMock()

    async def _hang(*_a, **_kw):
        await asyncio.sleep(30)

    client.post = _hang

    with patch(HTTP_CLIENT, client), patch(
        "mcp_server.priority_guardian.tools.delete_my_priority_guardian_data.TIMEOUT_S", 0.05
    ):
        with pytest.raises(ToolUsageError) as exc:
            await handle(USER_ID, CORRELATION_ID, {})

    message = str(exc.value).lower()
    assert "has not been deleted" not in message, (
        "asserted an outcome the tool cannot know — the backend may have committed"
    )
    assert "do not know whether it completed" in message
    assert "check whether" in message, "no actionable instruction before retrying"
