"""
Unit tests for Priority Guardian Pydantic validation models.

Tests the CreatePriorityRequest model in isolation — no DB, no HTTP.
Validates type-conditional required fields, field constraints, and edge cases.
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from pydantic import ValidationError

from backend.apps.priority_guardian.models.requests import CreatePriorityRequest


class TestCreatePriorityRequestDeadlineType:
    """Tests for deadline-type priority validation."""

    def test_valid_deadline_priority(self):
        """Deadline type with future deadline date is valid."""
        future_date = date.today() + timedelta(days=30)
        request = CreatePriorityRequest(
            name="Launch marketing site",
            type="deadline",
            deadline=future_date,
        )
        assert request.name == "Launch marketing site"
        assert request.type == "deadline"
        assert request.deadline == future_date

    def test_deadline_type_missing_deadline_rejected(self):
        """Deadline type without deadline field is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Launch marketing site",
                type="deadline",
                # Missing deadline
            )
        errors = exc_info.value.errors()
        assert any("deadline is required" in str(e["msg"]).lower() for e in errors)

    def test_deadline_in_past_rejected(self):
        """Deadline date in the past is rejected."""
        past_date = date.today() - timedelta(days=1)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Launch marketing site",
                type="deadline",
                deadline=past_date,
            )
        errors = exc_info.value.errors()
        assert any("future" in str(e["msg"]).lower() for e in errors)

    def test_deadline_today_rejected(self):
        """Deadline date equal to today is rejected (must be future)."""
        today = date.today()
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Launch marketing site",
                type="deadline",
                deadline=today,
            )
        errors = exc_info.value.errors()
        assert any("future" in str(e["msg"]).lower() for e in errors)


class TestCreatePriorityRequestFlexibleType:
    """Tests for flexible-type priority validation."""

    def test_valid_flexible_priority(self):
        """Flexible type with all required fields is valid."""
        future_date = date.today() + timedelta(days=30)
        request = CreatePriorityRequest(
            name="Client outreach",
            type="flexible",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=future_date,
            desired_result="3 new client meetings scheduled",
        )
        assert request.name == "Client outreach"
        assert request.type == "flexible"
        assert request.weekly_hour_target == Decimal("10.0")
        assert request.checkpoint_date == future_date
        assert request.desired_result == "3 new client meetings scheduled"

    def test_flexible_missing_weekly_hour_target_rejected(self):
        """Flexible type missing weekly_hour_target is rejected."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Client outreach",
                type="flexible",
                # Missing weekly_hour_target
                checkpoint_date=future_date,
                desired_result="3 new client meetings",
            )
        errors = exc_info.value.errors()
        assert any("weekly_hour_target is required" in str(e["msg"]).lower() for e in errors)

    def test_flexible_missing_checkpoint_date_rejected(self):
        """Flexible type missing checkpoint_date is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Client outreach",
                type="flexible",
                weekly_hour_target=Decimal("10.0"),
                # Missing checkpoint_date
                desired_result="3 new client meetings",
            )
        errors = exc_info.value.errors()
        assert any("checkpoint_date is required" in str(e["msg"]).lower() for e in errors)

    def test_flexible_missing_desired_result_rejected(self):
        """Flexible type missing desired_result is rejected."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Client outreach",
                type="flexible",
                weekly_hour_target=Decimal("10.0"),
                checkpoint_date=future_date,
                # Missing desired_result
            )
        errors = exc_info.value.errors()
        assert any("desired_result is required" in str(e["msg"]).lower() for e in errors)

    def test_checkpoint_date_in_past_rejected(self):
        """Checkpoint date in the past is rejected."""
        past_date = date.today() - timedelta(days=1)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Client outreach",
                type="flexible",
                weekly_hour_target=Decimal("10.0"),
                checkpoint_date=past_date,
                desired_result="3 new client meetings",
            )
        errors = exc_info.value.errors()
        assert any("future" in str(e["msg"]).lower() for e in errors)


class TestFieldValidation:
    """Tests for individual field constraints."""

    def test_weekly_hour_target_zero_rejected(self):
        """weekly_hour_target = 0 is rejected."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Client outreach",
                type="flexible",
                weekly_hour_target=Decimal("0"),
                checkpoint_date=future_date,
                desired_result="3 new client meetings",
            )
        errors = exc_info.value.errors()
        # The gt=0 constraint should trigger
        assert len(errors) > 0

    def test_weekly_hour_target_negative_rejected(self):
        """weekly_hour_target < 0 is rejected."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Client outreach",
                type="flexible",
                weekly_hour_target=Decimal("-5.0"),
                checkpoint_date=future_date,
                desired_result="3 new client meetings",
            )
        errors = exc_info.value.errors()
        assert len(errors) > 0

    def test_name_empty_string_rejected(self):
        """Empty name is rejected."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="",
                type="deadline",
                deadline=future_date,
            )
        errors = exc_info.value.errors()
        assert len(errors) > 0

    def test_name_whitespace_only_rejected(self):
        """Whitespace-only name is rejected."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="   ",
                type="deadline",
                deadline=future_date,
            )
        errors = exc_info.value.errors()
        assert any("empty" in str(e["msg"]).lower() for e in errors)

    def test_name_exceeds_100_chars_rejected(self):
        """Name exceeding 100 chars is rejected."""
        future_date = date.today() + timedelta(days=30)
        long_name = "x" * 101
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name=long_name,
                type="deadline",
                deadline=future_date,
            )
        errors = exc_info.value.errors()
        assert len(errors) > 0

    def test_name_exactly_100_chars_valid(self):
        """Name exactly 100 chars is valid."""
        future_date = date.today() + timedelta(days=30)
        name_100 = "x" * 100
        request = CreatePriorityRequest(
            name=name_100,
            type="deadline",
            deadline=future_date,
        )
        assert len(request.name) == 100

    def test_desired_result_exceeds_200_chars_rejected(self):
        """desired_result exceeding 200 chars is rejected."""
        future_date = date.today() + timedelta(days=30)
        long_result = "x" * 201
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Client outreach",
                type="flexible",
                weekly_hour_target=Decimal("10.0"),
                checkpoint_date=future_date,
                desired_result=long_result,
            )
        errors = exc_info.value.errors()
        assert len(errors) > 0

    def test_desired_result_exactly_200_chars_valid(self):
        """desired_result exactly 200 chars is valid."""
        future_date = date.today() + timedelta(days=30)
        result_200 = "x" * 200
        request = CreatePriorityRequest(
            name="Client outreach",
            type="flexible",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=future_date,
            desired_result=result_200,
        )
        assert len(request.desired_result) == 200

    def test_desired_result_whitespace_only_rejected(self):
        """Whitespace-only desired_result is rejected."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Client outreach",
                type="flexible",
                weekly_hour_target=Decimal("10.0"),
                checkpoint_date=future_date,
                desired_result="   ",
            )
        errors = exc_info.value.errors()
        assert any("empty" in str(e["msg"]).lower() for e in errors)


class TestEnumValidation:
    """Tests for enum/type validation."""

    def test_invalid_type_rejected(self):
        """Type not in ['deadline', 'flexible'] is rejected."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Some priority",
                type="invalid_type",
                deadline=future_date,
            )
        errors = exc_info.value.errors()
        assert len(errors) > 0

    def test_type_case_sensitive(self):
        """Type must match exact case (lowercase)."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError):
            CreatePriorityRequest(
                name="Some priority",
                type="Deadline",  # Wrong case
                deadline=future_date,
            )


class TestNameStripping:
    """Tests for name whitespace handling."""

    def test_name_strips_leading_trailing_whitespace(self):
        """Name strips leading/trailing whitespace."""
        future_date = date.today() + timedelta(days=30)
        request = CreatePriorityRequest(
            name="  Launch marketing site  ",
            type="deadline",
            deadline=future_date,
        )
        assert request.name == "Launch marketing site"

    def test_desired_result_strips_whitespace(self):
        """desired_result strips leading/trailing whitespace."""
        future_date = date.today() + timedelta(days=30)
        request = CreatePriorityRequest(
            name="Client outreach",
            type="flexible",
            weekly_hour_target=Decimal("10.0"),
            checkpoint_date=future_date,
            desired_result="  3 new meetings  ",
        )
        assert request.desired_result == "3 new meetings"


class TestCrossTypeFieldRejection:
    """
    Tests for cross-type field rejection.

    The validator rejects fields that belong to the "other" type:
    - Flexible priorities reject `deadline`
    - Deadline priorities reject `weekly_hour_target`, `checkpoint_date`, `desired_result`

    This prevents data inconsistency and ensures LLMs provide the correct fields.
    """

    def test_flexible_with_deadline_field_rejected(self):
        """Flexible priority with deadline field raises ValidationError."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Client outreach",
                type="flexible",
                weekly_hour_target=Decimal("10.0"),
                checkpoint_date=future_date,
                desired_result="3 new client meetings",
                deadline=future_date,  # Cross-type field - rejected
            )
        assert "deadline is not valid for flexible priorities" in str(exc_info.value)

    def test_deadline_with_weekly_hour_target_rejected(self):
        """Deadline priority with weekly_hour_target raises ValidationError."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Launch marketing site",
                type="deadline",
                deadline=future_date,
                weekly_hour_target=Decimal("5.0"),  # Cross-type field - rejected
            )
        assert "weekly_hour_target is not valid for deadline priorities" in str(exc_info.value)

    def test_deadline_with_checkpoint_date_rejected(self):
        """Deadline priority with checkpoint_date raises ValidationError."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Launch marketing site",
                type="deadline",
                deadline=future_date,
                checkpoint_date=future_date,  # Cross-type field - rejected
            )
        assert "checkpoint_date is not valid for deadline priorities" in str(exc_info.value)

    def test_deadline_with_desired_result_rejected(self):
        """Deadline priority with desired_result raises ValidationError."""
        future_date = date.today() + timedelta(days=30)
        with pytest.raises(ValidationError) as exc_info:
            CreatePriorityRequest(
                name="Launch marketing site",
                type="deadline",
                deadline=future_date,
                desired_result="Site live",  # Cross-type field - rejected
            )
        assert "desired_result is not valid for deadline priorities" in str(exc_info.value)
