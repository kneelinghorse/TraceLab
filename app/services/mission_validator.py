"""Mission validation service for comprehensive payload and business rule validation.

Implements B16.3 validation requirements:
- mission_id format validation (alphanumeric with dots/dashes)
- title length (3-255 characters)
- objective minimum length (10 characters)
- success_criteria non-empty array with non-empty string items
- Uniqueness checks
- Clear, actionable error messages
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.mission import MISSION_STATUSES, Mission
from app.schemas.mission import MISSION_ID_PATTERN


@dataclass
class ValidationError:
    """Represents a single validation error."""

    field: str
    message: str
    code: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of validation containing errors if any."""

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to API response format."""
        return {
            "valid": self.is_valid,
            "errors": [
                {
                    "field": e.field,
                    "message": e.message,
                    "code": e.code,
                    "context": e.context,
                }
                for e in self.errors
            ],
        }

    def to_422_response(self) -> dict[str, Any]:
        """Convert to FastAPI 422 error response format."""
        return {
            "detail": [
                {
                    "loc": ["body"] + e.field.split(".") if e.field else ["body"],
                    "msg": e.message,
                    "type": e.code,
                }
                for e in self.errors
            ]
        }


class MissionValidator:
    """Comprehensive validator for mission payloads and business rules.

    Provides layered validation:
    1. Format validation (patterns, lengths)
    2. Content validation (non-empty, type checks)
    3. Business rule validation (uniqueness, status transitions)
    """

    # Validation constants
    MISSION_ID_MAX_LENGTH = 50
    TITLE_MIN_LENGTH = 3
    TITLE_MAX_LENGTH = 255
    OBJECTIVE_MIN_LENGTH = 10

    def validate_mission_id(self, mission_id: str) -> list[ValidationError]:
        """Validate mission_id format.

        Rules:
        - Required (non-empty)
        - Max length 50
        - Pattern: starts with alphanumeric, can contain letters, numbers, dots, dashes, underscores
        """
        errors: list[ValidationError] = []

        if not mission_id:
            errors.append(
                ValidationError(
                    field="mission_id",
                    message="mission_id is required",
                    code="value_error.missing",
                )
            )
            return errors

        if len(mission_id) > self.MISSION_ID_MAX_LENGTH:
            errors.append(
                ValidationError(
                    field="mission_id",
                    message=f"mission_id must not exceed {self.MISSION_ID_MAX_LENGTH} characters",
                    code="value_error.any_str.max_length",
                    context={"limit_value": self.MISSION_ID_MAX_LENGTH},
                )
            )

        if not MISSION_ID_PATTERN.match(mission_id):
            errors.append(
                ValidationError(
                    field="mission_id",
                    message="mission_id must start with alphanumeric and contain only letters, numbers, dots, dashes, or underscores",
                    code="value_error.str.regex",
                    context={"pattern": MISSION_ID_PATTERN.pattern},
                )
            )

        return errors

    def validate_title(self, title: str) -> list[ValidationError]:
        """Validate title field.

        Rules:
        - Required (non-empty)
        - Min length 3
        - Max length 255
        """
        errors: list[ValidationError] = []

        if not title:
            errors.append(
                ValidationError(
                    field="title",
                    message="title is required",
                    code="value_error.missing",
                )
            )
            return errors

        if len(title) < self.TITLE_MIN_LENGTH:
            errors.append(
                ValidationError(
                    field="title",
                    message=f"title must be at least {self.TITLE_MIN_LENGTH} characters",
                    code="value_error.any_str.min_length",
                    context={"limit_value": self.TITLE_MIN_LENGTH},
                )
            )

        if len(title) > self.TITLE_MAX_LENGTH:
            errors.append(
                ValidationError(
                    field="title",
                    message=f"title must not exceed {self.TITLE_MAX_LENGTH} characters",
                    code="value_error.any_str.max_length",
                    context={"limit_value": self.TITLE_MAX_LENGTH},
                )
            )

        return errors

    def validate_objective(self, objective: str) -> list[ValidationError]:
        """Validate objective field.

        Rules:
        - Required (non-empty)
        - Min length 10
        """
        errors: list[ValidationError] = []

        if not objective:
            errors.append(
                ValidationError(
                    field="objective",
                    message="objective is required",
                    code="value_error.missing",
                )
            )
            return errors

        if len(objective) < self.OBJECTIVE_MIN_LENGTH:
            errors.append(
                ValidationError(
                    field="objective",
                    message=f"objective must be at least {self.OBJECTIVE_MIN_LENGTH} characters",
                    code="value_error.any_str.min_length",
                    context={"limit_value": self.OBJECTIVE_MIN_LENGTH},
                )
            )

        return errors

    def validate_success_criteria(
        self, success_criteria: list[Any] | None
    ) -> list[ValidationError]:
        """Validate success_criteria field.

        Rules:
        - Required (non-empty array)
        - Each item must be a non-empty string
        """
        errors: list[ValidationError] = []

        if success_criteria is None:
            errors.append(
                ValidationError(
                    field="success_criteria",
                    message="success_criteria is required",
                    code="value_error.missing",
                )
            )
            return errors

        if not isinstance(success_criteria, list):
            errors.append(
                ValidationError(
                    field="success_criteria",
                    message="success_criteria must be an array",
                    code="type_error.list",
                )
            )
            return errors

        if len(success_criteria) == 0:
            errors.append(
                ValidationError(
                    field="success_criteria",
                    message="success_criteria must contain at least one item",
                    code="value_error.list.min_items",
                    context={"limit_value": 1},
                )
            )
            return errors

        for i, item in enumerate(success_criteria):
            if not isinstance(item, str):
                errors.append(
                    ValidationError(
                        field=f"success_criteria.{i}",
                        message=f"success_criteria[{i}] must be a string",
                        code="type_error.str",
                    )
                )
            elif not item.strip():
                errors.append(
                    ValidationError(
                        field=f"success_criteria.{i}",
                        message=f"success_criteria[{i}] cannot be empty or whitespace",
                        code="value_error.any_str.min_length",
                    )
                )

        return errors

    def validate_status(self, status: str) -> list[ValidationError]:
        """Validate status field against allowed values."""
        errors: list[ValidationError] = []

        if status not in MISSION_STATUSES:
            errors.append(
                ValidationError(
                    field="status",
                    message=f"Invalid status '{status}'. Must be one of: {', '.join(sorted(MISSION_STATUSES))}",
                    code="value_error.not_in_enum",
                    context={"allowed_values": list(MISSION_STATUSES)},
                )
            )

        return errors

    def validate_uniqueness(
        self, db: Session, mission_id: str, exclude_id: str | None = None
    ) -> list[ValidationError]:
        """Check that mission_id is unique in the database.

        Args:
            db: Database session
            mission_id: The mission_id to check
            exclude_id: UUID to exclude (for updates)
        """
        errors: list[ValidationError] = []

        query = db.query(Mission).filter(Mission.mission_id == mission_id)
        if exclude_id:
            query = query.filter(Mission.id != exclude_id)

        if query.first() is not None:
            errors.append(
                ValidationError(
                    field="mission_id",
                    message=f"Mission with mission_id '{mission_id}' already exists",
                    code="value_error.unique",
                    context={"existing_value": mission_id},
                )
            )

        return errors

    def validate_create_payload(
        self, payload: dict[str, Any], db: Session | None = None
    ) -> ValidationResult:
        """Validate a complete mission creation payload.

        Args:
            payload: Dictionary with mission fields
            db: Optional database session for uniqueness checks

        Returns:
            ValidationResult with all errors found
        """
        errors: list[ValidationError] = []

        # Required field validations
        errors.extend(self.validate_mission_id(payload.get("mission_id", "")))
        errors.extend(self.validate_title(payload.get("title", "")))
        errors.extend(self.validate_objective(payload.get("objective", "")))
        errors.extend(self.validate_success_criteria(payload.get("success_criteria")))

        # Optional field validations
        if "status" in payload and payload["status"]:
            errors.extend(self.validate_status(payload["status"]))

        # Uniqueness check
        if (
            db
            and payload.get("mission_id")
            and not any(e.field == "mission_id" for e in errors)
        ):
            errors.extend(self.validate_uniqueness(db, payload["mission_id"]))

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    def validate_update_payload(
        self,
        payload: dict[str, Any],
        db: Session | None = None,
        exclude_id: str | None = None,
    ) -> ValidationResult:
        """Validate a mission update payload.

        Only validates fields that are present in the payload.

        Args:
            payload: Dictionary with fields to update
            db: Optional database session for uniqueness checks
            exclude_id: UUID of mission being updated (for uniqueness check)

        Returns:
            ValidationResult with all errors found
        """
        errors: list[ValidationError] = []

        # Only validate fields that are present
        if "mission_id" in payload:
            errors.extend(self.validate_mission_id(payload["mission_id"]))
            if db and not any(e.field == "mission_id" for e in errors):
                errors.extend(
                    self.validate_uniqueness(db, payload["mission_id"], exclude_id)
                )

        if "title" in payload:
            errors.extend(self.validate_title(payload["title"]))

        if "objective" in payload:
            errors.extend(self.validate_objective(payload["objective"]))

        if "success_criteria" in payload:
            errors.extend(self.validate_success_criteria(payload["success_criteria"]))

        if "status" in payload:
            errors.extend(self.validate_status(payload["status"]))

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)


# Singleton instance for convenience
mission_validator = MissionValidator()
