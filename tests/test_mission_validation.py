"""Comprehensive tests for mission validation (B16.3).

Tests all validation rules:
- mission_id format (alphanumeric with dots/dashes)
- title length (3-255 characters)
- objective minimum length (10 characters)
- success_criteria non-empty array with non-empty string items
- status values
- uniqueness constraints
- Pydantic schema validation
- MissionValidator service
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.mission import MISSION_ID_PATTERN, MissionCreate, MissionUpdate
from app.services.mission_validator import MissionValidator

# ============================================================================
# mission_id Validation Tests
# ============================================================================


class TestMissionIdValidation:
    """Tests for mission_id format validation."""

    @pytest.mark.parametrize(
        "mission_id",
        [
            "B16.1",
            "B16.2-test",
            "SPRINT_01",
            "abc123",
            "A",
            "1",
            "Test-Mission_v2.0",
            "R2.1",
            "B16.3_Missions-Validation",
        ],
    )
    def test_valid_mission_ids(self, mission_id: str):
        """Valid mission_id formats should pass validation."""
        assert MISSION_ID_PATTERN.match(mission_id) is not None

        # Also test via schema
        data = MissionCreate(
            mission_id=mission_id,
            title="Test Mission",
            objective="This is a test objective with at least 10 chars",
            success_criteria=["Criterion 1"],
        )
        assert data.mission_id == mission_id

    @pytest.mark.parametrize(
        "mission_id,reason",
        [
            ("-invalid", "starts with dash"),
            (".invalid", "starts with dot"),
            ("_invalid", "starts with underscore"),
            ("has space", "contains space"),
            ("has@symbol", "contains @ symbol"),
            ("has#hash", "contains # symbol"),
            ("", "empty string"),
        ],
    )
    def test_invalid_mission_id_format(self, mission_id: str, reason: str):
        """Invalid mission_id formats should fail validation."""
        # Test regex directly
        if mission_id:  # Empty string handled differently
            assert MISSION_ID_PATTERN.match(mission_id) is None, (
                f"Should reject: {reason}"
            )

        # Test via schema
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id=mission_id,
                title="Test Mission",
                objective="This is a test objective with at least 10 chars",
                success_criteria=["Criterion 1"],
            )
        errors = excinfo.value.errors()
        assert any(e["loc"] == ("mission_id",) for e in errors), (
            f"Should fail for: {reason}"
        )

    def test_mission_id_max_length(self):
        """mission_id exceeding max length should fail."""
        long_id = "A" * 51  # Max is 50
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id=long_id,
                title="Test Mission",
                objective="This is a test objective with at least 10 chars",
                success_criteria=["Criterion 1"],
            )
        errors = excinfo.value.errors()
        assert any("mission_id" in str(e["loc"]) for e in errors)


# ============================================================================
# title Validation Tests
# ============================================================================


class TestTitleValidation:
    """Tests for title field validation."""

    def test_valid_title_min_length(self):
        """Title with exactly 3 characters should pass."""
        data = MissionCreate(
            mission_id="B16.1",
            title="ABC",  # Exactly 3 chars
            objective="This is a test objective with at least 10 chars",
            success_criteria=["Criterion 1"],
        )
        assert data.title == "ABC"

    def test_title_too_short(self):
        """Title with less than 3 characters should fail."""
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id="B16.1",
                title="AB",  # 2 chars, too short
                objective="This is a test objective with at least 10 chars",
                success_criteria=["Criterion 1"],
            )
        errors = excinfo.value.errors()
        assert any(e["loc"] == ("title",) for e in errors)

    def test_title_max_length(self):
        """Title with exactly 255 characters should pass."""
        long_title = "A" * 255
        data = MissionCreate(
            mission_id="B16.1",
            title=long_title,
            objective="This is a test objective with at least 10 chars",
            success_criteria=["Criterion 1"],
        )
        assert len(data.title) == 255

    def test_title_too_long(self):
        """Title exceeding 255 characters should fail."""
        long_title = "A" * 256
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id="B16.1",
                title=long_title,
                objective="This is a test objective with at least 10 chars",
                success_criteria=["Criterion 1"],
            )
        errors = excinfo.value.errors()
        assert any(e["loc"] == ("title",) for e in errors)

    def test_empty_title(self):
        """Empty title should fail validation."""
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id="B16.1",
                title="",
                objective="This is a test objective with at least 10 chars",
                success_criteria=["Criterion 1"],
            )
        errors = excinfo.value.errors()
        assert any(e["loc"] == ("title",) for e in errors)


# ============================================================================
# objective Validation Tests
# ============================================================================


class TestObjectiveValidation:
    """Tests for objective field validation."""

    def test_valid_objective_min_length(self):
        """Objective with exactly 10 characters should pass."""
        data = MissionCreate(
            mission_id="B16.1",
            title="Test Mission",
            objective="1234567890",  # Exactly 10 chars
            success_criteria=["Criterion 1"],
        )
        assert len(data.objective) == 10

    def test_objective_too_short(self):
        """Objective with less than 10 characters should fail."""
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id="B16.1",
                title="Test Mission",
                objective="123456789",  # 9 chars, too short
                success_criteria=["Criterion 1"],
            )
        errors = excinfo.value.errors()
        assert any(e["loc"] == ("objective",) for e in errors)

    def test_empty_objective(self):
        """Empty objective should fail validation."""
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id="B16.1",
                title="Test Mission",
                objective="",
                success_criteria=["Criterion 1"],
            )
        errors = excinfo.value.errors()
        assert any(e["loc"] == ("objective",) for e in errors)

    def test_long_objective_allowed(self):
        """Long objectives should be allowed."""
        long_objective = "A" * 10000
        data = MissionCreate(
            mission_id="B16.1",
            title="Test Mission",
            objective=long_objective,
            success_criteria=["Criterion 1"],
        )
        assert len(data.objective) == 10000


# ============================================================================
# success_criteria Validation Tests
# ============================================================================


class TestSuccessCriteriaValidation:
    """Tests for success_criteria field validation."""

    def test_valid_single_criterion(self):
        """Single non-empty string criterion should pass."""
        data = MissionCreate(
            mission_id="B16.1",
            title="Test Mission",
            objective="This is a valid objective",
            success_criteria=["Criterion 1"],
        )
        assert len(data.success_criteria) == 1

    def test_valid_multiple_criteria(self):
        """Multiple non-empty string criteria should pass."""
        data = MissionCreate(
            mission_id="B16.1",
            title="Test Mission",
            objective="This is a valid objective",
            success_criteria=["Criterion 1", "Criterion 2", "Criterion 3"],
        )
        assert len(data.success_criteria) == 3

    def test_empty_array_fails(self):
        """Empty success_criteria array should fail."""
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id="B16.1",
                title="Test Mission",
                objective="This is a valid objective",
                success_criteria=[],
            )
        errors = excinfo.value.errors()
        assert any("success_criteria" in str(e["loc"]) for e in errors)

    def test_empty_string_item_fails(self):
        """Empty string in success_criteria should fail."""
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id="B16.1",
                title="Test Mission",
                objective="This is a valid objective",
                success_criteria=["Valid criterion", ""],
            )
        errors = excinfo.value.errors()
        # Should indicate which item failed
        assert any("success_criteria" in str(e["loc"]) for e in errors)

    def test_whitespace_only_item_fails(self):
        """Whitespace-only string in success_criteria should fail."""
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id="B16.1",
                title="Test Mission",
                objective="This is a valid objective",
                success_criteria=["Valid", "   ", "Also valid"],
            )
        errors = excinfo.value.errors()
        assert any("success_criteria" in str(e["loc"]) for e in errors)


# ============================================================================
# status Validation Tests
# ============================================================================


class TestStatusValidation:
    """Tests for status field validation."""

    @pytest.mark.parametrize(
        "status",
        [
            "draft", "queued", "in_progress", "completed",
            "blocked", "cancelled", "validation_failed",
        ],
    )
    def test_valid_statuses(self, status: str):
        """All valid status values should pass."""
        data = MissionCreate(
            mission_id="B16.1",
            title="Test Mission",
            objective="This is a valid objective",
            success_criteria=["Criterion 1"],
            status=status,
        )
        assert data.status == status

    def test_invalid_status_fails(self):
        """Invalid status value should fail."""
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id="B16.1",
                title="Test Mission",
                objective="This is a valid objective",
                success_criteria=["Criterion 1"],
                status="invalid_status",
            )
        errors = excinfo.value.errors()
        assert any(e["loc"] == ("status",) for e in errors)

    def test_default_status_is_draft(self):
        """Default status should be 'draft'."""
        data = MissionCreate(
            mission_id="B16.1",
            title="Test Mission",
            objective="This is a valid objective",
            success_criteria=["Criterion 1"],
        )
        assert data.status == "draft"


# ============================================================================
# MissionUpdate Schema Tests
# ============================================================================


class TestMissionUpdateValidation:
    """Tests for MissionUpdate schema validation."""

    def test_partial_update_allowed(self):
        """Partial updates with only some fields should work."""
        data = MissionUpdate(title="New Title")
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {"title": "New Title"}

    def test_update_title_too_short(self):
        """Title too short in update should fail."""
        with pytest.raises(ValidationError) as excinfo:
            MissionUpdate(title="AB")
        errors = excinfo.value.errors()
        assert any(e["loc"] == ("title",) for e in errors)

    def test_update_objective_too_short(self):
        """Objective too short in update should fail."""
        with pytest.raises(ValidationError) as excinfo:
            MissionUpdate(objective="123456789")  # 9 chars
        errors = excinfo.value.errors()
        assert any(e["loc"] == ("objective",) for e in errors)

    def test_update_empty_success_criteria(self):
        """Empty success_criteria in update should fail."""
        with pytest.raises(ValidationError) as excinfo:
            MissionUpdate(success_criteria=[])
        errors = excinfo.value.errors()
        assert any("success_criteria" in str(e["loc"]) for e in errors)

    def test_update_success_criteria_with_empty_string(self):
        """success_criteria with empty string in update should fail."""
        with pytest.raises(ValidationError) as excinfo:
            MissionUpdate(success_criteria=["Valid", ""])
        errors = excinfo.value.errors()
        assert any("success_criteria" in str(e["loc"]) for e in errors)

    def test_update_invalid_status(self):
        """Invalid status in update should fail."""
        with pytest.raises(ValidationError) as excinfo:
            MissionUpdate(status="not_valid")
        errors = excinfo.value.errors()
        assert any(e["loc"] == ("status",) for e in errors)


# ============================================================================
# MissionValidator Service Tests
# ============================================================================


class TestMissionValidatorService:
    """Tests for MissionValidator service class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.validator = MissionValidator()

    def test_validate_mission_id_valid(self):
        """Valid mission_id should pass."""
        errors = self.validator.validate_mission_id("B16.1")
        assert len(errors) == 0

    def test_validate_mission_id_empty(self):
        """Empty mission_id should fail."""
        errors = self.validator.validate_mission_id("")
        assert len(errors) == 1
        assert errors[0].field == "mission_id"
        assert errors[0].code == "value_error.missing"

    def test_validate_mission_id_invalid_pattern(self):
        """Invalid pattern should fail."""
        errors = self.validator.validate_mission_id("-invalid")
        assert len(errors) == 1
        assert errors[0].field == "mission_id"
        assert "regex" in errors[0].code

    def test_validate_mission_id_too_long(self):
        """Too long mission_id should fail."""
        errors = self.validator.validate_mission_id("A" * 51)
        assert len(errors) >= 1
        assert any(e.field == "mission_id" for e in errors)

    def test_validate_title_valid(self):
        """Valid title should pass."""
        errors = self.validator.validate_title("Valid Title")
        assert len(errors) == 0

    def test_validate_title_too_short(self):
        """Title too short should fail."""
        errors = self.validator.validate_title("AB")
        assert len(errors) == 1
        assert errors[0].field == "title"

    def test_validate_objective_valid(self):
        """Valid objective should pass."""
        errors = self.validator.validate_objective("This is valid")
        assert len(errors) == 0

    def test_validate_objective_too_short(self):
        """Objective too short should fail."""
        errors = self.validator.validate_objective("123456789")
        assert len(errors) == 1
        assert errors[0].field == "objective"

    def test_validate_success_criteria_valid(self):
        """Valid success_criteria should pass."""
        errors = self.validator.validate_success_criteria(
            ["Criterion 1", "Criterion 2"]
        )
        assert len(errors) == 0

    def test_validate_success_criteria_empty_array(self):
        """Empty array should fail."""
        errors = self.validator.validate_success_criteria([])
        assert len(errors) == 1
        assert errors[0].field == "success_criteria"

    def test_validate_success_criteria_empty_item(self):
        """Empty string item should fail."""
        errors = self.validator.validate_success_criteria(["Valid", ""])
        assert len(errors) == 1
        assert "success_criteria.1" in errors[0].field

    def test_validate_success_criteria_whitespace_item(self):
        """Whitespace-only item should fail."""
        errors = self.validator.validate_success_criteria(["Valid", "   "])
        assert len(errors) == 1
        assert "success_criteria.1" in errors[0].field

    def test_validate_status_valid(self):
        """Valid status should pass."""
        errors = self.validator.validate_status("in_progress")
        assert len(errors) == 0

    def test_validate_status_invalid(self):
        """Invalid status should fail."""
        errors = self.validator.validate_status("not_a_status")
        assert len(errors) == 1
        assert errors[0].field == "status"

    def test_validate_create_payload_complete(self):
        """Complete valid payload should pass."""
        result = self.validator.validate_create_payload(
            {
                "mission_id": "B16.1",
                "title": "Test Mission",
                "objective": "This is a valid objective",
                "success_criteria": ["Criterion 1"],
            }
        )
        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_create_payload_multiple_errors(self):
        """Payload with multiple errors should report all."""
        result = self.validator.validate_create_payload(
            {
                "mission_id": "-invalid",
                "title": "AB",
                "objective": "short",
                "success_criteria": [],
            }
        )
        assert not result.is_valid
        assert len(result.errors) >= 4  # At least one error per field

    def test_validation_result_to_dict(self):
        """ValidationResult.to_dict should return proper structure."""
        result = self.validator.validate_create_payload(
            {
                "mission_id": "",
                "title": "",
                "objective": "",
                "success_criteria": None,
            }
        )
        response = result.to_dict()
        assert "valid" in response
        assert "errors" in response
        assert isinstance(response["errors"], list)
        assert all("field" in e and "message" in e for e in response["errors"])

    def test_validation_result_to_422_response(self):
        """ValidationResult.to_422_response should return FastAPI format."""
        result = self.validator.validate_create_payload(
            {
                "mission_id": "",
                "title": "AB",
                "objective": "",
                "success_criteria": None,
            }
        )
        response = result.to_422_response()
        assert "detail" in response
        assert isinstance(response["detail"], list)
        assert all("loc" in e and "msg" in e for e in response["detail"])


# ============================================================================
# Integration-style Tests
# ============================================================================


class TestValidationErrorMessages:
    """Tests ensuring error messages are clear and actionable."""

    def test_mission_id_pattern_error_message(self):
        """mission_id pattern error should explain the requirement."""
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id="-bad",
                title="Test Mission",
                objective="Valid objective here",
                success_criteria=["Criterion"],
            )
        errors = excinfo.value.errors()
        mission_id_error = next(e for e in errors if e["loc"] == ("mission_id",))
        # Check message is descriptive
        assert (
            "alphanumeric" in mission_id_error["msg"].lower()
            or "start" in mission_id_error["msg"].lower()
        )

    def test_success_criteria_item_error_identifies_index(self):
        """success_criteria item error should identify which item failed."""
        with pytest.raises(ValidationError) as excinfo:
            MissionCreate(
                mission_id="B16.1",
                title="Test Mission",
                objective="Valid objective here",
                success_criteria=["Good", "Also good", ""],
            )
        errors = excinfo.value.errors()
        # Error message should mention the index
        criteria_error = next(e for e in errors if "success_criteria" in str(e["loc"]))
        assert "2" in str(criteria_error["loc"]) or "2" in criteria_error["msg"]


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_unicode_in_mission_id_fails(self):
        """Unicode characters in mission_id should fail."""
        with pytest.raises(ValidationError):
            MissionCreate(
                mission_id="B16.1\u2019",  # Curly apostrophe
                title="Test Mission",
                objective="Valid objective here",
                success_criteria=["Criterion"],
            )

    def test_unicode_in_title_allowed(self):
        """Unicode characters in title should be allowed."""
        data = MissionCreate(
            mission_id="B16.1",
            title="Test Mission \u2014 Unicode",  # Em dash
            objective="Valid objective here",
            success_criteria=["Criterion"],
        )
        assert "\u2014" in data.title

    def test_newlines_in_objective_allowed(self):
        """Newlines in objective should be allowed."""
        data = MissionCreate(
            mission_id="B16.1",
            title="Test Mission",
            objective="Line 1\nLine 2\nLine 3",
            success_criteria=["Criterion"],
        )
        assert "\n" in data.objective

    def test_special_chars_in_success_criteria_allowed(self):
        """Special characters in success_criteria items should be allowed."""
        data = MissionCreate(
            mission_id="B16.1",
            title="Test Mission",
            objective="Valid objective here",
            success_criteria=[
                "- Uses markdown formatting",
                "* Supports bullet points",
                "1. Numbered lists work",
            ],
        )
        assert len(data.success_criteria) == 3


# ============================================================================
# T40.1 — Authoring Fields Validation Tests
# ============================================================================


class TestAuthoringFieldsOnCreate:
    """MissionCreate accepts all 11 authoring fields + constraints."""

    def _base_kwargs(self) -> dict:
        return {
            "mission_id": "AUTH-C-1",
            "title": "Authoring Create",
            "objective": "Exercise authoring fields on create payload",
            "success_criteria": ["Validation passes"],
        }

    def test_all_authoring_fields_round_trip(self):
        data = MissionCreate(
            **self._base_kwargs(),
            background="Background prose.",
            focus="Narrow focus.",
            references=[{"title": "Ref A"}],
            required_entities=["Entity A"],
            excluded_entities=["Entity B"],
            expected_output_schema={"type": "object"},
            coverage_thresholds={"min_sources": 5},
            validation_thresholds={"structural": 0.85},
            deliverable_format="markdown report",
            max_loops=6,
            min_loops=3,
            constraints=["no paywalled sources"],
        )

        assert data.background == "Background prose."
        assert data.focus == "Narrow focus."
        assert data.references == [{"title": "Ref A"}]
        assert data.required_entities == ["Entity A"]
        assert data.excluded_entities == ["Entity B"]
        assert data.expected_output_schema == {"type": "object"}
        assert data.coverage_thresholds == {"min_sources": 5}
        assert data.validation_thresholds == {"structural": 0.85}
        assert data.deliverable_format == "markdown report"
        assert data.max_loops == 6
        assert data.min_loops == 3
        assert data.constraints == ["no paywalled sources"]

    def test_all_authoring_fields_optional(self):
        """None/absent authoring fields don't break create."""
        data = MissionCreate(**self._base_kwargs())
        assert data.background is None
        assert data.max_loops is None
        assert data.constraints is None

    @pytest.mark.parametrize("bound", ["max_loops", "min_loops"])
    def test_loop_bounds_reject_zero_and_negative(self, bound: str):
        with pytest.raises(ValidationError):
            MissionCreate(**self._base_kwargs(), **{bound: 0})
        with pytest.raises(ValidationError):
            MissionCreate(**self._base_kwargs(), **{bound: -1})


class TestAuthoringFieldsOnUpdate:
    """MissionUpdate accepts authoring fields as optional partial updates."""

    def test_partial_update_single_field(self):
        data = MissionUpdate(focus="Refined focus.")
        assert data.focus == "Refined focus."
        assert data.background is None
        assert data.max_loops is None

    def test_partial_update_all_authoring_fields(self):
        data = MissionUpdate(
            background="B",
            focus="F",
            references=[{"title": "R"}],
            required_entities=["E1"],
            excluded_entities=["E2"],
            expected_output_schema={"type": "object"},
            coverage_thresholds={"c": 1},
            validation_thresholds={"v": 1},
            deliverable_format="text",
            max_loops=5,
            min_loops=2,
            constraints=["c1"],
        )
        assert data.background == "B"
        assert data.focus == "F"
        assert data.max_loops == 5
        assert data.constraints == ["c1"]

    def test_empty_update_allowed(self):
        """An empty update is valid — all fields optional."""
        data = MissionUpdate()
        assert data.model_dump(exclude_unset=True) == {}

    @pytest.mark.parametrize("bound", ["max_loops", "min_loops"])
    def test_loop_bounds_reject_zero_and_negative(self, bound: str):
        with pytest.raises(ValidationError):
            MissionUpdate(**{bound: 0})
        with pytest.raises(ValidationError):
            MissionUpdate(**{bound: -1})
