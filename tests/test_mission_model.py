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
        }
        assert required.issubset(columns), f"Missing columns: {required - columns}"

    def test_indexes_defined(self):
        """Verify expected indexes are defined."""
        index_names = {idx.name for idx in Mission.__table__.indexes}
        expected = {"idx_missions_project_status", "idx_missions_mission_id"}
        assert expected.issubset(index_names), (
            f"Missing indexes: {expected - index_names}"
        )

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
