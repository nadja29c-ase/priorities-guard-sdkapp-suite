"""
Priority Guardian request models.

All input validation lives in one place. The router orchestrates only:
parse request → validate via Pydantic → transactional DB logic → return response.

This keeps validation testable in isolation and reusable when Inc 03+ adds update/edit endpoints.
"""

from datetime import date
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class CreatePriorityRequest(BaseModel):
    """
    Request model for creating a priority.

    Two priority types exist:
    - deadline: has a hard end date. Requires `deadline` field.
    - flexible: ongoing time investment toward a 1-month goal.
      Requires `weekly_hour_target`, `checkpoint_date`, and `desired_result`.

    The `calendar_keyword` is NOT in the request - the backend assigns it deterministically.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Priority name exactly as stated by user. Max 100 chars.",
    )

    type: Literal["deadline", "flexible"] = Field(
        ...,
        description="Priority type: deadline (hard end date) or flexible (ongoing time investment)",
    )

    # Deadline-type fields
    deadline: Optional[date] = Field(
        default=None,
        description="Hard end date. Required when type=deadline. Must be in the future.",
    )

    # Flexible-type fields
    weekly_hour_target: Optional[Decimal] = Field(
        default=None,
        gt=0,
        description="Hours per week target. Required when type=flexible. Must be > 0.",
    )

    checkpoint_date: Optional[date] = Field(
        default=None,
        description="Evaluation checkpoint ~1 month out. Required when type=flexible.",
    )

    desired_result: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Concrete outcome in ~1 month. Required when type=flexible. Max 200 chars.",
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        """Validate name is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("name cannot be empty or whitespace-only")
        return v.strip()

    @field_validator("desired_result")
    @classmethod
    def validate_desired_result_not_empty(cls, v: Optional[str]) -> Optional[str]:
        """Validate desired_result is not empty if provided."""
        if v is not None and not v.strip():
            raise ValueError("desired_result cannot be empty or whitespace-only")
        return v.strip() if v else v

    @model_validator(mode="after")
    def validate_type_conditional_fields(self) -> "CreatePriorityRequest":
        """
        Validate type-conditional required fields and reject cross-type fields.

        - deadline type: requires `deadline` field, must be future date
          REJECTS: weekly_hour_target, checkpoint_date, desired_result
        - flexible type: requires `weekly_hour_target`, `checkpoint_date`, `desired_result`
          REJECTS: deadline
        """
        from datetime import date as date_type

        today = date_type.today()

        if self.type == "deadline":
            # Deadline type requires deadline field
            if self.deadline is None:
                raise ValueError("deadline is required when type is 'deadline'")

            # Deadline must be in the future
            if self.deadline <= today:
                raise ValueError("deadline must be in the future")

            # Reject flexible-only fields on deadline priorities
            if self.weekly_hour_target is not None:
                raise ValueError("weekly_hour_target is not valid for deadline priorities")
            if self.checkpoint_date is not None:
                raise ValueError("checkpoint_date is not valid for deadline priorities")
            if self.desired_result is not None:
                raise ValueError("desired_result is not valid for deadline priorities")

        elif self.type == "flexible":
            # Flexible type requires all three fields
            if self.weekly_hour_target is None:
                raise ValueError("weekly_hour_target is required when type is 'flexible'")

            if self.checkpoint_date is None:
                raise ValueError("checkpoint_date is required when type is 'flexible'")

            if self.desired_result is None:
                raise ValueError("desired_result is required when type is 'flexible'")

            # Checkpoint date must be in the future
            if self.checkpoint_date <= today:
                raise ValueError("checkpoint_date must be in the future")

            # Reject deadline-only fields on flexible priorities
            if self.deadline is not None:
                raise ValueError("deadline is not valid for flexible priorities")

        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Launch marketing site",
                    "type": "deadline",
                    "deadline": "2026-03-15",
                },
                {
                    "name": "Client outreach",
                    "type": "flexible",
                    "weekly_hour_target": 10.0,
                    "checkpoint_date": "2026-03-08",
                    "desired_result": "3 new client meetings scheduled",
                },
            ]
        }
    }


class UpdatePriorityRequest(BaseModel):
    """
    Request model for updating a priority.

    All fields are optional (partial update). Only provided fields are updated.
    Type and calendar_keyword are immutable after creation.

    For deadline priorities: name, deadline
    For flexible priorities: name, weekly_hour_target, checkpoint_date, desired_result
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Priority name. Max 100 chars.",
    )

    deadline: Optional[date] = Field(
        default=None,
        description="Hard end date. Only valid for deadline-type priorities.",
    )

    weekly_hour_target: Optional[Decimal] = Field(
        default=None,
        gt=0,
        description="Hours per week target. Only valid for flexible-type priorities.",
    )

    checkpoint_date: Optional[date] = Field(
        default=None,
        description="Evaluation checkpoint. Only valid for flexible-type priorities.",
    )

    desired_result: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Concrete outcome. Only valid for flexible-type priorities.",
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        """Validate name is not empty or whitespace-only if provided."""
        if v is not None and not v.strip():
            raise ValueError("name cannot be empty or whitespace-only")
        return v.strip() if v else v

    @field_validator("desired_result")
    @classmethod
    def validate_desired_result_not_empty(cls, v: Optional[str]) -> Optional[str]:
        """Validate desired_result is not empty if provided."""
        if v is not None and not v.strip():
            raise ValueError("desired_result cannot be empty or whitespace-only")
        return v.strip() if v else v

    @field_validator("deadline", "checkpoint_date")
    @classmethod
    def validate_date_in_future(cls, v: Optional[date]) -> Optional[date]:
        """Validate dates are in the future if provided."""
        if v is not None:
            from datetime import date as date_type
            if v <= date_type.today():
                raise ValueError("date must be in the future")
        return v

    def has_updates(self) -> bool:
        """Check if any fields are provided for update."""
        return any([
            self.name is not None,
            self.deadline is not None,
            self.weekly_hour_target is not None,
            self.checkpoint_date is not None,
            self.desired_result is not None,
        ])


class CreateDeliverableRequest(BaseModel):
    """
    Request model for creating a deliverable.

    Deliverables are associated with a parent priority.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Deliverable name. Max 200 chars.",
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: str) -> str:
        """Validate name is not empty or whitespace-only."""
        if not v or not v.strip():
            raise ValueError("name cannot be empty or whitespace-only")
        return v.strip()


class UpdateDeliverableRequest(BaseModel):
    """
    Request model for updating a deliverable.

    All fields are optional (partial update). Only provided fields are updated.
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Deliverable name. Max 200 chars.",
    )

    done: Optional[bool] = Field(
        default=None,
        description="Whether the deliverable is completed.",
    )

    @field_validator("name")
    @classmethod
    def validate_name_not_empty(cls, v: Optional[str]) -> Optional[str]:
        """Validate name is not empty or whitespace-only if provided."""
        if v is not None and not v.strip():
            raise ValueError("name cannot be empty or whitespace-only")
        return v.strip() if v else v

    def has_updates(self) -> bool:
        """Check if any fields are provided for update."""
        return self.name is not None or self.done is not None
