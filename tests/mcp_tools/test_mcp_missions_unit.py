"""Unit tests for MCP mission management tools (B16.4).

These tests verify the MCP tool definitions and handlers without requiring
database access. For integration tests that require the database, see
test_mcp_missions.py.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import MagicMock


def _make_mission_mock(**overrides):
    """Build a Mission mock with safe defaults for every attribute the
    MCP serializer reads.

    MagicMock returns a child MagicMock for any unset attribute, which
    poisons JSON serialization and the truthiness check in the constraints
    fallback. Centralize the defaults here so individual tests only set the
    fields they care about.
    """
    mission = MagicMock()
    mission.id = overrides.pop("id", "test-uuid")
    mission.project_id = overrides.pop("project_id", None)
    mission.project = overrides.pop("project", None)
    mission.mission_id = overrides.pop("mission_id", "MCP-TEST")
    mission.title = overrides.pop("title", "Test")
    mission.objective = overrides.pop("objective", "Test objective")
    mission.success_criteria = overrides.pop("success_criteria", ["c1"])
    mission.context = overrides.pop("context", {})
    mission.deliverables = overrides.pop("deliverables", [])
    mission.research_phases = overrides.pop("research_phases", {})
    mission.tags = overrides.pop("tags", [])
    mission.mission_metadata = overrides.pop("mission_metadata", {})
    mission.research_depth = overrides.pop("research_depth", "baseline")
    # Mission-authoring fields (T40.1).
    mission.background = overrides.pop("background", None)
    mission.focus = overrides.pop("focus", None)
    mission.references = overrides.pop("references", None)
    mission.required_entities = overrides.pop("required_entities", None)
    mission.excluded_entities = overrides.pop("excluded_entities", None)
    mission.expected_output_schema = overrides.pop("expected_output_schema", None)
    mission.coverage_thresholds = overrides.pop("coverage_thresholds", None)
    mission.validation_thresholds = overrides.pop("validation_thresholds", None)
    mission.deliverable_format = overrides.pop("deliverable_format", None)
    mission.max_loops = overrides.pop("max_loops", None)
    mission.min_loops = overrides.pop("min_loops", None)
    mission.constraints = overrides.pop("constraints", None)
    mission.status = overrides.pop("status", "draft")
    mission.queued_at = overrides.pop("queued_at", None)
    mission.started_at = overrides.pop("started_at", None)
    mission.completed_at = overrides.pop("completed_at", None)
    mission.deepsearch_job_id = overrides.pop("deepsearch_job_id", None)
    mission.execution_metadata = overrides.pop("execution_metadata", {})
    mission.result_document_ids = overrides.pop("result_document_ids", [])
    mission.result_report_id = overrides.pop("result_report_id", None)
    mission.result_markdown = overrides.pop("result_markdown", None)
    mission.result_protocol = overrides.pop("result_protocol", None)
    mission.error_message = overrides.pop("error_message", None)
    mission.created_at = overrides.pop("created_at", datetime.utcnow())
    mission.updated_at = overrides.pop("updated_at", datetime.utcnow())
    mission.created_by = overrides.pop("created_by", None)
    if overrides:
        raise TypeError(f"Unknown mission attrs: {sorted(overrides)}")
    return mission


class TestMissionToolDefinitions:
    """Tests for MCP tool definitions - no database required."""

    def test_mission_tools_defined(self):
        """All mission tools are defined."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool_names = [t.name for t in MISSION_TOOLS]
        assert "create_mission" in tool_names
        assert "list_missions" in tool_names
        assert "get_mission" in tool_names
        assert "submit_mission" in tool_names
        assert "get_mission_status" in tool_names

    def test_create_mission_tool_schema(self):
        """create_mission tool has correct schema."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "create_mission")
        assert tool.description is not None
        assert "Create a new mission" in tool.description
        schema = tool.inputSchema
        assert schema["type"] == "object"
        assert "mission_id" in schema["properties"]
        assert "title" in schema["properties"]
        assert "objective" in schema["properties"]
        assert "success_criteria" in schema["properties"]
        assert schema["required"] == [
            "mission_id",
            "title",
            "objective",
            "success_criteria",
        ]

    def test_list_missions_tool_schema(self):
        """list_missions tool has correct schema."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "list_missions")
        assert tool.description is not None
        schema = tool.inputSchema
        assert "project_id" in schema["properties"]
        assert "status" in schema["properties"]
        assert "page" in schema["properties"]
        assert "page_size" in schema["properties"]

    def test_list_missions_status_enum(self):
        """list_missions status field has correct enum values."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "list_missions")
        status_schema = tool.inputSchema["properties"]["status"]
        assert "enum" in status_schema
        assert "draft" in status_schema["enum"]
        assert "queued" in status_schema["enum"]
        assert "in_progress" in status_schema["enum"]
        assert "completed" in status_schema["enum"]
        assert "blocked" in status_schema["enum"]
        assert "cancelled" in status_schema["enum"]

    def test_get_mission_tool_schema(self):
        """get_mission tool has correct schema."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "get_mission")
        assert tool.description is not None
        schema = tool.inputSchema
        assert "mission_id" in schema["properties"]
        assert schema["required"] == ["mission_id"]

    def test_submit_mission_tool_schema(self):
        """submit_mission tool has correct schema."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "submit_mission")
        assert tool.description is not None
        assert "DeepSearch" in tool.description
        schema = tool.inputSchema
        assert "mission_id" in schema["properties"]
        assert schema["required"] == ["mission_id"]

    def test_get_mission_status_tool_schema(self):
        """get_mission_status tool has correct schema."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "get_mission_status")
        assert tool.description is not None
        schema = tool.inputSchema
        assert "mission_id" in schema["properties"]
        assert schema["required"] == ["mission_id"]

    def test_create_mission_optional_fields(self):
        """create_mission has all optional fields defined."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "create_mission")
        schema = tool.inputSchema
        props = schema["properties"]

        # Check optional fields exist
        assert "project_id" in props
        assert "context" in props
        assert "deliverables" in props
        assert "research_phases" in props
        assert "tags" in props
        assert "priority" in props
        assert "max_loops" in props

    def test_create_mission_priority_enum(self):
        """create_mission priority has correct enum values."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "create_mission")
        priority_schema = tool.inputSchema["properties"]["priority"]
        assert "enum" in priority_schema
        assert "low" in priority_schema["enum"]
        assert "normal" in priority_schema["enum"]
        assert "high" in priority_schema["enum"]
        assert "critical" in priority_schema["enum"]


class TestMCPServerIntegration:
    """Integration tests for MCP server setup - no database required."""

    def test_create_mcp_server(self):
        """MCP server can be created."""
        from app.mcp_server.server import create_mcp_server

        server = create_mcp_server("test-tracelab")
        assert server is not None

    def test_create_mcp_server_custom_name(self):
        """MCP server accepts custom name."""
        from app.mcp_server.server import create_mcp_server

        server = create_mcp_server("custom-server-name")
        assert server is not None

    def test_register_mission_tools(self):
        """Mission tools can be registered with server."""
        from mcp.server import Server

        from app.mcp_server.tools.missions import register_mission_tools

        server = Server("test-server")
        register_mission_tools(server)
        # If no exception, registration succeeded


class TestToolHandlerDispatch:
    """Tests for tool handler dispatch - no database required."""

    def test_tool_handlers_exist(self):
        """All tools have corresponding handlers."""
        from app.mcp_server.tools.missions import MISSION_TOOLS, TOOL_HANDLERS

        tool_names = [t.name for t in MISSION_TOOLS]
        for name in tool_names:
            assert name in TOOL_HANDLERS, f"Missing handler for {name}"

    def test_tool_handlers_are_callable(self):
        """All tool handlers are async callable."""
        from app.mcp_server.tools.missions import TOOL_HANDLERS

        for name, handler in TOOL_HANDLERS.items():
            assert asyncio.iscoroutinefunction(handler), f"{name} handler is not async"

    def test_handler_count_matches_tools(self):
        """Number of handlers matches number of tools."""
        from app.mcp_server.tools.missions import MISSION_TOOLS, TOOL_HANDLERS

        assert len(TOOL_HANDLERS) == len(MISSION_TOOLS)


class TestSerializeMission:
    """Tests for mission serialization helper - uses mocks."""

    def test_serialize_mission_basic(self):
        """Serialize basic mission to dict."""
        from app.mcp_server.tools.missions import _serialize_mission

        # Create a mock mission
        mission = _make_mission_mock(
            id="test-uuid",
            mission_id="MCP-TEST-001",
            title="Test Mission",
            objective="Test objective",
            success_criteria=["Criterion 1"],
            context={"key": "value"},
            deliverables=["file.py"],
            tags=["test"],
            mission_metadata={"priority": "normal"},
            created_by="test",
        )

        result = _serialize_mission(mission)

        assert result["mission_id"] == "MCP-TEST-001"
        assert result["id"] == "test-uuid"
        assert result["status"] == "draft"
        assert result["title"] == "Test Mission"

    def test_serialize_mission_with_results(self):
        """Serialize mission with results."""
        import uuid

        from app.mcp_server.tools.missions import _serialize_mission

        doc_id = str(uuid.uuid4())
        report_id = str(uuid.uuid4())

        completed = datetime.utcnow()
        mission = _make_mission_mock(
            id="test-uuid-2",
            project_id="project-uuid",
            mission_id="MCP-TEST-002",
            title="Completed Mission",
            objective="Test completed",
            success_criteria=["Done"],
            status="completed",
            queued_at=completed,
            started_at=completed,
            completed_at=completed,
            deepsearch_job_id="ds-job-123",
            execution_metadata={"duration_ms": 5000},
            result_document_ids=[doc_id],
            result_report_id=report_id,
            result_markdown="# Results",
            result_protocol={"version": "1.0"},
            created_by="mcp-tool",
        )

        result = _serialize_mission(mission)

        assert result["status"] == "completed"
        assert result["deepsearch_job_id"] == "ds-job-123"
        assert result["result_markdown"] == "# Results"
        assert len(result["result_document_ids"]) == 1
        assert result["result_report_id"] == report_id
        assert result["completed_at"] is not None

    def test_serialize_mission_null_fields(self):
        """Serialize mission with null optional fields."""
        from app.mcp_server.tools.missions import _serialize_mission

        mission = _make_mission_mock(
            id="test-uuid-3",
            mission_id="MCP-TEST-003",
            title="Minimal",
            objective="Minimal mission",
            success_criteria=["Test"],
            context=None,
            deliverables=None,
            research_phases=None,
            tags=None,
            mission_metadata=None,
            execution_metadata=None,
            result_document_ids=None,
        )

        result = _serialize_mission(mission)

        assert result["project_id"] is None
        assert result["context"] == {}
        assert result["deliverables"] == []
        assert result["result_markdown"] is None

    def test_serialize_mission_includes_t40_1_fields(self):
        """T41.2: serializer must surface all 12 T40.1 mission-authoring fields.

        Mirrors REST behavior at app/api/v1/missions.py:84-96. Discovered
        2026-04-27 during DeepSearch triage when MCP get_mission returned 11
        of 23 fields for OODS-FIGMA-HOST-01 (UUID 2a781109-...d22e).
        """
        from app.mcp_server.tools.missions import _serialize_mission

        references = [{"title": "AWS Lambda docs"}]
        required_entities = [
            "AWS Lambda",
            "Google Cloud Run",
            "Vercel Functions",
            "Fly.io",
            "Railway",
        ]
        excluded_entities = ["AWS EC2"]
        expected_output_schema = {"type": "comparison_matrix"}
        coverage_thresholds = {"min_sources": 50}
        validation_thresholds = {"min_score": 7.0}
        constraints = ["No AWS-only solutions"]

        mission = _make_mission_mock(
            id="t41-2-uuid",
            mission_id="OODS-FIGMA-HOST-01",
            title="Mission-authoring fields round-trip",
            objective="Surface T40.1 fields through MCP",
            success_criteria=["all 12 fields present"],
            background="Hosted code-execution platforms for OODS evaluation.",
            focus="Serverless containerized execution with sub-second cold starts.",
            references=references,
            required_entities=required_entities,
            excluded_entities=excluded_entities,
            expected_output_schema=expected_output_schema,
            coverage_thresholds=coverage_thresholds,
            validation_thresholds=validation_thresholds,
            deliverable_format="comparison table",
            max_loops=8,
            min_loops=3,
            constraints=constraints,
        )

        result = _serialize_mission(mission)

        assert result["background"] == mission.background
        assert result["focus"] == mission.focus
        assert result["references"] == references
        assert result["required_entities"] == required_entities
        assert result["excluded_entities"] == excluded_entities
        assert result["expected_output_schema"] == expected_output_schema
        assert result["coverage_thresholds"] == coverage_thresholds
        assert result["validation_thresholds"] == validation_thresholds
        assert result["deliverable_format"] == "comparison table"
        assert result["max_loops"] == 8
        assert result["min_loops"] == 3
        assert result["constraints"] == constraints

    def test_serialize_mission_constraints_fallback_from_context(self):
        """Legacy missions store constraints inside context; MCP must surface them.

        Mirrors REST fallback at app/api/v1/missions.py:64-68 so DS readers see
        the same value through either surface for pre-T40.1 missions.
        """
        from app.mcp_server.tools.missions import _serialize_mission

        legacy_constraints = ["legacy: stored in context"]
        mission = _make_mission_mock(
            id="legacy-uuid",
            mission_id="LEGACY-001",
            title="Legacy mission",
            objective="Pre-T40.1 mission with constraints in context",
            success_criteria=["fallback works"],
            context={"constraints": legacy_constraints, "other": "data"},
            constraints=None,  # column is null
        )

        result = _serialize_mission(mission)

        assert result["constraints"] == legacy_constraints

    def test_serialize_mission_constraints_column_wins_over_context(self):
        """When the constraints column is populated, prefer it over context."""
        from app.mcp_server.tools.missions import _serialize_mission

        mission = _make_mission_mock(
            id="modern-uuid",
            mission_id="MODERN-001",
            title="Modern mission",
            objective="Post-T40.1 mission with both column and context",
            success_criteria=["column wins"],
            context={"constraints": ["context-only"]},
            constraints=["from-column"],
        )

        result = _serialize_mission(mission)

        assert result["constraints"] == ["from-column"]


class TestSerializeMissionSlimFullSplit:
    """T41.4: heavy-blob trimming behavior on _serialize_mission.

    The OODS-FIGMA-HOST-01 trigger mission's execution_metadata is ~16KB —
    well past MCP transport limits in some clients. Default `slim=True`
    summarizes large blobs; `slim=False` is for the explicit opt-in path.
    """

    def _make_large_metadata(self, target_bytes: int = 8000) -> dict:
        """Build an execution_metadata-shaped dict that serializes above
        the trim threshold so the trim branch fires."""
        # Repeating a long string produces predictable byte size.
        chunk = "x" * 100
        items = max(1, target_bytes // len(chunk))
        return {
            "duration_ms": 663620,
            "loops_executed": 3,
            "trace": [chunk for _ in range(items)],
        }

    def test_slim_default_summarizes_large_execution_metadata(self):
        from app.mcp_server.tools.missions import _serialize_mission

        large_meta = self._make_large_metadata()
        mission = _make_mission_mock(
            id="big-meta-uuid",
            mission_id="BIG-META-001",
            execution_metadata=large_meta,
        )

        result = _serialize_mission(mission)  # slim=True is default

        assert isinstance(result["execution_metadata"], dict)
        assert result["execution_metadata"]["_trimmed"] is True
        assert result["execution_metadata"]["field"] == "execution_metadata"
        assert result["execution_metadata"]["byte_size"] > 5_000
        assert "include_execution_metadata" in result["execution_metadata"]["hint"]

    def test_full_mode_returns_untrimmed_execution_metadata(self):
        from app.mcp_server.tools.missions import _serialize_mission

        large_meta = self._make_large_metadata()
        mission = _make_mission_mock(
            id="big-meta-uuid-2",
            mission_id="BIG-META-002",
            execution_metadata=large_meta,
        )

        result = _serialize_mission(mission, slim=False)

        assert result["execution_metadata"] == large_meta
        assert "_trimmed" not in result["execution_metadata"]

    def test_slim_leaves_small_execution_metadata_alone(self):
        from app.mcp_server.tools.missions import _serialize_mission

        small_meta = {"duration_ms": 5000, "loops": 3}
        mission = _make_mission_mock(
            id="small-meta-uuid",
            mission_id="SMALL-META-001",
            execution_metadata=small_meta,
        )

        result = _serialize_mission(mission)

        assert result["execution_metadata"] == small_meta
        # No trim stub — the field is small enough to send raw.
        assert "_trimmed" not in str(result["execution_metadata"])

    def test_slim_summarizes_large_result_protocol(self):
        from app.mcp_server.tools.missions import _serialize_mission

        protocol = {"version": "1.0", "items": ["x" * 100 for _ in range(100)]}
        mission = _make_mission_mock(
            id="big-proto-uuid",
            mission_id="BIG-PROTO-001",
            result_protocol=protocol,
        )

        result = _serialize_mission(mission)

        assert isinstance(result["result_protocol"], dict)
        assert result["result_protocol"]["_trimmed"] is True
        assert result["result_protocol"]["field"] == "result_protocol"

    def test_slim_summarizes_large_result_markdown_with_preview(self):
        from app.mcp_server.tools.missions import _serialize_mission

        markdown = "# Title\n" + ("Body paragraph. " * 1000)
        assert len(markdown.encode("utf-8")) > 5_000
        mission = _make_mission_mock(
            id="big-md-uuid",
            mission_id="BIG-MD-001",
            result_markdown=markdown,
        )

        result = _serialize_mission(mission)

        assert isinstance(result["result_markdown"], dict)
        assert result["result_markdown"]["_trimmed"] is True
        assert result["result_markdown"]["field"] == "result_markdown"
        assert result["result_markdown"]["byte_size"] == len(markdown.encode("utf-8"))
        assert result["result_markdown"]["preview"].startswith("# Title")
        assert result["result_markdown"]["preview"].endswith("...")

    def test_slim_leaves_small_result_markdown_alone(self):
        from app.mcp_server.tools.missions import _serialize_mission

        markdown = "# Short report\n\nBrief findings."
        mission = _make_mission_mock(
            id="small-md-uuid",
            mission_id="SMALL-MD-001",
            result_markdown=markdown,
        )

        result = _serialize_mission(mission)
        assert result["result_markdown"] == markdown

    def test_slim_payload_under_8kb_for_realistic_completed_mission(self):
        """End-to-end size guarantee — the documented 8KB cap holds for the
        kind of completed mission that triggered T41.4 in the first place."""
        import json

        from app.mcp_server.tools.missions import _serialize_mission

        mission = _make_mission_mock(
            id="realistic-uuid",
            mission_id="OODS-FIGMA-HOST-01",
            title="Backend Hosting Architecture for OODS-for-Figma V1.5 Drift Workloads",
            objective=(
                "Compare backend hosting platforms for a Figma plugin backend "
                "that runs multi-minute pipeline workloads."
            ),
            success_criteria=[
                "Recommendation grounded in vendor docs and independent benchmarks",
                "Distinguish platforms with native browser-automation",
                "Document timeout ceilings and architectural patterns",
                "Pricing model captured for burst-and-idle profile",
            ],
            background="OODS-for-Figma V1.5 introduces a hosted backend...",
            required_entities=[
                "AWS Lambda",
                "Google Cloud Run",
                "Vercel Functions",
                "Fly.io",
                "Railway",
            ],
            excluded_entities=["Heroku", "Netlify Functions", "Azure Functions"],
            max_loops=3,
            status="completed",
            execution_metadata=self._make_large_metadata(target_bytes=16_000),
            result_markdown="# Hosting Comparison Matrix\n" + ("x " * 5000),
        )

        result = _serialize_mission(mission)
        size = len(json.dumps(result, indent=2, default=str).encode("utf-8"))
        assert size < 8_000, (
            f"slim payload was {size} bytes — exceeds documented 8KB cap. "
            f"Trimming logic must be reviewed."
        )


class TestMCPModuleExports:
    """Tests for MCP module exports."""

    def test_mcp_init_exports(self):
        """MCP __init__ exports create_mcp_server."""
        from app.mcp_server import create_mcp_server

        assert callable(create_mcp_server)

    def test_tools_init_exports(self):
        """Tools __init__ exports missions module."""
        from app.mcp_server.tools import missions

        assert hasattr(missions, "MISSION_TOOLS")
        assert hasattr(missions, "TOOL_HANDLERS")


class TestToolSchemaConstraints:
    """Tests for tool schema constraints and validation rules."""

    def test_mission_id_constraints(self):
        """mission_id field has proper constraints."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "create_mission")
        mission_id_schema = tool.inputSchema["properties"]["mission_id"]
        assert mission_id_schema["minLength"] == 1
        assert mission_id_schema["maxLength"] == 50

    def test_title_constraints(self):
        """title field has proper constraints."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "create_mission")
        title_schema = tool.inputSchema["properties"]["title"]
        assert title_schema["minLength"] == 3
        assert title_schema["maxLength"] == 255

    def test_objective_constraints(self):
        """objective field has proper constraints."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "create_mission")
        objective_schema = tool.inputSchema["properties"]["objective"]
        assert objective_schema["minLength"] == 10

    def test_success_criteria_constraints(self):
        """success_criteria field has proper constraints."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "create_mission")
        criteria_schema = tool.inputSchema["properties"]["success_criteria"]
        assert criteria_schema["type"] == "array"
        assert criteria_schema["minItems"] == 1

    def test_max_loops_constraints(self):
        """max_loops field has proper constraints."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "create_mission")
        max_loops_schema = tool.inputSchema["properties"]["max_loops"]
        assert max_loops_schema["default"] == 3
        assert max_loops_schema["minimum"] == 1
        assert max_loops_schema["maximum"] == 10

    def test_page_size_constraints(self):
        """list_missions page_size has proper constraints."""
        from app.mcp_server.tools.missions import MISSION_TOOLS

        tool = next(t for t in MISSION_TOOLS if t.name == "list_missions")
        page_size_schema = tool.inputSchema["properties"]["page_size"]
        assert page_size_schema["default"] == 20
        assert page_size_schema["minimum"] == 1
        assert page_size_schema["maximum"] == 100
