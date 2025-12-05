# Operator Console Guide

The Operator Console provides visibility into Mission Protocol data, evidence relationships, and correction queue status. This guide covers how to use the console for operational monitoring and data export.

## Overview

The console is accessible at `/console` and requires authentication. It consists of three main views:

1. **Dashboard** (`/console`) - Overview of mission status and corrections
2. **Mission List** (`/console/missions`) - Browse and filter missions
3. **Mission Detail** (`/console/missions/[id]`) - View mission relationships and export data
4. **Corrections Queue** (`/console/corrections`) - Monitor auto-linking correction status

## Dashboard

The dashboard provides a high-level view of system health:

### Mission Overview
- **Total Missions**: Count of all missions in the system
- **In Progress**: Missions currently being worked on
- **Complete**: Finished missions
- **Draft**: Missions not yet started
- **In Review**: Missions awaiting review

### Quality Distribution
- **Excellent (80-100%)**: High-quality missions
- **Good (60-79%)**: Above-average completion
- **Fair (40-59%)**: Needs attention
- **Poor (0-39%)**: Requires immediate action

### Recent Missions
Quick access to the 5 most recently updated missions.

### Corrections Overview
Summary of the auto-linking correction queue with retry and clear actions.

## Mission List

Browse all missions with filtering and sorting capabilities.

### Filters
- **Search**: Filter by title or mission ID
- **Status**: Filter by draft, in_progress, review, or complete
- **Quality**: Filter by completion percentage range

### Sorting
Click column headers to sort by:
- Title
- Completion percentage
- Updated date

### Actions
Click any mission row to view its detail page.

## Mission Detail

View comprehensive mission data including relationships and export options.

### Stats
- Completion percentage
- Evidence item count (linked vs total)
- Quality gate status (passing/failing)

### Research Statement
If available, shows the mission's topic, objective, and scope.

### Quality Gates
Visual display of each quality gate with pass/fail/pending status.

### Evidence
List of evidence items with linking status and relevance scores.

### Relationship Tree
Hierarchical view of connected entities:
- **Documents**: Source documents with linked chunks
- **Chunks**: Individual text chunks with relevance scores
- **Insights**: Validated or pending insights
- **Related Missions**: Other missions sharing evidence

### Export
Export mission data in JSON or YAML format:
- Click **JSON** for machine-readable format
- Click **YAML** for human-readable format

Both formats include mission data and relationships (if available).

## Corrections Queue

Monitor and manage the auto-linking correction queue.

### Stats Grid
- **Pending**: Items waiting for retry
- **In Progress**: Currently processing
- **Completed**: Successfully corrected
- **Failed**: Exhausted retry attempts
- **Success Rate**: Overall correction success percentage

### Queue Tab
Detailed view of recent correction items with:
- Status badge (pending, in_progress, completed, failed, skipped)
- Error type classification
- Retry count
- Best similarity score achieved
- Time since last update

### Telemetry Tab
Grafana-ready JSON data for external monitoring:
- Queue counts
- Webhook delivery stats
- Success rate metrics

### Dead Letter Tab
Failed webhook deliveries that require manual intervention:
- Target URL
- Error message
- Retry attempts
- Payload inspection

### Actions
- **Retry Pending**: Queue pending items for immediate retry
- **Clear Completed**: Remove completed items from queue
- **Process Now**: Trigger immediate processing of pending items

## Authentication

All console routes are protected by the `AuthGate` component. Users must be authenticated to access:
- `/console`
- `/console/missions`
- `/console/missions/[id]`
- `/console/corrections`

The authentication header with username and logout button appears on all protected pages.

## API Endpoints

The console consumes these backend endpoints:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/missions` | GET | List all missions |
| `/api/v1/missions/{id}` | GET | Get mission detail |
| `/api/v1/missions/{id}/related` | GET | Get relationship context |
| `/api/v1/deepsearch/corrections` | GET | Get correction status |
| `/api/v1/deepsearch/corrections` | POST | Trigger corrections |
| `/api/v1/deepsearch/corrections/telemetry` | GET | Get telemetry summary |
| `/api/v1/deepsearch/corrections/dead-letter` | GET | Get failed webhooks |

## Performance

The console is optimized for:
- Initial page load under 2 seconds
- Cached relationship data when available
- Parallel API calls for dashboard data
- Client-side filtering for mission list

## Troubleshooting

### Console shows "Loading..."
- Check that the backend API is running
- Verify authentication token is valid
- Check browser console for network errors

### No relationships displayed
- The mission may not have evidence with chunk links
- Relationship API may not be available for this mission type

### Export buttons not working
- Check browser popup/download settings
- Ensure JavaScript is enabled

### Correction retries not processing
- Check backend logs for processing errors
- Verify webhook URLs are accessible
- Review dead letter queue for delivery failures
