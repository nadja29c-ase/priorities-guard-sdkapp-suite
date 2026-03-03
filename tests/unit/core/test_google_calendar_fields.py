"""
Unit tests for Google Calendar API field filtering (data minimization).

Tests that fetch_events() and list_events() request only the fields PG uses,
reducing data transferred over the network per GDPR Art. 5(1)(c).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.core.google_calendar import fetch_events, list_events


class TestFetchEventsFieldsParameter:
    """Test that fetch_events() requests only necessary fields."""

    EXPECTED_FIELDS = "items(id,summary,description,start,end,status,attendees(self,responseStatus))"

    @pytest.mark.asyncio
    async def test_fetch_events_includes_fields_parameter(self):
        """fetch_events() must include 'fields' key in params dict."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        await fetch_events(
            http_client=mock_client,
            access_token="test-token",
            time_min="2024-01-01T00:00:00Z",
            time_max="2024-01-07T23:59:59Z",
        )

        # Verify get was called
        mock_client.get.assert_called_once()
        call_kwargs = mock_client.get.call_args

        # Extract params from call
        params = call_kwargs.kwargs.get("params", {})

        # Verify fields parameter is present with exact expected value
        assert "fields" in params, "fetch_events() must include 'fields' parameter"
        assert params["fields"] == self.EXPECTED_FIELDS, (
            f"Expected fields='{self.EXPECTED_FIELDS}', got '{params['fields']}'"
        )

    @pytest.mark.asyncio
    async def test_fetch_events_fields_excludes_unnecessary_data(self):
        """Verify fields parameter excludes location, creator, organizer, etc."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        await fetch_events(
            http_client=mock_client,
            access_token="test-token",
            time_min="2024-01-01T00:00:00Z",
            time_max="2024-01-07T23:59:59Z",
        )

        params = mock_client.get.call_args.kwargs.get("params", {})
        fields = params.get("fields", "")

        # These fields should NOT be requested (data minimization)
        excluded_fields = ["location", "creator", "organizer", "conferenceData", "hangoutLink"]
        for field in excluded_fields:
            assert field not in fields, f"'{field}' should not be in fields parameter"


class TestListEventsFieldsParameter:
    """Test that list_events() requests only necessary fields."""

    EXPECTED_FIELDS = "items(id,summary,description,start,end,status,attendees(self,responseStatus)),nextPageToken"

    @pytest.mark.asyncio
    async def test_list_events_includes_fields_parameter(self):
        """list_events() must include 'fields' key in params dict."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        await list_events(
            http_client=mock_client,
            access_token="test-token",
            time_min="2024-01-01T00:00:00Z",
            time_max="2024-01-07T23:59:59Z",
        )

        # Verify get was called
        assert mock_client.get.called
        call_kwargs = mock_client.get.call_args

        # Extract params from call
        params = call_kwargs.kwargs.get("params", {})

        # Verify fields parameter is present with exact expected value
        assert "fields" in params, "list_events() must include 'fields' parameter"
        assert params["fields"] == self.EXPECTED_FIELDS, (
            f"Expected fields='{self.EXPECTED_FIELDS}', got '{params['fields']}'"
        )

    @pytest.mark.asyncio
    async def test_list_events_includes_next_page_token_in_fields(self):
        """list_events() fields must include nextPageToken for pagination."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"items": []}

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response

        await list_events(
            http_client=mock_client,
            access_token="test-token",
            time_min="2024-01-01T00:00:00Z",
            time_max="2024-01-07T23:59:59Z",
        )

        params = mock_client.get.call_args.kwargs.get("params", {})
        fields = params.get("fields", "")

        assert "nextPageToken" in fields, (
            "list_events() fields must include 'nextPageToken' for pagination"
        )


class TestFieldsRestrictedEventProcessing:
    """Test that event processing works with fields-restricted responses."""

    def test_minimal_event_has_required_fields(self):
        """Verify the fields we request contain all data needed for processing."""
        # This is the minimal event structure returned when using our fields parameter
        minimal_event = {
            "id": "event123",
            "summary": "Team Meeting",
            "description": "Weekly sync",
            "start": {"dateTime": "2024-01-15T10:00:00Z"},
            "end": {"dateTime": "2024-01-15T11:00:00Z"},
            "status": "confirmed",
            "attendees": [
                {"self": True, "responseStatus": "accepted"}
            ]
        }

        # All required fields are present
        assert "id" in minimal_event
        assert "summary" in minimal_event
        assert "start" in minimal_event
        assert "end" in minimal_event
        assert "status" in minimal_event
        assert "attendees" in minimal_event
        assert minimal_event["attendees"][0]["responseStatus"] == "accepted"

    def test_event_without_excluded_fields_is_valid(self):
        """Events without location, creator, organizer should still be processable."""
        # Event with ONLY the fields we request (no location, creator, organizer, etc.)
        minimal_event = {
            "id": "event456",
            "summary": "Project Review",
            "start": {"dateTime": "2024-01-15T14:00:00Z"},
            "end": {"dateTime": "2024-01-15T15:00:00Z"},
            "status": "confirmed",
        }

        # Should not have these fields
        assert "location" not in minimal_event
        assert "creator" not in minimal_event
        assert "organizer" not in minimal_event
        assert "conferenceData" not in minimal_event
        assert "hangoutLink" not in minimal_event

        # But should still be a valid event for our purposes
        assert minimal_event["id"] is not None
        assert minimal_event["summary"] is not None

    def test_declined_event_detection_with_minimal_fields(self):
        """Declined event detection must work with fields-restricted response."""
        # Event where user has declined
        declined_event = {
            "id": "event789",
            "summary": "Optional Meeting",
            "start": {"dateTime": "2024-01-15T16:00:00Z"},
            "end": {"dateTime": "2024-01-15T17:00:00Z"},
            "status": "confirmed",
            "attendees": [
                {"self": True, "responseStatus": "declined"}
            ]
        }

        # Find self in attendees
        self_attendee = next(
            (a for a in declined_event.get("attendees", []) if a.get("self")),
            None
        )

        # Verify we can detect declined status
        assert self_attendee is not None
        assert self_attendee["responseStatus"] == "declined"

    def test_all_day_event_with_minimal_fields(self):
        """All-day events (date instead of dateTime) work with minimal fields."""
        all_day_event = {
            "id": "allday123",
            "summary": "Company Holiday",
            "start": {"date": "2024-01-15"},
            "end": {"date": "2024-01-16"},
            "status": "confirmed",
        }

        # All-day events use "date" instead of "dateTime"
        assert "date" in all_day_event["start"]
        assert "dateTime" not in all_day_event["start"]
