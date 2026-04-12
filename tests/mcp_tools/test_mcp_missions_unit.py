"""Unit tests for MCP mission management tools (B16.4).

These tests verify the MCP tool definitions and handlers without requiring
database access. For integration tests that require the database, see
test_mcp_missions.py.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import MagicMock


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
        mission = MagicMock()
        mission.id = "test-uuid"
        mission.project_id = None
        mission.mission_id = "MCP-TEST-001"
        mission.title = "Test Mission"
        mission.objective = "Test objective"
        mission.success_criteria = ["Criterion 1"]
        mission.context = {"key": "value"}
        mission.deliverables = ["file.py"]
        mission.research_phases = {}
        mission.tags = ["test"]
        mission.mission_metadata = {"priority": "normal"}
        mission.status = "draft"
        mission.queued_at = None
        mission.started_at = None
        mission.completed_at = None
        mission.deepsearch_job_id = None
        mission.execution_metadata = {}
        mission.result_document_ids = []
        mission.result_report_id = None
        mission.result_markdown = None
        mission.result_protocol = None
        mission.error_message = None
        mission.created_at = datetime.utcnow()
        mission.updated_at = datetime.utcnow()
        mission.created_by = "test"

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

        mission = MagicMock()
        mission.id = "test-uuid-2"
        mission.project_id = "project-uuid"
        mission.mission_id = "MCP-TEST-002"
        mission.title = "Completed Mission"
        mission.objective = "Test completed"
        mission.success_criteria = ["Done"]
        mission.context = {}
        mission.deliverables = []
        mission.research_phases = {}
        mission.tags = []
        mission.mission_metadata = {}
        mission.status = "completed"
        mission.queued_at = datetime.utcnow()
        mission.started_at = datetime.utcnow()
        mission.completed_at = datetime.utcnow()
        mission.deepsearch_job_id = "ds-job-123"
        mission.execution_metadata = {"duration_ms": 5000}
        mission.result_document_ids = [doc_id]
        mission.result_report_id = report_id
        mission.result_markdown = "# Results"
        mission.result_protocol = {"version": "1.0"}
        mission.error_message = None
        mission.created_at = datetime.utcnow()
        mission.updated_at = datetime.utcnow()
        mission.created_by = "mcp-tool"

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

        mission = MagicMock()
        mission.id = "test-uuid-3"
        mission.project_id = None
        mission.mission_id = "MCP-TEST-003"
        mission.title = "Minimal"
        mission.objective = "Minimal mission"
        mission.success_criteria = ["Test"]
        mission.context = None
        mission.deliverables = None
        mission.research_phases = None
        mission.tags = None
        mission.mission_metadata = None
        mission.status = "draft"
        mission.queued_at = None
        mission.started_at = None
        mission.completed_at = None
        mission.deepsearch_job_id = None
        mission.execution_metadata = None
        mission.result_document_ids = None
        mission.result_report_id = None
        mission.result_markdown = None
        mission.result_protocol = None
        mission.error_message = None
        mission.created_at = datetime.utcnow()
        mission.updated_at = datetime.utcnow()
        mission.created_by = None

        result = _serialize_mission(mission)

        assert result["project_id"] is None
        assert result["context"] == {}
        assert result["deliverables"] == []
        assert result["result_markdown"] is None


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
