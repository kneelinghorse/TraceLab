# TraceLab MCP Tools

This document describes the MCP (Model Context Protocol) tools available in TraceLab for mission management.

## Overview

TraceLab provides an MCP server that exposes tools for AI agents to interact with the mission management system. These tools allow agents to create, list, query, and submit missions for execution.

## Installation

The MCP server requires the `mcp` package:

```bash
pip install mcp
```

## Running the MCP Server

```bash
python -m app.mcp_server.server
```

Or import and run programmatically:

```python
from app.mcp_server import create_mcp_server

server = create_mcp_server("my-tracelab-server")
```

## Available Tools

### create_mission

Create a new mission in TraceLab for research tracking or DeepSearch execution.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `mission_id` | string | Yes | Human-readable identifier (e.g., "B16.1", "research-001"). 1-50 characters. |
| `title` | string | Yes | Mission title. 3-255 characters. |
| `objective` | string | Yes | What this mission aims to achieve. Minimum 10 characters. |
| `success_criteria` | string[] | Yes | List of measurable success conditions. At least 1 required. |
| `project_id` | string | No | UUID of the project to associate this mission with. |
| `context` | object | No | Additional context for the mission. |
| `deliverables` | string[] | No | Expected deliverables. |
| `research_phases` | object | No | Research phase configuration. |
| `tags` | string[] | No | Tags for categorization. |
| `priority` | string | No | Mission priority: "low", "normal", "high", or "critical". Default: "normal" |
| `max_loops` | integer | No | Maximum DeepSearch iteration loops (1-10). Default: 3 |

**Returns:** The created mission object with all fields.

**Example:**

```json
{
  "mission_id": "B16.5",
  "title": "Implement DeepSearch Client",
  "objective": "Build a client library for communicating with the DeepSearch API",
  "success_criteria": [
    "Client can authenticate with DeepSearch",
    "Client can submit missions",
    "Client can poll for status"
  ],
  "tags": ["api", "client"],
  "priority": "high"
}
```

### list_missions

List missions with optional filtering by project and status. Returns paginated results.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `project_id` | string | No | Filter by project UUID. |
| `status` | string | No | Filter by status: "draft", "queued", "in_progress", "completed", "blocked", or "cancelled". |
| `page` | integer | No | Page number (1-indexed). Default: 1 |
| `page_size` | integer | No | Results per page (1-100). Default: 20 |

**Returns:** Paginated list of missions with pagination metadata.

**Example:**

```json
{
  "status": "in_progress",
  "page": 1,
  "page_size": 10
}
```

### get_mission

Get full details of a specific mission including results if available.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `mission_id` | string | Yes | The mission's human-readable ID (e.g., "B16.1") or UUID. |

**Returns:** Full mission object with all fields and results.

**Example:**

```json
{
  "mission_id": "B16.5"
}
```

### submit_mission

Submit a mission for DeepSearch execution. The mission must have valid success_criteria.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `mission_id` | string | Yes | The mission's human-readable ID (e.g., "B16.1") or UUID. |

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | string | DeepSearch job ID for tracking. |
| `status` | string | Current status (will be "queued"). |
| `mission_id` | string | The mission's human-readable ID. |
| `uuid` | string | The mission's UUID. |
| `eta` | string | Estimated time (pending DeepSearch integration). |

**Workflow:**

1. Fetches the mission from TraceLab
2. Validates success_criteria is not empty
3. Updates mission status to "queued"
4. Stores the deepsearch_job_id for tracking

**Note:** Full DeepSearch API integration requires B16.5 (DeepSearch Client).

**Example:**

```json
{
  "mission_id": "B16.5"
}
```

### get_mission_status

Get the current status and progress of a mission, including results if completed.

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `mission_id` | string | Yes | The mission's human-readable ID (e.g., "B16.1") or UUID. |

**Returns:**

| Field | Type | Description |
|-------|------|-------------|
| `mission_id` | string | Human-readable mission ID. |
| `uuid` | string | Mission UUID. |
| `status` | string | Current status. |
| `deepsearch_job_id` | string | DeepSearch job ID if submitted. |
| `timestamps` | object | Created, queued, started, and completed timestamps. |
| `execution_metadata` | object | Execution metrics (if available). |
| `error_message` | string | Error details if blocked/failed. |
| `results` | object | Results object if completed (see below). |

**Results Object (when status is "completed"):**

| Field | Type | Description |
|-------|------|-------------|
| `document_ids` | string[] | UUIDs of documents produced. |
| `report_id` | string | UUID of the generated report. |
| `has_markdown` | boolean | Whether markdown output is available. |
| `has_protocol` | boolean | Whether protocol result is available. |
| `markdown_preview` | string | First 500 characters of markdown (if available). |

**Example:**

```json
{
  "mission_id": "B16.5"
}
```

## Error Handling

All tools return JSON responses. Errors are returned in the format:

```json
{
  "error": "Error message describing what went wrong"
}
```

Common error scenarios:

- **Mission not found:** When the specified mission_id doesn't exist.
- **Validation error:** When required fields are missing or invalid.
- **Already submitted:** When trying to submit an already queued/in-progress mission.
- **Empty success_criteria:** When submitting a mission without success criteria.

## Mission Statuses

| Status | Description |
|--------|-------------|
| `draft` | Initial state, mission is being defined. |
| `queued` | Mission submitted for execution, waiting in queue. |
| `in_progress` | Mission is actively being executed. |
| `completed` | Mission finished successfully with results. |
| `blocked` | Mission cannot proceed, requires intervention. |
| `cancelled` | Mission was cancelled before completion. |

## Integration with DeepSearch

The `submit_mission` tool prepares missions for DeepSearch execution:

1. Mission is created with `create_mission`
2. Mission is submitted with `submit_mission` (status becomes "queued")
3. DeepSearch picks up the mission and starts execution (status becomes "in_progress")
4. Results are stored when complete (status becomes "completed")
5. Use `get_mission_status` to poll for completion and retrieve results

**Note:** Full DeepSearch integration requires the DeepSearch Client (B16.5) to be implemented.
