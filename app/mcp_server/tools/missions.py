"""MCP tools for mission management.

Provides tools for creating, listing, getting, submitting, and checking
status of missions in TraceLab.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from mcp.server import Server
from mcp.types import TextContent, Tool

from app.core.config import settings
from app.core.database import get_db
from app.schemas.mission import MissionCreate, MissionUpdate
from app.services.deepsearch_client import (
    DeepSearchClient,
    DeepSearchClientError,
    DeepSearchConfigurationError,
)
from app.services.mission_service import (
    MissionNotFoundError,
    MissionService,
    MissionValidationError,
)

logger = logging.getLogger(__name__)

# Module-level service instance
_mission_service = MissionService()


def _serialize_mission(mission) -> Dict[str, Any]:
    """Serialize a Mission ORM object to a dictionary.

    Handles UUID and datetime serialization for JSON output.
    """
    return {
        "id": str(mission.id) if mission.id else None,
        "project_id": str(mission.project_id) if mission.project_id else None,
        "mission_id": mission.mission_id,
        "title": mission.title,
        "objective": mission.objective,
        "success_criteria": mission.success_criteria or [],
        "context": mission.context or {},
        "deliverables": mission.deliverables or [],
        "research_phases": mission.research_phases or {},
        "tags": mission.tags or [],
        "metadata": mission.mission_metadata or {},
        "research_depth": mission.research_depth or "baseline",
        "status": mission.status,
        "queued_at": mission.queued_at.isoformat() if mission.queued_at else None,
        "started_at": mission.started_at.isoformat() if mission.started_at else None,
        "completed_at": mission.completed_at.isoformat() if mission.completed_at else None,
        "deepsearch_job_id": mission.deepsearch_job_id,
        "execution_metadata": mission.execution_metadata or {},
        "result_document_ids": [str(d) for d in (mission.result_document_ids or [])],
        "result_report_id": str(mission.result_report_id) if mission.result_report_id else None,
        "result_markdown": mission.result_markdown,
        "result_protocol": mission.result_protocol,
        "error_message": mission.error_message,
        "created_at": mission.created_at.isoformat() if mission.created_at else None,
        "updated_at": mission.updated_at.isoformat() if mission.updated_at else None,
        "created_by": mission.created_by,
    }


# Tool definitions for MCP server registration
MISSION_TOOLS: List[Tool] = [
    Tool(
        name="create_mission",
        description="Create a new mission in TraceLab for research tracking or DeepSearch execution.",
        inputSchema={
            "type": "object",
            "properties": {
                "mission_id": {
                    "type": "string",
                    "description": "Human-readable mission identifier (e.g., 'B16.1', 'research-001')",
                    "minLength": 1,
                    "maxLength": 50,
                },
                "title": {
                    "type": "string",
                    "description": "Mission title (3-255 characters)",
                    "minLength": 3,
                    "maxLength": 255,
                },
                "objective": {
                    "type": "string",
                    "description": "What this mission aims to achieve (minimum 10 characters)",
                    "minLength": 10,
                },
                "success_criteria": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of measurable success conditions (at least 1 required)",
                    "minItems": 1,
                },
                "project_id": {
                    "type": "string",
                    "description": "UUID of the project to associate this mission with (optional)",
                },
                "context": {
                    "type": "object",
                    "description": "Additional context for the mission (optional)",
                },
                "deliverables": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Expected deliverables (optional)",
                },
                "research_phases": {
                    "type": "object",
                    "description": "Research phase configuration (optional)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization (optional)",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high", "critical"],
                    "default": "normal",
                    "description": "Mission priority (optional)",
                },
                "max_loops": {
                    "type": "integer",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Maximum DeepSearch iteration loops (optional)",
                },
                "research_depth": {
                    "type": "string",
                    "enum": ["baseline", "deep", "alpha"],
                    "default": "baseline",
                    "description": "Research depth tier: baseline (quick verification), deep (comprehensive analysis), alpha (novel domain exploration)",
                },
            },
            "required": ["mission_id", "title", "objective", "success_criteria"],
        },
    ),
    Tool(
        name="list_missions",
        description="List missions with optional filtering by project and status. Returns paginated results.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Filter by project UUID (optional)",
                },
                "status": {
                    "type": "string",
                    "enum": ["draft", "queued", "in_progress", "completed", "blocked", "cancelled"],
                    "description": "Filter by mission status (optional)",
                },
                "page": {
                    "type": "integer",
                    "default": 1,
                    "minimum": 1,
                    "description": "Page number (1-indexed)",
                },
                "page_size": {
                    "type": "integer",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Results per page (1-100)",
                },
            },
        },
    ),
    Tool(
        name="get_mission",
        description="Get full details of a specific mission including results if available.",
        inputSchema={
            "type": "object",
            "properties": {
                "mission_id": {
                    "type": "string",
                    "description": "The mission's human-readable ID (e.g., 'B16.1') or UUID",
                },
            },
            "required": ["mission_id"],
        },
    ),
    Tool(
        name="submit_mission",
        description="Submit a mission for DeepSearch execution. The mission must have valid success_criteria.",
        inputSchema={
            "type": "object",
            "properties": {
                "mission_id": {
                    "type": "string",
                    "description": "The mission's human-readable ID (e.g., 'B16.1') or UUID",
                },
                "research_depth": {
                    "type": "string",
                    "enum": ["baseline", "deep", "alpha"],
                    "description": "Override research depth at submission time. If not provided, uses the depth set at creation (default: baseline)",
                },
            },
            "required": ["mission_id"],
        },
    ),
    Tool(
        name="get_mission_status",
        description="Get the current status and progress of a mission, including results if completed.",
        inputSchema={
            "type": "object",
            "properties": {
                "mission_id": {
                    "type": "string",
                    "description": "The mission's human-readable ID (e.g., 'B16.1') or UUID",
                },
            },
            "required": ["mission_id"],
        },
    ),
]


def _get_mission_by_id_or_mission_id(db, mission_id_str: str):
    """Look up a mission by UUID or human-readable mission_id."""
    # Try as UUID first
    try:
        uuid_val = UUID(mission_id_str)
        return _mission_service.get_mission(db, uuid_val)
    except (ValueError, MissionNotFoundError):
        pass

    # Try as human-readable mission_id
    return _mission_service.get_mission_by_mission_id(db, mission_id_str)


async def handle_create_mission(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle the create_mission tool call."""
    import json

    try:
        # Parse project_id if provided
        project_id = None
        if arguments.get("project_id"):
            project_id = UUID(arguments["project_id"])

        # Build metadata with priority and max_loops
        metadata = {}
        if arguments.get("priority"):
            metadata["priority"] = arguments["priority"]
        if arguments.get("max_loops"):
            metadata["max_loops"] = arguments["max_loops"]

        # Create the mission
        create_data = MissionCreate(
            mission_id=arguments["mission_id"],
            title=arguments["title"],
            objective=arguments["objective"],
            success_criteria=arguments["success_criteria"],
            project_id=project_id,
            context=arguments.get("context", {}),
            deliverables=arguments.get("deliverables", []),
            research_phases=arguments.get("research_phases", {}),
            tags=arguments.get("tags", []),
            metadata=metadata,
            research_depth=arguments.get("research_depth", "baseline"),
            status="draft",
            created_by="mcp-tool",
        )

        # Get a database session
        db = next(get_db())
        try:
            mission = _mission_service.create_mission(db, create_data)
            result = _serialize_mission(mission)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        finally:
            db.close()

    except MissionValidationError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except Exception as e:
        logger.exception("Error creating mission")
        return [TextContent(type="text", text=json.dumps({"error": f"Failed to create mission: {str(e)}"}))]


async def handle_list_missions(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle the list_missions tool call."""
    import json

    try:
        project_id = None
        if arguments.get("project_id"):
            project_id = UUID(arguments["project_id"])

        page = arguments.get("page", 1)
        page_size = arguments.get("page_size", 20)
        status = arguments.get("status")

        db = next(get_db())
        try:
            missions, pagination = _mission_service.list_missions(
                db,
                page=page,
                page_size=page_size,
                status=status,
                project_id=project_id,
            )

            result = {
                "data": [_serialize_mission(m) for m in missions],
                "pagination": {
                    "page": pagination.page,
                    "page_size": pagination.page_size,
                    "total": pagination.total,
                    "pages": pagination.pages,
                },
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        finally:
            db.close()

    except MissionValidationError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except Exception as e:
        logger.exception("Error listing missions")
        return [TextContent(type="text", text=json.dumps({"error": f"Failed to list missions: {str(e)}"}))]


async def handle_get_mission(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle the get_mission tool call."""
    import json

    try:
        mission_id = arguments["mission_id"]

        db = next(get_db())
        try:
            mission = _get_mission_by_id_or_mission_id(db, mission_id)
            result = _serialize_mission(mission)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        finally:
            db.close()

    except MissionNotFoundError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except Exception as e:
        logger.exception("Error getting mission")
        return [TextContent(type="text", text=json.dumps({"error": f"Failed to get mission: {str(e)}"}))]


async def handle_submit_mission(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle the submit_mission tool call.

    Supports two modes (controlled by DEEPSEARCH_MODE env var):
    - "worker": Just sets status='queued', DeepSearch worker polls DB (Railway prod)
    - "http": POSTs to DeepSearch API with callback URL (local dev)

    This tool:
    1. Fetches the mission from TraceLab
    2. Validates success_criteria is not empty
    3. Checks mission isn't already queued/in_progress
    4. Worker mode: Sets status='queued' for worker to pick up
       HTTP mode: POSTs to DeepSearch /missions/execute
    5. Returns job info
    """
    import json

    try:
        mission_id = arguments["mission_id"]

        db = next(get_db())
        try:
            # 1. Fetch the mission
            mission = _get_mission_by_id_or_mission_id(db, mission_id)

            # 2. Validate success_criteria
            if not mission.success_criteria or len(mission.success_criteria) == 0:
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "Mission must have at least one success criterion to be submitted",
                        "mission_id": mission.mission_id,
                    })
                )]

            # 3. Check if already submitted
            if mission.status in ("queued", "in_progress"):
                return [TextContent(
                    type="text",
                    text=json.dumps({
                        "error": f"Mission is already {mission.status}",
                        "mission_id": mission.mission_id,
                        "deepsearch_job_id": mission.deepsearch_job_id,
                    })
                )]

            # 4. Check mode: worker (DB polling) or http (API calls)
            deepsearch_mode = getattr(settings, 'deepsearch_mode', 'worker').lower()

            if deepsearch_mode == "http":
                # HTTP mode: POST to DeepSearch API (for local dev)
                base_url = getattr(settings, 'api_base_url', None) or "http://localhost:8000"
                callback_url = f"{base_url}/api/v1/webhooks/deepsearch"

                # Use override research_depth if provided, else mission's depth
                effective_depth = arguments.get("research_depth") or mission.research_depth or "baseline"

                try:
                    client = DeepSearchClient()
                    response = await client.execute_mission(
                        mission_id=mission.mission_id,
                        title=mission.title,
                        objective=mission.objective,
                        success_criteria=mission.success_criteria,
                        callback_url=callback_url,
                        context=mission.context or {},
                        deliverables=mission.deliverables or [],
                        research_phases=mission.research_phases or {},
                        metadata=mission.mission_metadata or {},
                        research_depth=effective_depth,
                    )
                    job_id = response.job_id
                    logger.info(
                        "Mission %s submitted to DeepSearch via HTTP, job_id=%s",
                        mission.mission_id,
                        job_id,
                    )
                except DeepSearchConfigurationError as e:
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "error": f"DeepSearch not configured: {e}",
                            "mission_id": mission.mission_id,
                            "hint": "Set DEEPSEARCH_API_URL and DEEPSEARCH_API_KEY, or use DEEPSEARCH_MODE=worker",
                        })
                    )]
                except DeepSearchClientError as e:
                    logger.error("DeepSearch HTTP submission failed: %s", e)
                    return [TextContent(
                        type="text",
                        text=json.dumps({
                            "error": f"DeepSearch submission failed: {e}",
                            "mission_id": mission.mission_id,
                            "error_code": getattr(e, 'error_code', None),
                            "status_code": getattr(e, 'status_code', None),
                        })
                    )]

                # Update with job_id from HTTP response
                update_data = MissionUpdate(
                    status="queued",
                    deepsearch_job_id=job_id,
                )
                message = "Mission submitted to DeepSearch via HTTP."
            else:
                # Worker mode: Just set status to queued, worker will pick it up
                job_id = None  # Worker will set its own job_id
                update_data = MissionUpdate(status="queued")
                message = "Mission queued for DeepSearch worker."
                logger.info(
                    "Mission %s queued for DeepSearch worker pickup",
                    mission.mission_id,
                )

            # 5. Update mission status
            updated_mission = _mission_service.update_mission(db, mission.id, update_data)

            result = {
                "status": "queued",
                "mode": deepsearch_mode,
                "mission_id": updated_mission.mission_id,
                "uuid": str(updated_mission.id),
                "message": message,
            }
            if job_id:
                result["job_id"] = job_id
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        finally:
            db.close()

    except MissionNotFoundError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except Exception as e:
        logger.exception("Error submitting mission")
        return [TextContent(type="text", text=json.dumps({"error": f"Failed to submit mission: {str(e)}"}))]


async def handle_get_mission_status(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle the get_mission_status tool call.

    Returns:
    - status: Current mission status
    - progress: Execution progress information
    - results: If completed, includes document IDs, report ID, and markdown
    """
    import json

    try:
        mission_id = arguments["mission_id"]

        db = next(get_db())
        try:
            mission = _get_mission_by_id_or_mission_id(db, mission_id)

            # Build status response
            result = {
                "mission_id": mission.mission_id,
                "uuid": str(mission.id),
                "status": mission.status,
                "deepsearch_job_id": mission.deepsearch_job_id,
                "timestamps": {
                    "created_at": mission.created_at.isoformat() if mission.created_at else None,
                    "queued_at": mission.queued_at.isoformat() if mission.queued_at else None,
                    "started_at": mission.started_at.isoformat() if mission.started_at else None,
                    "completed_at": mission.completed_at.isoformat() if mission.completed_at else None,
                },
            }

            # Add execution metadata if available
            if mission.execution_metadata:
                result["execution_metadata"] = mission.execution_metadata

            # Add error message if blocked/failed
            if mission.error_message:
                result["error_message"] = mission.error_message

            # Add results if completed
            if mission.status == "completed":
                result["results"] = {
                    "document_ids": [str(d) for d in (mission.result_document_ids or [])],
                    "report_id": str(mission.result_report_id) if mission.result_report_id else None,
                    "has_markdown": bool(mission.result_markdown),
                    "has_protocol": bool(mission.result_protocol),
                }
                if mission.result_markdown:
                    # Include first 500 chars of markdown as preview
                    result["results"]["markdown_preview"] = mission.result_markdown[:500]
                    if len(mission.result_markdown) > 500:
                        result["results"]["markdown_preview"] += "..."

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        finally:
            db.close()

    except MissionNotFoundError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except Exception as e:
        logger.exception("Error getting mission status")
        return [TextContent(type="text", text=json.dumps({"error": f"Failed to get mission status: {str(e)}"}))]


# Handler dispatch map
TOOL_HANDLERS = {
    "create_mission": handle_create_mission,
    "list_missions": handle_list_missions,
    "get_mission": handle_get_mission,
    "submit_mission": handle_submit_mission,
    "get_mission_status": handle_get_mission_status,
}


def register_mission_tools(server: Server) -> None:
    """Register all mission management tools with the MCP server."""

    @server.list_tools()
    async def list_tools() -> List[Tool]:
        return MISSION_TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        return await handler(arguments)
