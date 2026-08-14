"""Tests for the Mission model with DeepSearch-compatible schema.

These tests focus on unit testing the Mission model's methods and structure.
Database integration tests require PostgreSQL due to TSVECTOR columns in
other models.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

# Skip the autouse database fixture for these tests
pytestmark = pytest.mark.usefixtures()

# Import Mission directly without triggering database creation
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Avoid importing from app.models (which triggers Base creation)
# Instead import just the mission module directly
from app.models.mission import MISSION_STATUSES, Mission


class TestMissionStatuses:
    """Tests for valid mission status values."""

    def test_all_statuses_defined(self):
        """Verify all expected status values are in MISSION_STATUSES."""
        expected = {
            "draft",
            "queued",
            "in_progress",
            "completed",
            "blocked",
            "cancelled",
            "validation_failed",
        }
        assert expected == MISSION_STATUSES


class TestMissionInstantiation:
    """Tests for Mission model instantiation without database."""

    def test_create_mission_minimal(self):
        """Test creating a mission instance with required fields only."""
        mission = Mission(
            mission_id="B16.1",
            title="Test Mission",
            objective="Test the mission creation",
            success_criteria=["Criterion 1", "Criterion 2"],
        )

        assert mission.mission_id == "B16.1"
        assert mission.title == "Test Mission"
        assert mission.objective == "Test the mission creation"
        assert mission.success_criteria == ["Criterion 1", "Criterion 2"]
        # Note: status default is 'draft' but only applies at database level
        # In-memory, it's None until persisted or explicitly set

    def test_create_mission_full(self):
        """Test creating a mission instance with all fields populated."""
        now = datetime.utcnow()
        project_id = uuid.uuid4()
        report_id = uuid.uuid4()

        mission = Mission(
            project_id=project_id,
            mission_id="B16.2",
            title="Full Mission Test",
            objective="Test all mission fields",
            success_criteria=["Success 1", "Success 2", "Success 3"],
            context={"background": "Testing context"},
            deliverables=["Deliverable 1", "Deliverable 2"],
            research_phases={"phase1": "Planning"},
            tags=["test", "integration"],
            mission_metadata={"priority": "high"},
            status="queued",
            queued_at=now,
            deepsearch_job_id="job-123",
            result_report_id=report_id,
            result_markdown="# Results",
            result_protocol={"status": "completed"},
            created_by="test-agent",
        )

        assert mission.project_id == project_id
        assert mission.context == {"background": "Testing context"}
        assert mission.deliverables == ["Deliverable 1", "Deliverable 2"]
        assert mission.tags == ["test", "integration"]
        assert mission.mission_metadata == {"priority": "high"}
        assert mission.status == "queued"
        assert mission.queued_at == now
        assert mission.deepsearch_job_id == "job-123"
        assert mission.result_report_id == report_id
        assert mission.result_markdown == "# Results"
        assert mission.result_protocol == {"status": "completed"}
        assert mission.created_by == "test-agent"


class TestMissionMethods:
    """Tests for Mission model helper methods."""

    def test_to_dict(self):
        """Test the to_dict method includes all fields."""
        mission = Mission(
            mission_id="DICT-1",
            title="Dict Test",
            objective="Test to_dict",
            success_criteria=["Criterion"],
            tags=["test"],
            status="in_progress",
        )
        # Manually set id for testing
        mission.id = uuid.uuid4()
        mission.created_at = datetime.utcnow()
        mission.updated_at = datetime.utcnow()

        result = mission.to_dict()

        assert result["mission_id"] == "DICT-1"
        assert result["title"] == "Dict Test"
        assert result["objective"] == "Test to_dict"
        assert result["success_criteria"] == ["Criterion"]
        assert result["tags"] == ["test"]
        assert result["status"] == "in_progress"
        assert result["id"] is not None
        assert result["created_at"] is not None
        # Check for result fields
        assert "result_markdown" in result
        assert "result_document_ids" in result
        assert "execution_metadata" in result

    def test_to_dict_with_none_values(self):
        """Test to_dict handles None values correctly."""
        mission = Mission(
            mission_id="DICT-2",
            title="None Values Test",
            objective="Test None handling",
            success_criteria=["Criterion"],
        )

        result = mission.to_dict()

        # These should default to empty containers
        assert result["context"] == {}
        assert result["deliverables"] == []
        assert result["tags"] == []
        assert result["execution_metadata"] == {}
        assert result["result_document_ids"] == []
        # These can be None
        assert result["queued_at"] is None
        assert result["started_at"] is None
        assert result["completed_at"] is None
        assert result["result_markdown"] is None

    def test_to_mission_protocol(self):
        """Test conversion to Mission Protocol format."""
        mission = Mission(
            mission_id="PROTO-1",
            title="Protocol Test",
            objective="Test Mission Protocol conversion",
            success_criteria=["Criterion 1", "Criterion 2"],
            context={"key": "value"},
            deliverables=["Deliverable"],
            research_phases={"phase": "test"},
            tags=["proto"],
            mission_metadata={"meta": "data"},
            # These should NOT appear in protocol output
            status="in_progress",
            result_markdown="Some results",
        )

        proto = mission.to_mission_protocol()

        # Should include mission definition fields
        assert proto["mission_id"] == "PROTO-1"
        assert proto["title"] == "Protocol Test"
        assert proto["objective"] == "Test Mission Protocol conversion"
        assert proto["success_criteria"] == ["Criterion 1", "Criterion 2"]
        assert proto["context"] == {"key": "value"}
        assert proto["deliverables"] == ["Deliverable"]
        assert proto["research_phases"] == {"phase": "test"}
        assert proto["tags"] == ["proto"]
        assert proto["metadata"] == {"meta": "data"}
        # Should NOT include execution or result fields
        assert "status" not in proto
        assert "result_markdown" not in proto
        assert "queued_at" not in proto
        assert "id" not in proto

    def test_from_mission_protocol_minimal(self):
        """Test creating a Mission from minimal Mission Protocol definition."""
        protocol = {
            "mission_id": "FROM-PROTO-1",
            "title": "From Protocol",
            "objective": "Create from Mission Protocol",
            "success_criteria": ["Criterion"],
        }

        mission = Mission.from_mission_protocol(protocol)

        assert mission.mission_id == "FROM-PROTO-1"
        assert mission.title == "From Protocol"
        assert mission.objective == "Create from Mission Protocol"
        assert mission.success_criteria == ["Criterion"]
        # Optional fields should have defaults
        assert mission.context == {}
        assert mission.deliverables == []
        assert mission.research_phases == {}
        assert mission.tags == []
        assert mission.mission_metadata == {}

    def test_from_mission_protocol_full(self):
        """Test creating a Mission from full Mission Protocol definition."""
        project_id = uuid.uuid4()
        protocol = {
            "mission_id": "FROM-PROTO-2",
            "title": "From Protocol Full",
            "objective": "Create from full Mission Protocol",
            "success_criteria": ["Criterion 1", "Criterion 2"],
            "context": {"source": "protocol"},
            "deliverables": ["Result 1", "Result 2"],
            "research_phases": {"discovery": {"status": "planned"}},
            "tags": ["imported", "test"],
            "metadata": {"imported": True, "version": "1.0"},
        }

        mission = Mission.from_mission_protocol(
            protocol,
            project_id=project_id,
            created_by="import-agent",
        )

        assert mission.mission_id == "FROM-PROTO-2"
        assert mission.project_id == project_id
        assert mission.created_by == "import-agent"
        assert mission.context == {"source": "protocol"}
        assert mission.deliverables == ["Result 1", "Result 2"]
        assert mission.research_phases == {"discovery": {"status": "planned"}}
        assert mission.tags == ["imported", "test"]
        assert mission.mission_metadata == {"imported": True, "version": "1.0"}


class TestMissionResultFields:
    """Tests for Mission result and execution tracking fields."""

    def test_execution_lifecycle_fields(self):
        """Test setting execution timestamps."""
        mission = Mission(
            mission_id="EXEC-1",
            title="Execution Test",
            objective="Test execution lifecycle",
            success_criteria=["Complete successfully"],
        )

        now = datetime.utcnow()

        # Queue the mission
        mission.status = "queued"
        mission.queued_at = now
        assert mission.queued_at == now
        assert mission.started_at is None

        # Start the mission
        mission.status = "in_progress"
        mission.started_at = now
        mission.deepsearch_job_id = "ds-job-abc123"
        assert mission.started_at == now
        assert mission.deepsearch_job_id == "ds-job-abc123"

        # Complete the mission
        mission.status = "completed"
        mission.completed_at = now
        mission.result_markdown = "# Results\n\nMission completed."
        mission.result_document_ids = [str(uuid.uuid4())]
        assert mission.completed_at == now
        assert len(mission.result_document_ids) == 1

    def test_result_protocol_storage(self):
        """Test storing Mission Protocol result object."""
        mission = Mission(
            mission_id="RESULT-1",
            title="Result Test",
            objective="Test result protocol storage",
            success_criteria=["Store result"],
        )
        mission.result_protocol = {
            "status": "completed",
            "findings": ["Finding 1", "Finding 2"],
            "recommendations": ["Rec 1"],
            "evidence_summary": {"total_sources": 10, "used_sources": 5},
        }

        assert mission.result_protocol["status"] == "completed"
        assert len(mission.result_protocol["findings"]) == 2
        assert mission.result_protocol["evidence_summary"]["total_sources"] == 10

    def test_error_handling_fields(self):
        """Test storing error information."""
        mission = Mission(
            mission_id="ERROR-1",
            title="Error Test",
            objective="Test error storage",
            success_criteria=["Handle errors"],
            status="blocked",
            error_message="Failed to connect to DeepSearch API: Connection timeout",
        )

        assert mission.status == "blocked"
        assert "Connection timeout" in mission.error_message


class TestMissionTableDefinition:
    """Tests for Mission table structure and constraints."""

    def test_table_name(self):
        """Verify the table name is correct."""
        assert Mission.__tablename__ == "missions"

    def test_required_columns_exist(self):
        """Verify all required columns are defined."""
        columns = {col.name for col in Mission.__table__.columns}
        required = {
            "id",
            "project_id",
            "mission_id",
            "title",
            "objective",
            "success_criteria",
            "context",
            "deliverables",
            "research_phases",
            "tags",
            "mission_metadata",
            "status",
            "queued_at",
            "started_at",
            "completed_at",
            "deepsearch_job_id",
            "execution_metadata",
            "result_document_ids",
            "result_report_id",
            "result_markdown",
            "result_protocol",
            "error_message",
            "created_at",
            "updated_at",
            "created_by",
            # T40.1 authoring fields
            "background",
            "focus",
            "references",
            "required_entities",
            "excluded_entities",
            "expected_output_schema",
            "coverage_thresholds",
            "validation_thresholds",
            "deliverable_format",
            "max_loops",
            "min_loops",
            "constraints",
            # DeepSearch lease boundary (migration 039). These remain internal:
            # workers need them for fenced claims, but REST/MCP serializers must
            # never expose the opaque token.
            "deepsearch_lease_owner",
            "deepsearch_lease_token",
            "deepsearch_leased_at",
            "deepsearch_heartbeat_at",
            "deepsearch_lease_expires_at",
            "deepsearch_attempt_count",
            "deepsearch_result_key",
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    def test_indexes_defined(self):
        """Verify expected indexes are defined."""
        index_names = {idx.name for idx in Mission.__table__.indexes}
        expected = {
            "idx_missions_project_status",
            "idx_missions_mission_id",
            "missions_deepsearch_lease_token_active_uq",
            "missions_deepsearch_result_key_uq",
            "missions_deepsearch_claim_scan_idx",
        }
        assert expected.issubset(index_names), (
            f"Missing indexes: {expected - index_names}"
        )

    def test_lease_timestamps_are_timezone_aware(self):
        """Lease comparisons use NOW(); dropping timezone would corrupt fencing."""
        for name in (
            "deepsearch_leased_at",
            "deepsearch_heartbeat_at",
            "deepsearch_lease_expires_at",
        ):
            assert Mission.__table__.columns[name].type.timezone is True

    def test_opaque_lease_fields_are_not_public_dict_fields(self):
        """Ownership proofs must never leak through the model's public serializer."""
        lease_token = uuid.uuid4().hex
        result_key = uuid.uuid4().hex
        mission = Mission(
            mission_id="LEASE-PRIVATE-1",
            title="Lease privacy",
            objective="Keep worker fencing credentials private",
            success_criteria=["No opaque token in output"],
            deepsearch_lease_owner="worker-a",
            deepsearch_lease_token=lease_token,
            deepsearch_result_key=result_key,
        )

        serialized = mission.to_dict()

        assert "deepsearch_lease_token" not in serialized
        assert "deepsearch_result_key" not in serialized

    def test_constraints_defined(self):
        """Verify check constraints are defined."""
        constraint_names = {
            c.name
            for c in Mission.__table__.constraints
            if hasattr(c, "name") and c.name
        }
        expected = {
            "success_criteria_not_empty",
            "title_length",
            "valid_mission_status",
        }
        assert expected.issubset(constraint_names), (
            f"Missing constraints: {expected - constraint_names}"
        )


class TestMissionAuthoringFields:
    """T40.1 — authoring fields consumed by DeepSearch contract compiler."""

    def _full_authoring_kwargs(self) -> dict:
        return {
            "background": "Background prose for the mission.",
            "focus": "Narrow framing for the research question.",
            "references": [{"title": "Ref A"}, {"title": "Ref B"}],
            "required_entities": ["Contrast-Consistent Search", "CCS"],
            "excluded_entities": ["unrelated acronym"],
            "expected_output_schema": {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
            },
            "coverage_thresholds": {"min_sources": 5, "min_per_entity": 2},
            "validation_thresholds": {"structural": 0.85, "coverage": 0.70},
            "deliverable_format": "markdown report",
            "max_loops": 6,
            "min_loops": 3,
            "constraints": ["no paywalled sources", "prefer peer-reviewed"],
        }

    def test_instantiation_with_all_authoring_fields(self):
        mission = Mission(
            mission_id="AUTH-1",
            title="Authoring Test",
            objective="Exercise every authoring field",
            success_criteria=["Round-trip works"],
            **self._full_authoring_kwargs(),
        )

        for field, value in self._full_authoring_kwargs().items():
            assert getattr(mission, field) == value, f"mismatch on {field}"

    def test_to_dict_includes_authoring_fields(self):
        mission = Mission(
            mission_id="AUTH-2",
            title="Dict Round Trip",
            objective="All authoring fields emit in to_dict",
            success_criteria=["Round-trip works"],
            **self._full_authoring_kwargs(),
        )
        mission.id = uuid.uuid4()
        mission.created_at = datetime.utcnow()
        mission.updated_at = datetime.utcnow()

        result = mission.to_dict()

        for field, value in self._full_authoring_kwargs().items():
            assert result[field] == value, f"to_dict missing {field}"

    def test_to_mission_protocol_includes_authoring_fields(self):
        mission = Mission(
            mission_id="AUTH-3",
            title="Protocol Round Trip",
            objective="All authoring fields emit in protocol form",
            success_criteria=["Round-trip works"],
            **self._full_authoring_kwargs(),
        )

        proto = mission.to_mission_protocol()

        for field, value in self._full_authoring_kwargs().items():
            assert proto[field] == value, f"to_mission_protocol missing {field}"

    def test_from_mission_protocol_round_trip(self):
        protocol = {
            "mission_id": "AUTH-4",
            "title": "From Protocol Authoring",
            "objective": "Instantiate via from_mission_protocol",
            "success_criteria": ["Round-trip works"],
            **self._full_authoring_kwargs(),
        }

        mission = Mission.from_mission_protocol(protocol)

        for field, value in self._full_authoring_kwargs().items():
            assert getattr(mission, field) == value, f"mismatch on {field}"

    def test_constraints_fallback_to_context(self):
        """Legacy missions stored constraints inside `context`; fallback exposes them."""
        mission = Mission(
            mission_id="AUTH-5",
            title="Fallback Constraints",
            objective="constraints column null, context has legacy data",
            success_criteria=["Fallback works"],
            context={"constraints": ["legacy constraint"]},
        )

        result = mission.to_dict()
        assert result["constraints"] == ["legacy constraint"]

        proto = mission.to_mission_protocol()
        assert proto["constraints"] == ["legacy constraint"]

    def test_constraints_column_wins_over_context(self):
        """When both are populated, the promoted column is authoritative."""
        mission = Mission(
            mission_id="AUTH-6",
            title="Column Wins",
            objective="constraints column takes precedence",
            success_criteria=["Precedence works"],
            context={"constraints": ["legacy"]},
            constraints=["new column"],
        )

        result = mission.to_dict()
        assert result["constraints"] == ["new column"]

    def test_authoring_fields_optional(self):
        """Every authoring field is nullable — default instantiation succeeds."""
        mission = Mission(
            mission_id="AUTH-7",
            title="Optional Defaults",
            objective="None for every authoring field is allowed",
            success_criteria=["Nulls OK"],
        )

        for field in self._full_authoring_kwargs():
            assert getattr(mission, field) is None, f"{field} should default to None"
